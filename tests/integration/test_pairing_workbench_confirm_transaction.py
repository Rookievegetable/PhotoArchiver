"""LOGIC-03/DATA-01 — 终审确认链事务原子性（真实 SQLite 集成测试）.

``PairingWorkbenchService.confirm`` 的读→校验→决策行→样本→投影完整链在单个
BEGIN IMMEDIATE 事务内执行：中途任一写入失败整体回滚（无"已 confirmed 但
样本/投影缺失"半程状态）、busy 冲突整 attempt 重试、并发双确认串行化且无
冗余 confirmed 行。

全部使用 tmp_path 隔离数据库；不触碰生产库。仅覆盖 ``confirm``——
``assign_person``/``reject``/``unassign`` 的事务行为不在本任务范围（Owner 决定）。
"""

import threading
from datetime import datetime
from pathlib import Path

import pytest

from photo_archiver.application.commands.pairing import ConfirmAssignmentCommand
from photo_archiver.application.services import PairingWorkbenchService
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
)
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.domain import (
    FaceBox,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceEmbedding,
    FaceObservation,
    Person,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionRun,
    ValidationError,
)
from photo_archiver.domain.entities.cluster_assignment import (
    ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
    ASSIGNMENT_STATUS_SUGGESTED,
    ClusterPersonAssignment,
)

_BASE = datetime(2026, 1, 1, 8, 0, 0)


class _World:
    """真实 SQLite 世界：person + photo + observation/cluster + suggested 行。"""

    def __init__(self, tmp_path: Path):
        self.repos = build_sqlite_repositories(tmp_path / "confirm_tx.sqlite3")
        self.provider = self.repos._connection_provider
        self.reconciler = ProjectionReconciler(
            recognition_repository=self.repos.recognition,
            assignment_repository=self.repos.cluster_assignments,
            cluster_repository=self.repos.face_clusters,
            observation_repository=self.repos.face_observations,
        )
        self.workbench = PairingWorkbenchService(
            self.repos.cluster_assignments,
            self.repos.face_clusters,
            self.repos.face_observations,
            self.repos.people,
            self.repos.recognition,
            self.repos.person_face_samples,
            reconciler=self.reconciler,
            transaction_runner=self.provider.run_immediate,
        )
        run = RecognitionRun(parameters={})
        self.repos.recognition_runs.add_run(run)
        self.run = run

    def seed_suggested(self):
        """一人一照片一观测一簇 + suggested 决策行；返回 (person, photo, row)。"""
        person = Person(name="人员甲", roster_order=1)
        self.repos.people.add(person)
        path = Path(self.provider.database_path).parent / "photo_a.jpg"
        photo = Photo(path=PhotoPath(path, PhotoPathBase.ABSOLUTE), captured_at=_BASE)
        self.repos.photos.add(photo)
        observation = FaceObservation(
            run_id=self.run.id,
            photo_id=photo.id,
            face_index=0,
            photo_face_count=1,
            det_score=0.9,
            box=FaceBox(0, 0, 10, 10),
            embedding=FaceEmbedding((1.0, 0.0, 0.0)),
            scope_verdict="in_selected_scope",
            quality_score=0.9,
        )
        self.repos.face_observations.add_many([observation])
        cluster_run = FaceClusterRun(
            recognition_run_id=self.run.id, algorithm_version="v1",
        )
        self.repos.face_clusters.add_cluster_run(cluster_run)
        cluster = FaceCluster(
            cluster_run_id=cluster_run.id,
            run_id=self.run.id,
            ordinal=0,
            member_count=1,
            sort_key="k|g00|0000001",
            first_captured_at=_BASE,
        )
        self.repos.face_clusters.add_clusters([cluster])
        self.repos.face_clusters.add_members([
            FaceClusterMember(cluster_id=cluster.id, observation_id=observation.id),
        ])
        row = ClusterPersonAssignment(
            cluster_id=cluster.id,
            person_id=person.id,
            status=ASSIGNMENT_STATUS_SUGGESTED,
            source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
        )
        self.repos.cluster_assignments.add_assignments([row])
        return person, photo, row

    def confirm(self, row):
        return self.workbench.confirm(ConfirmAssignmentCommand(assignment_id=row.id))

    def latest_row(self, row):
        return self.repos.cluster_assignments.get_assignment(row.id)

    def projection_rows(self, person):
        return self.repos.recognition.list_approved_by_person(person.id)

    def sample_rows(self, person):
        return self.repos.person_face_samples.list_by_person(person.id)


def test_confirm_persists_decision_samples_and_projection(tmp_path):
    """正常确认：决策行 confirmed、样本沉淀、投影 APPROVED 全部落库。"""
    world = _World(tmp_path)
    person, _photo, row = world.seed_suggested()

    result = world.confirm(row)

    assert result.status == "confirmed"
    assert result.samples_written == 1
    assert result.compat_results_written == 1
    persisted = world.latest_row(row)
    assert persisted.status == "confirmed"
    assert len(world.sample_rows(person)) == 1
    projections = world.projection_rows(person)
    assert len(projections) == 1
    assert projections[0].assignment_id == row.id


def test_injected_add_samples_failure_rolls_back_whole_confirm(tmp_path):
    """样本沉淀失败：决策行/样本/投影全部回滚，无半程状态。"""
    world = _World(tmp_path)
    person, _photo, row = world.seed_suggested()
    original = world.repos.person_face_samples.add_samples

    def failing_add(rows):
        raise RuntimeError("injected add_samples failure")

    world.repos.person_face_samples.add_samples = failing_add  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="injected"):
        world.confirm(row)
    world.repos.person_face_samples.add_samples = original  # type: ignore[method-assign]

    # 零残留：决策行仍是 suggested、无样本、无投影。
    assert world.latest_row(row).status == "suggested"
    assert world.sample_rows(person) == []
    assert world.projection_rows(person) == []


def test_injected_enable_samples_failure_rolls_back_whole_confirm(tmp_path):
    """样本复活失败：与 add_samples 同样整体回滚。"""
    world = _World(tmp_path)
    person, _photo, row = world.seed_suggested()
    original = world.repos.person_face_samples.enable_samples

    def failing_enable(person_id, observation_ids):
        raise RuntimeError("injected enable_samples failure")

    world.repos.person_face_samples.enable_samples = failing_enable  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="injected"):
        world.confirm(row)
    world.repos.person_face_samples.enable_samples = original  # type: ignore[method-assign]

    assert world.latest_row(row).status == "suggested"
    assert world.sample_rows(person) == []
    assert world.projection_rows(person) == []


def test_retry_after_injected_failure_succeeds(tmp_path):
    """注入解除后重试：整条链完整落库（run_immediate 整 attempt 重试语义）。"""
    world = _World(tmp_path)
    person, _photo, row = world.seed_suggested()
    original = world.repos.person_face_samples.add_samples
    calls = {"count": 0}

    def failing_once(rows):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("injected first-attempt failure")
        return original(rows)

    world.repos.person_face_samples.add_samples = failing_once  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="injected"):
        world.confirm(row)
    world.repos.person_face_samples.add_samples = original  # type: ignore[method-assign]

    result = world.confirm(row)
    assert result.status == "confirmed"
    assert world.latest_row(row).status == "confirmed"
    assert len(world.sample_rows(person)) == 1
    assert len(world.projection_rows(person)) == 1


def test_repeated_confirm_is_rejected_without_extra_rows(tmp_path):
    """重复确认：状态机拒绝二次 confirm，无冗余有效决策行。"""
    world = _World(tmp_path)
    person, _photo, row = world.seed_suggested()
    world.confirm(row)

    with pytest.raises(ValidationError, match="Only suggested assignments"):
        world.confirm(row)

    rows = [
        assignment for assignment in world.repos.cluster_assignments.list_by_cluster(
            row.cluster_id,
        )
        if assignment.status == "confirmed"
    ]
    assert len(rows) == 1
    assert len(world.sample_rows(person)) == 1


def test_concurrent_confirms_have_single_winner(tmp_path):
    """并发双确认（两线程 + BEGIN IMMEDIATE 串行化）：恰一胜者、零冗余。"""
    world = _World(tmp_path)
    person, _photo, row = world.seed_suggested()
    outcomes: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def attempt(name: str) -> None:
        barrier.wait()
        try:
            outcomes[name] = world.confirm(row)
        except Exception as exc:  # noqa: BLE001 - 并发败者的异常类型即被观测行为
            outcomes[name] = exc

    threads = [
        threading.Thread(target=attempt, args=(name,))
        for name in ("first", "second")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    succeeded = [v for v in outcomes.values() if hasattr(v, "status")]
    assert len(succeeded) == 1  # 恰一胜者
    confirmed = [
        assignment for assignment in world.repos.cluster_assignments.list_by_cluster(
            row.cluster_id,
        )
        if assignment.status == "confirmed"
    ]
    assert len(confirmed) == 1  # 无冗余有效决策
    assert len(world.sample_rows(person)) == 1  # UNIQUE 去重，无重复样本
    assert len(world.projection_rows(person)) == 1  # 投影唯一
