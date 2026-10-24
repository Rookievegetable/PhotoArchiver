"""S4 C-3 — 建议服务编排的准入集成单元测试（内存仓储；D2/D3/D4/D5=A）.

覆盖：sample_match 优先与剩余集推导、整批 auto_confirmed 落库、数量不一致/
时间缺失/严格位置拒绝对时的既有 suggested 行为（D3=A，零部分自动确认）、
人工决策保护（已确认簇/人员排除）、重复调用幂等与摘要口径。
不接入生产数据库；排序断言验证 sort_key 与 roster_order 语义。
"""

from datetime import datetime, timedelta, timezone

from photo_archiver.application.commands.pairing import (
    StartSuggestPairingsCommand,
)
from photo_archiver.application.services import SuggestPairingsService
from photo_archiver.domain import RecognitionRun, build_sort_key
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


def _real_sort_keys() -> list[str]:
    """真实 ``build_sort_key`` 产物（P4-T5a）：插入序 c,b,a（注册序）与拍摄
    时间序 a<b<c 相反；时间文本与生产一致恒为六位微秒精度（timespec=
    microseconds，含 a 的整秒 .000000 形态），a、b 同处 8:00:00 一秒内——
    真实键的不规则结构（可变长路径段）由此进入配对链。"""
    return [
        build_sort_key(
            datetime(2026, 1, 1, 8, 0, 2).isoformat(timespec="microseconds"),
            "photos/c.jpg", 0,
        ),
        build_sort_key(
            datetime(2026, 1, 1, 8, 0, 0, 500000).isoformat(timespec="microseconds"),
            "photos/b.jpg", 1,
        ),
        build_sort_key(
            datetime(2026, 1, 1, 8, 0, 0).isoformat(timespec="microseconds"),
            "photos/a.jpg", 2,
        ),
    ]


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
    generation = world.add_generation(_real_sort_keys())

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
    """真实 build_sort_key 产物驱动位置配对：拍摄时间序簇 × roster_order 升序人员。

    键为真实 ``build_sort_key`` 产物（非合成字符串）：插入序 c,b,a（注册序）
    与拍摄时间序 a<b<c 相反；a 秒级、b 微秒级（同秒 8:00:00 内混合）、c 秒级。
    """
    world = _World()
    # roster 故意与插入序不同：p_c=1、p_a=2、p_b=3
    p_a = world.add_person("甲", 2)
    p_b = world.add_person("乙", 3)
    p_c = world.add_person("丙", 1)
    generation = world.add_generation(_real_sort_keys())
    cluster_by_key = {
        c.sort_key.split("|")[1]: c
        for c in world.clusters.list_clusters(generation.id)
    }

    world.build_services().execute(StartSuggestPairingsCommand(generation.id))

    rows = {r.cluster_id: r for r in world.active_rows(generation.id)}
    # 拍摄时间序 a(8:00:00) < b(8:00:00.5) < c(8:00:02)：
    # a → roster 1（丙）、b → roster 2（甲）、c → roster 3（乙）。
    assert rows[cluster_by_key["photos/a.jpg"].id].person_id == p_c.id
    assert rows[cluster_by_key["photos/b.jpg"].id].person_id == p_a.id
    assert rows[cluster_by_key["photos/c.jpg"].id].person_id == p_b.id


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


def test_cross_offset_aware_clusters_positional_pairing_follows_absolute_time():
    """T11：跨 UTC 偏移 aware 簇经真实 SuggestPairingsService 整批位置配对
    按绝对时间序（A-min 消费端）。

    簇 A=`09:00+08:00`(01:00Z 早, photos/z.jpg)、簇 B=`02:00+00:00`(02:00Z
    晚, photos/a.jpg)——时间序与路径序刻意相反；独立全 aware 用例（不与
    naive 键混排，不固化 naive/aware 边界序）。修复前原始偏移文本序会把
    B 排前 → 配对颠倒；修复后 A→roster 1、B→roster 2。
    """
    world = _World()
    p_first = world.add_person("甲", 1)
    p_second = world.add_person("乙", 2)
    cluster_run = FaceClusterRun(
        recognition_run_id=world.recognition_run.id, algorithm_version="v1",
    )
    world.clusters.add_cluster_run(cluster_run)
    aware_specs = [
        (
            datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone(timedelta(hours=8))),
            "photos/z.jpg",
        ),
        (
            datetime(2026, 1, 1, 2, 0, 0, tzinfo=timezone.utc),
            "photos/a.jpg",
        ),
    ]
    clusters = []
    for ordinal, (captured, path_key) in enumerate(aware_specs):
        cluster = FaceCluster(
            cluster_run_id=cluster_run.id,
            run_id=world.recognition_run.id,
            ordinal=ordinal,
            member_count=1,
            sort_key=build_sort_key(
                captured.astimezone(timezone.utc).isoformat(
                    timespec="microseconds"),
                path_key, ordinal,
            ),
            first_captured_at=captured,
        )
        world.clusters.add_clusters([cluster])
        clusters.append(cluster)
    cluster_run.start()
    cluster_run.complete(len(clusters), len(clusters), 0)

    summary = world.build_services().execute(
        StartSuggestPairingsCommand(cluster_run.id))

    assert summary.auto_confirmed == 2
    assert summary.auto_confirm_blocked_reason is None
    rows = {r.cluster_id: r for r in world.active_rows(cluster_run.id)}
    cluster_by_path = {c.sort_key.split("|")[1]: c for c in clusters}
    # 绝对时间序：A(01:00Z, photos/z.jpg) → roster 1（甲）；B(02:00Z,
    # photos/a.jpg) → roster 2（乙）。若按注册序/原始偏移文本序配对则颠倒。
    assert rows[cluster_by_path["photos/z.jpg"].id].person_id == p_first.id
    assert rows[cluster_by_path["photos/a.jpg"].id].person_id == p_second.id
    for cluster in clusters:
        row = rows[cluster.id]
        assert row.sort_snapshot["sort_key"] == cluster.sort_key
        assert row.sort_snapshot["first_captured_at"] == (
            cluster.first_captured_at.isoformat())
