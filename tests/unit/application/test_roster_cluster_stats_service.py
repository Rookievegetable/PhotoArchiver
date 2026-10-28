"""P4 人员页统计面板的统计用例对拍测试（RosterClusterStatsService）.

验收 §3.1：构造多代际 + 多决策 → 面板四数字与**直查（仓储独立读回）**
对拍一致；锚点 = ``list_cluster_runs``（newest-first）首位；active 决策
（suggested / confirmed / auto_confirmed）之外的状态不计数；历史代际的
决策不并入锚点统计；空态（无 run / 无代际）返回 ``None`` / 空集。

对拍口径：oracle 全部走仓储读方法直接重算（与被测用例不同的代码路径），
不用被测服务的中间结果。
"""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.services import RosterClusterStatsService
from photo_archiver.domain import (
    ClusterPersonAssignment,
    FaceBox,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceEmbedding,
    FaceObservation,
    Person,
    RecognitionRun,
    RunPhotoSnapshot,
)
from photo_archiver.domain.entities.cluster_assignment import (
    ASSIGNMENT_SOURCE_MANUAL,
    ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
    ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
    ASSIGNMENT_STATUS_AUTO_CONFIRMED,
    ASSIGNMENT_STATUS_CONFIRMED,
    ASSIGNMENT_STATUS_REJECTED,
    ASSIGNMENT_STATUS_SUGGESTED,
    ASSIGNMENT_STATUS_UNASSIGNED,
)

_OLD_GEN_TIME = datetime(2026, 1, 1, 8, 0)
_NEW_GEN_TIME = datetime(2026, 2, 1, 8, 0)


class Harness:
    """Seed photos / observations / generations / decisions over SQLite."""

    def __init__(self, tmp_path: Path) -> None:
        self.repos = build_sqlite_repositories(tmp_path / "stats.db")
        self.service = RosterClusterStatsService(
            self.repos.face_clusters,
            self.repos.face_observations,
            self.repos.cluster_assignments,
        )

    def add_person(self, name: str) -> Person:
        person = Person(name=name)
        self.repos.people.add(person)
        assert person.id is not None
        return person

    def add_run(self, photo_count: int = 3) -> tuple:
        """One recognition run with ``photo_count`` photos; returns (run, photos)."""
        run = RecognitionRun(parameters={}, created_at=datetime(2026, 3, 1))
        self.repos.recognition_runs.add_run(run)
        photos = []
        for index in range(photo_count):
            from photo_archiver.domain import Photo, PhotoPath

            photo = Photo(path=PhotoPath(f"photos/p{index}-{uuid4()}.jpg"))
            self.repos.photos.add(photo)
            self.repos.recognition_runs.add_run_photos(run.id, [
                RunPhotoSnapshot(
                    run.id, photo.id, f"photos/p{index}-{uuid4()}.jpg",
                    datetime(2026, 3, 1),
                ),
            ])
            photos.append(photo)
        assert run.id is not None
        return run, photos

    def add_observation(self, run, photo, index: int) -> FaceObservation:
        observation = FaceObservation(
            run_id=run.id, photo_id=photo.id, face_index=index,
            photo_face_count=index + 1, det_score=0.9,
            box=FaceBox(index, 0, index + 10, 10),
            embedding=FaceEmbedding((1.0, 0.0)),
            scope_verdict="in_selected_scope",
        )
        self.repos.face_observations.add_many([observation])
        return observation

    def add_generation(self, run, member_groups, created_at: datetime):
        """One generation; ``member_groups`` = [[observation, ...], ...]."""
        generation = FaceClusterRun(
            recognition_run_id=run.id, algorithm_version="v1", created_at=created_at,
        )
        self.repos.face_clusters.add_cluster_run(generation)
        clusters = []
        for ordinal, observations in enumerate(member_groups):
            cluster = FaceCluster(
                cluster_run_id=generation.id, run_id=run.id, ordinal=ordinal,
                member_count=len(observations), sort_key=f"cluster-{ordinal}",
                first_captured_at=datetime(2026, 3, 1),
            )
            self.repos.face_clusters.add_clusters([cluster])
            clusters.append(cluster)
            for observation in observations:
                self.repos.face_clusters.add_members([
                    FaceClusterMember(
                        cluster_id=cluster.id, observation_id=observation.id,
                    ),
                ])
        generation.start()
        generation.complete(len(clusters), sum(len(g) for g in member_groups), 0)
        return generation, clusters

    def add_decision(
        self, cluster, person, *, status: str, source: str = ASSIGNMENT_SOURCE_MANUAL,
        created_at: datetime | None = None,
    ) -> ClusterPersonAssignment:
        decision = ClusterPersonAssignment(
            cluster_id=cluster.id,
            person_id=person.id if person is not None else None,
            status=status, source=source, created_at=created_at,
        )
        self.repos.cluster_assignments.add_assignments([decision])
        return decision


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def _oracle(harness: Harness, run_id, roster_total: int) -> dict:
    """独立 oracle：不经被测服务，直接用仓储读方法重算四数字。"""
    generations = harness.repos.face_clusters.list_cluster_runs(run_id)
    anchor = generations[0]
    observations = {
        observation.id: observation
        for observation in harness.repos.face_observations.list_by_run(run_id)
    }
    members = harness.repos.face_clusters.list_members(anchor.id)
    photo_ids = {
        observations[member.observation_id].photo_id
        for member in members
        if member.observation_id in observations
    }
    matched = {
        assignment.person_id
        for assignment in harness.repos.cluster_assignments.list_active_by_cluster_run(
            anchor.id,
        )
        if assignment.person_id is not None
    }
    return {
        "anchor_id": anchor.id,
        "photo_count": len(photo_ids),
        "face_count": len(members),
        "matched": matched,
        "unmatched": roster_total - len(matched),
    }


def test_stats_matches_direct_query_oracle_with_multi_generations(
    harness: Harness, tmp_path: Path,
) -> None:
    """多代际 + 多决策：四数字与直查 oracle 逐项一致（对拍）。"""
    people = [harness.add_person(name) for name in ("张三", "李四", "王五")]
    run, photos = harness.add_run(photo_count=3)
    o1 = harness.add_observation(run, photos[0], 0)
    o2 = harness.add_observation(run, photos[0], 1)  # 同照片第二张脸
    o3 = harness.add_observation(run, photos[1], 0)
    o4 = harness.add_observation(run, photos[2], 0)
    # 旧代际（非锚点）：也带决策——不得并入锚点统计。
    old_gen, old_clusters = harness.add_generation(
        run, [[o1, o2, o3], [o4]], _OLD_GEN_TIME,
    )
    harness.add_decision(
        old_clusters[0], people[0], status=ASSIGNMENT_STATUS_CONFIRMED,
        created_at=_OLD_GEN_TIME,
    )
    harness.add_decision(
        old_clusters[1], people[2], status=ASSIGNMENT_STATUS_SUGGESTED,
        source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION, created_at=_OLD_GEN_TIME,
    )
    # 锚点代际（最新）：3 张脸 / 2 张去重照片；张三 confirmed（active）、
    # 王五 rejected（终态，不计）、一条 unassigned（person=None，不计）。
    new_gen, new_clusters = harness.add_generation(
        run, [[o1, o3], [o2]], _NEW_GEN_TIME,
    )
    harness.add_decision(
        new_clusters[0], people[0], status=ASSIGNMENT_STATUS_CONFIRMED,
        created_at=_NEW_GEN_TIME,
    )
    harness.add_decision(
        new_clusters[0], people[2], status=ASSIGNMENT_STATUS_REJECTED,
        created_at=_NEW_GEN_TIME,
    )
    harness.add_decision(
        new_clusters[1], None, status=ASSIGNMENT_STATUS_UNASSIGNED,
        created_at=_NEW_GEN_TIME,
    )

    roster_total = len(harness.repos.people.list_all())
    stats = harness.service.stats(run.id, roster_total=roster_total)

    oracle = _oracle(harness, run.id, roster_total)
    assert stats is not None
    assert stats.cluster_run_id == oracle["anchor_id"] == new_gen.id
    assert stats.anchor_created_at == _NEW_GEN_TIME  # 锚点取最新代际
    assert stats.photo_count == oracle["photo_count"] == 2  # o1/o2 同照片去重
    assert stats.face_count == oracle["face_count"] == 3
    assert stats.matched_person_count == len(oracle["matched"]) == 1
    assert stats.unmatched_person_count == oracle["unmatched"] == 2
    # 历史代际决策不并入：张三在旧代际的 confirmed 不影响本口径之外的人。
    assert oracle["matched"] == {people[0].id}


def test_active_statuses_count_rejected_and_unassigned_do_not(
    harness: Harness,
) -> None:
    """active 三状态（suggested/confirmed/auto_confirmed）计数；终态不计。"""
    zhang = harness.add_person("张三")
    li = harness.add_person("李四")
    wang = harness.add_person("王五")
    run, photos = harness.add_run(photo_count=3)
    o1 = harness.add_observation(run, photos[0], 0)
    o2 = harness.add_observation(run, photos[1], 0)
    o3 = harness.add_observation(run, photos[2], 0)
    generation, clusters = harness.add_generation(run, [[o1], [o2], [o3]], _NEW_GEN_TIME)
    harness.add_decision(
        clusters[0], zhang, status=ASSIGNMENT_STATUS_CONFIRMED, created_at=_NEW_GEN_TIME,
    )
    harness.add_decision(
        clusters[1], li, status=ASSIGNMENT_STATUS_AUTO_CONFIRMED,
        source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM, created_at=_NEW_GEN_TIME,
    )
    harness.add_decision(
        clusters[2], wang, status=ASSIGNMENT_STATUS_REJECTED, created_at=_NEW_GEN_TIME,
    )

    roster_total = 3
    stats = harness.service.stats(run.id, roster_total=roster_total)

    assert stats is not None
    assert stats.matched_person_count == 2  # 张三 + 李四（auto_confirmed 也是当前有效）
    assert stats.unmatched_person_count == 1  # 王五只有 rejected，属未匹配
    assert harness.service.matched_person_ids(run.id) == {zhang.id, li.id}


def test_suggested_decisions_count_as_matched(harness: Harness) -> None:
    """D2-A 口径：suggested 属当前有效决策，涉及人物计入已匹配。"""
    zhang = harness.add_person("张三")
    run, photos = harness.add_run(photo_count=1)
    observation = harness.add_observation(run, photos[0], 0)
    generation, clusters = harness.add_generation(run, [[observation]], _NEW_GEN_TIME)
    harness.add_decision(
        clusters[0], zhang, status=ASSIGNMENT_STATUS_SUGGESTED,
        source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION, created_at=_NEW_GEN_TIME,
    )

    stats = harness.service.stats(run.id, roster_total=1)

    assert stats is not None
    assert stats.matched_person_count == 1
    assert stats.unmatched_person_count == 0


def test_anchor_is_newest_generation_not_first_created(harness: Harness) -> None:
    """锚点 = list_cluster_runs（newest-first）首位，与创建顺序无关。"""
    run, photos = harness.add_run(photo_count=1)
    observation = harness.add_observation(run, photos[0], 0)
    old_gen, _ = harness.add_generation(run, [[observation]], _OLD_GEN_TIME)
    new_gen, _ = harness.add_generation(run, [[observation]], _NEW_GEN_TIME)
    assert old_gen.created_at < new_gen.created_at

    anchor = harness.service.anchor_generation(run.id)

    assert anchor is not None
    assert anchor.id == new_gen.id


def test_matched_person_ids_track_each_generation(harness: Harness) -> None:
    """D3-A：matched_person_ids 只反映锚点（最新代际）的 active 决策。"""
    zhang = harness.add_person("张三")
    li = harness.add_person("李四")
    run, photos = harness.add_run(photo_count=2)
    o1 = harness.add_observation(run, photos[0], 0)
    o2 = harness.add_observation(run, photos[1], 0)
    old_gen, old_clusters = harness.add_generation(run, [[o1], [o2]], _OLD_GEN_TIME)
    harness.add_decision(
        old_clusters[0], zhang, status=ASSIGNMENT_STATUS_CONFIRMED, created_at=_OLD_GEN_TIME,
    )
    harness.add_decision(
        old_clusters[1], li, status=ASSIGNMENT_STATUS_CONFIRMED, created_at=_OLD_GEN_TIME,
    )
    assert harness.service.matched_person_ids(run.id) == {zhang.id, li.id}

    # 只重跑一次聚类产生新代际（无任何决策）→ 锚点切换，matched 清空。
    harness.add_generation(run, [[o1]], _NEW_GEN_TIME)
    assert harness.service.matched_person_ids(run.id) == set()
    stats = harness.service.stats(run.id, roster_total=2)
    assert stats is not None
    assert stats.matched_person_count == 0
    assert stats.unmatched_person_count == 2


def test_empty_states_return_none_or_empty(harness: Harness) -> None:
    """无代际 / 无 run → stats 为 None、matched 为空集（面板空态依据）。"""
    run, photos = harness.add_run(photo_count=1)
    harness.add_observation(run, photos[0], 0)

    # 识别运行存在但尚无聚类代际。
    assert harness.service.anchor_generation(run.id) is None
    assert harness.service.stats(run.id, roster_total=5) is None
    assert harness.service.matched_person_ids(run.id) == set()

    # 完全无 run：任意 id 查不到任何代际。
    stray_id = uuid4()
    assert harness.service.anchor_generation(stray_id) is None
    assert harness.service.stats(stray_id, roster_total=5) is None
    assert harness.service.matched_person_ids(stray_id) == set()


def test_unmatched_never_renders_negative(harness: Harness) -> None:
    """防御：名单总数小于已匹配数（异常数据）时未匹配数不为负。"""
    zhang = harness.add_person("张三")
    run, photos = harness.add_run(photo_count=1)
    observation = harness.add_observation(run, photos[0], 0)
    generation, clusters = harness.add_generation(run, [[observation]], _NEW_GEN_TIME)
    harness.add_decision(
        clusters[0], zhang, status=ASSIGNMENT_STATUS_CONFIRMED, created_at=_NEW_GEN_TIME,
    )

    stats = harness.service.stats(run.id, roster_total=0)

    assert stats is not None
    assert stats.matched_person_count == 1
    assert stats.unmatched_person_count == 0  # max(0, 0-1)
