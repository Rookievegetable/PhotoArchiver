"""S4 C-3 — 建议服务编排的准入集成单元测试（内存仓储；D2/D3/D4/D5=A）.

覆盖：sample_match 优先与剩余集推导、整批 auto_confirmed 落库、数量不一致/
时间缺失/严格位置拒绝对时的既有 suggested 行为（D3=A，零部分自动确认）、
人工决策保护（已确认簇/人员排除）、重复调用幂等与摘要口径。
不接入生产数据库；排序断言验证 sort_key 与 roster_order 语义。
"""

from datetime import datetime

from photo_archiver.application.commands.pairing import (
    StartSuggestPairingsCommand,
)
from photo_archiver.application.services import SuggestPairingsService
from photo_archiver.domain import RecognitionRun
from photo_archiver.domain.entities.face_cluster import FaceCluster, FaceClusterRun
from photo_archiver.domain.entities.person import Person
from photo_archiver.domain.services.positional_auto_confirm import (
    ADMISSION_REASON_COUNT_MISMATCH,
    ADMISSION_REASON_EMPTY_INPUT,
    ADMISSION_REASON_MISSING_CAPTURE_TIME,
    ADMISSION_REASON_REJECTED_POSITIONAL_PAIR,
)
from photo_archiver.infrastructure import (
    InMemoryClusterPersonAssignmentRepository,
    InMemoryFaceClusterRepository,
    InMemoryFaceObservationRepository,
    InMemoryPersonFaceSampleRepository,
    NumpyCosineSimilarityFactory,
)

_BASE = datetime(2026, 1, 1, 8, 0, 0)


class _ClusterRepo(InMemoryFaceClusterRepository):
    """InMemory 簇仓储（get_cluster_run 由基类经 add_cluster_run 登记）。"""

    def __init__(self):
        super().__init__()


class _PersonRepo:
    def __init__(self, persons):
        self._persons = persons

    def list_all(self):
        return sorted(
            self._persons.values(),
            key=lambda p: (
                p.roster_order is None,
                p.roster_order if p.roster_order is not None else 0,
                str(p.id),
            ),
        )


class _World:
    """一代聚类 + 名单；无观测/无样本（冷启动纯位置配对形态）。"""

    def __init__(self):
        self.clusters = _ClusterRepo()
        self.observations = InMemoryFaceObservationRepository()
        self.assignments = InMemoryClusterPersonAssignmentRepository(
            cluster_scope=self.clusters.list_clusters,
        )
        self.samples = InMemoryPersonFaceSampleRepository()
        self.persons = {}
        run = RecognitionRun(parameters={})
        self.recognition_run = run

    def add_person(self, name: str, roster_order: int | None) -> Person:
        person = Person(name=name, roster_order=roster_order)
        self.persons[person.id] = person
        return person

    def add_generation(self, sort_keys: list[str], *,
                       missing_time_indexes: tuple[int, ...] = ()) -> FaceClusterRun:
        cluster_run = FaceClusterRun(
            recognition_run_id=self.recognition_run.id, algorithm_version="v1",
        )
        self.clusters.add_cluster_run(cluster_run)
        clusters = []
        for ordinal, sort_key in enumerate(sort_keys):
            cluster = FaceCluster(
                cluster_run_id=cluster_run.id,
                run_id=self.recognition_run.id,
                ordinal=ordinal,
                member_count=1,
                sort_key=sort_key,
                first_captured_at=(
                    None if ordinal in missing_time_indexes else _BASE
                ),
            )
            self.clusters.add_clusters([cluster])
            clusters.append(cluster)
        cluster_run.start()
        cluster_run.complete(len(sort_keys), len(sort_keys), 0)
        return cluster_run

    def build_services(self) -> SuggestPairingsService:
        return SuggestPairingsService(
            self.clusters,
            self.observations,
            _PersonRepo(self.persons),
            self.assignments,
            self.samples,
            NumpyCosineSimilarityFactory(),
        )

    def active_rows(self, cluster_run_id):
        return self.assignments.list_active_by_cluster_run(cluster_run_id)


# ── 准入成功：整批 auto_confirmed ───────────────────────────────────────────


def test_cold_start_admitted_creates_auto_confirmed_rows():
    world = _World()
    for i in range(3):
        world.add_person(f"人员{i}", i + 1)
    generation = world.add_generation(["k|c|000001", "k|a|000002", "k|b|000003"])

    summary = world.build_services().execute(
        StartSuggestPairingsCommand(generation.id))

    assert summary.auto_confirmed == 3
    assert summary.suggestions == 0
    assert summary.ordered == 0 and summary.sample_matched == 0
    assert summary.auto_confirm_blocked_reason is None

    rows = world.active_rows(generation.id)
    assert len(rows) == 3
    assert all(r.status == "auto_confirmed" for r in rows)
    assert all(r.source == "ordered_auto_confirm" for r in rows)
    assert all(r.score is None for r in rows)


def test_positional_pairing_follows_sort_key_and_roster_order():
    """严格位置对 = sort_key 升序簇 × roster_order 升序人员（输入乱序也一致）。"""
    world = _World()
    # roster 故意与插入序不同：p_c=1、p_a=2、p_b=3
    p_a = world.add_person("甲", 2)
    p_b = world.add_person("乙", 3)
    p_c = world.add_person("丙", 1)
    generation = world.add_generation(["k|c|000001", "k|a|000002", "k|b|000003"])
    cluster_by_key = {
        c.sort_key.split("|")[1]: c
        for c in world.clusters.list_clusters(generation.id)
    }

    world.build_services().execute(StartSuggestPairingsCommand(generation.id))

    rows = {r.cluster_id: r for r in world.active_rows(generation.id)}
    # sort_key 升序：a → roster 1（丙）、b → roster 2（甲）、c → roster 3（乙）
    assert rows[cluster_by_key["a"].id].person_id == p_c.id
    assert rows[cluster_by_key["b"].id].person_id == p_a.id
    assert rows[cluster_by_key["c"].id].person_id == p_b.id


def test_auto_confirmed_rows_carry_positional_sort_snapshot():
    world = _World()
    world.add_person("甲", 1)
    generation = world.add_generation(["k|a|000001"])

    world.build_services().execute(StartSuggestPairingsCommand(generation.id))

    row = world.active_rows(generation.id)[0]
    assert row.sort_snapshot["sort_key"] == "k|a|000001"
    assert row.sort_snapshot["first_captured_at"] == _BASE.isoformat()
    assert "auto_confirmed_at" in row.sort_snapshot


# ── 数量不一致 / 时间缺失 / 拒绝对 → 既有 suggested 行为（D3=A）────────────


def test_count_mismatch_keeps_existing_suggested_behavior():
    world = _World()
    world.add_person("甲", 1)
    world.add_person("乙", 2)
    generation = world.add_generation(["k|a|000001", "k|b|000002", "k|c|000003"])

    summary = world.build_services().execute(
        StartSuggestPairingsCommand(generation.id))

    assert summary.auto_confirmed == 0
    assert summary.auto_confirm_blocked_reason == ADMISSION_REASON_COUNT_MISMATCH
    assert summary.suggestions == 2 and summary.ordered == 2
    rows = world.active_rows(generation.id)
    assert len(rows) == 2
    assert all(r.status == "suggested" for r in rows)
    assert all(r.source == "ordered_suggestion" for r in rows)


def test_missing_capture_time_blocks_whole_batch():
    world = _World()
    world.add_person("甲", 1)
    world.add_person("乙", 2)
    generation = world.add_generation(
        ["k|a|000001", "k|b|000002"], missing_time_indexes=(1,))

    summary = world.build_services().execute(
        StartSuggestPairingsCommand(generation.id))

    assert summary.auto_confirmed == 0
    assert summary.auto_confirm_blocked_reason == ADMISSION_REASON_MISSING_CAPTURE_TIME
    rows = world.active_rows(generation.id)
    assert len(rows) == 2
    assert all(r.status == "suggested" for r in rows)


def test_rejected_positional_pair_blocks_and_suggested_path_keeps_filter():
    """严格位置对 (c_b,乙) 被拒：整批不自动确认；既有 suggested 路径按既有
    拒绝过滤语义顺延（c_a→甲、c_b→丙），历史行为不变。"""
    world = _World()
    p_a = world.add_person("甲", 1)
    p_b = world.add_person("乙", 2)
    p_c = world.add_person("丙", 3)
    generation = world.add_generation(["k|a|000001", "k|b|000002", "k|c|000003"])
    cluster_by_key = {
        c.sort_key.split("|")[1]: c
        for c in world.clusters.list_clusters(generation.id)
    }
    from photo_archiver.domain import ClusterPersonAssignment

    rejected_row = ClusterPersonAssignment(
        cluster_id=cluster_by_key["b"].id, person_id=p_b.id)
    rejected_row.reject()
    world.assignments.add_assignments([rejected_row])

    summary = world.build_services().execute(
        StartSuggestPairingsCommand(generation.id))

    assert summary.auto_confirmed == 0
    assert summary.auto_confirm_blocked_reason == (
        ADMISSION_REASON_REJECTED_POSITIONAL_PAIR)
    rows = {r.cluster_id: r for r in world.active_rows(generation.id)
            if r.status == "suggested"}
    # 既有规则③语义：被拒 (c_b,乙) 顺延到下一位人员（丙）。
    assert rows[cluster_by_key["a"].id].person_id == p_a.id
    assert rows[cluster_by_key["b"].id].person_id == p_c.id


# ── 人工决策保护与幂等 ──────────────────────────────────────────────────────


def test_existing_confirmed_decision_is_protected_and_excluded():
    """已 confirmed 的簇/人员被排除出剩余集；其余簇仍可整批自动确认。"""
    from photo_archiver.domain import ClusterPersonAssignment

    world = _World()
    p_confirmed = world.add_person("甲", 1)
    p_other = world.add_person("乙", 2)
    generation = world.add_generation(["k|a|000001", "k|b|000002"])
    cluster_by_key = {
        c.sort_key.split("|")[1]: c
        for c in world.clusters.list_clusters(generation.id)
    }
    confirmed_row = ClusterPersonAssignment(
        cluster_id=cluster_by_key["a"].id, person_id=p_confirmed.id)
    confirmed_row.confirm({"sort_key": "k|a|000001"})
    world.assignments.add_assignments([confirmed_row])

    summary = world.build_services().execute(
        StartSuggestPairingsCommand(generation.id))

    assert summary.auto_confirmed == 1
    rows = {r.cluster_id: r for r in world.active_rows(generation.id)}
    assert rows[cluster_by_key["a"].id].status == "confirmed"  # 人工决策未被触碰
    assert rows[cluster_by_key["b"].id].status == "auto_confirmed"
    assert rows[cluster_by_key["b"].id].person_id == p_other.id


def test_repeat_execution_is_idempotent_after_admitted_batch():
    world = _World()
    world.add_person("甲", 1)
    world.add_person("乙", 2)
    generation = world.add_generation(["k|a|000001", "k|b|000002"])

    service = world.build_services()
    first = service.execute(StartSuggestPairingsCommand(generation.id))
    assert first.auto_confirmed == 2
    before = len(world.assignments.list_by_cluster_run(generation.id))

    second = service.execute(StartSuggestPairingsCommand(generation.id))

    # 已 auto_confirmed 的簇进入 clusters_with_active、其人员进入身份占用
    # 排除 → E_c 与 E_p 同为空 → EMPTY_INPUT 阻断（比数量失配更精确：
    # 本代际已无任何剩余可配对对象），零新决策、零重复建议。
    assert second.auto_confirmed == 0
    assert second.auto_confirm_blocked_reason == ADMISSION_REASON_EMPTY_INPUT
    assert len(world.assignments.list_by_cluster_run(generation.id)) == before
