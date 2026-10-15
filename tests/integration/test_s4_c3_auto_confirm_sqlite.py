"""S4 C-3 — 位置自动确认服务集成的真实 SQLite 集成测试.

覆盖（§6.2）：整批事务原子性与失败回滚、auto_confirmed 的数据安全边界
（score=NULL、零投影、零样本、零 recognition_results 写入）、重复执行幂等、
D-6 人工决策路径（解除/拒绝/终审）与机器 fail-closed 保护。

全部使用 tmp_path 隔离数据库；不触碰生产库。
"""

from datetime import datetime
from pathlib import Path

import pytest

from photo_archiver.application.commands.pairing import (
    AssignClusterPersonCommand,
    RejectAssignmentCommand,
    StartSuggestPairingsCommand,
    UnassignClusterCommand,
)
from photo_archiver.application.services import PairingWorkbenchService, SuggestPairingsService
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.services.projection_reconciler import ProjectionReconciler
from photo_archiver.domain import (
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
from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR, MACHINE_ACTOR
from photo_archiver.domain.exceptions import ManualDecisionProtectedError
from photo_archiver.domain.services.positional_auto_confirm import (
    ADMISSION_REASON_REJECTED_POSITIONAL_PAIR,
)
from photo_archiver.infrastructure import NumpyCosineSimilarityFactory

_BASE = datetime(2026, 1, 1, 8, 0, 0)


class _World:
    """真实 SQLite 世界：persons + run/photos + observations + 一代 3 簇。"""

    def __init__(self, tmp_path: Path):
        self.repos = build_sqlite_repositories(tmp_path / "c3.sqlite3")
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
        )
        run = RecognitionRun(parameters={})
        self.repos.recognition_runs.add_run(run)
        self.run = run
        self._cluster_run = None
        self._photo_seq = 0

    def add_person(self, name: str, roster_order: int) -> Person:
        person = Person(name=name, roster_order=roster_order)
        self.repos.people.add(person)
        return person

    def add_photo(self, captured: datetime):
        self._photo_seq += 1
        path = Path(self.repos._connection_provider.database_path).parent / (
            f"photo_{self._photo_seq}.jpg"
        )
        from photo_archiver.domain import Photo, PhotoPath, PhotoPathBase

        photo = Photo(path=PhotoPath(path, PhotoPathBase.ABSOLUTE), captured_at=captured)
        self.repos.photos.add(photo)
        self.repos.recognition_runs.add_run_photos(self.run.id, [
            RunPhotoSnapshot(self.run.id, photo.id, str(path), captured),
        ])
        return photo

    def add_cluster(self, sort_key: str, photo, captured: datetime):
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
        if self._cluster_run is None:
            cluster_run = FaceClusterRun(
                recognition_run_id=self.run.id, algorithm_version="v1",
            )
            self.repos.face_clusters.add_cluster_run(cluster_run)
            self._cluster_run = cluster_run
        cluster = FaceCluster(
            cluster_run_id=self._cluster_run.id,
            run_id=self.run.id,
            ordinal=len(self.repos.face_clusters.list_clusters(self._cluster_run.id)),
            member_count=1,
            sort_key=sort_key,
            first_captured_at=captured,
        )
        self.repos.face_clusters.add_clusters([cluster])
        self.repos.face_clusters.add_members([
            FaceClusterMember(cluster_id=cluster.id, observation_id=observation.id),
        ])
        return cluster

    def seed_three_pairs(self):
        """3 簇 × 3 人，时间齐备、无拒绝对；返回 (persons, clusters, photos)。"""
        persons = [self.add_person(f"人员{i}", i + 1) for i in range(3)]
        clusters, photos = [], []
        for i in range(3):
            photo = self.add_photo(_BASE)
            photos.append(photo)
            clusters.append(self.add_cluster(f"k|g{i:02d}|00000{i}", photo,
                                             captured=_BASE))
        return persons, clusters, photos

    def build_suggest(self) -> SuggestPairingsService:
        return SuggestPairingsService(
            self.repos.face_clusters,
            self.repos.face_observations,
            self.repos.people,
            self.repos.cluster_assignments,
            self.repos.person_face_samples,
            NumpyCosineSimilarityFactory(),
            transaction_runner=self.repos._connection_provider.run_immediate,
        )

    def assignment_rows(self):
        return self.repos.cluster_assignments.list_by_cluster_run(
            self._cluster_run.id)

    def photo_of(self, row):
        """该决策簇成员观测所属照片 id（测试辅助）。"""
        members = self.repos.face_clusters.list_members(self._cluster_run.id)
        member = next(m for m in members if m.cluster_id == row.cluster_id)
        observations = {
            o.id: o for o in self.repos.face_observations.list_by_run(self.run.id)
        }
        return observations[member.observation_id].photo_id


# ── 整批落库、数据安全边界与幂等 ────────────────────────────────────────────


def test_admitted_batch_persists_auto_confirmed_with_safe_boundaries(tmp_path):
    world = _World(tmp_path)
    persons, clusters, photos = world.seed_three_pairs()
    summary = world.build_suggest().execute(
        StartSuggestPairingsCommand(world._cluster_run.id))

    assert summary.auto_confirmed == 3
    assert summary.auto_confirm_blocked_reason is None
    rows = world.assignment_rows()
    assert len(rows) == 3
    assert all(r.status == "auto_confirmed" for r in rows)
    assert all(r.source == "ordered_auto_confirm" for r in rows)
    # BD-4：位置配对分数恒 NULL（数据库实值断言）。
    assert all(r.score is None for r in rows)
    # BD-5/D1=A：不沉淀样本、不写 recognition_results（零投影/零归档可见性）。
    assert world.repos.person_face_samples.list_enabled() == []
    assert world.repos.recognition.list_projections() == []
    assert world.repos.recognition.list_all_approved() == []
    for person, cluster, photo in zip(persons, clusters, photos):
        assert world.repos.recognition.find_projection(photo.id, person.id) is None


def test_repeat_execution_is_idempotent(tmp_path):
    world = _World(tmp_path)
    world.seed_three_pairs()
    service = world.build_suggest()
    service.execute(StartSuggestPairingsCommand(world._cluster_run.id))

    second = service.execute(StartSuggestPairingsCommand(world._cluster_run.id))

    assert second.auto_confirmed == 0
    assert len(world.assignment_rows()) == 3


# ── 整批事务与失败回滚 ──────────────────────────────────────────────────────


def test_injected_failure_rolls_back_whole_batch(tmp_path):
    world = _World(tmp_path)
    world.seed_three_pairs()
    service = world.build_suggest()
    repository = world.repos.cluster_assignments
    original = repository.add_assignments

    def failing_add(rows):
        if any(r.status == "auto_confirmed" for r in rows):
            raise RuntimeError("injected mid-batch failure")
        return original(rows)

    repository.add_assignments = failing_add  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="injected"):
        service.execute(StartSuggestPairingsCommand(world._cluster_run.id))
    repository.add_assignments = original

    # 回滚后：本批零残留（auto_confirmed 与 sample_match suggested 均不存在）。
    assert world.assignment_rows() == []

    # 解除注入后重试：整批完整落库。
    summary = service.execute(StartSuggestPairingsCommand(world._cluster_run.id))
    assert summary.auto_confirmed == 3
    assert len(world.assignment_rows()) == 3


# ── D-6 人工决策与机器保护 ──────────────────────────────────────────────────


def test_machine_cannot_revoke_auto_confirmed_but_human_can(tmp_path):
    world = _World(tmp_path)
    world.seed_three_pairs()
    service = world.build_suggest()
    service.execute(StartSuggestPairingsCommand(world._cluster_run.id))
    target = world.assignment_rows()[0]

    with pytest.raises(ManualDecisionProtectedError):
        world.workbench.unassign(
            UnassignClusterCommand(target.cluster_id), actor=MACHINE_ACTOR)

    world.workbench.unassign(
        UnassignClusterCommand(target.cluster_id), actor=HUMAN_ACTOR)
    assert world.repos.cluster_assignments.get_assignment(
        target.id).status == "unassigned"


def test_human_confirm_via_assign_person_triggers_sanctioned_flows(tmp_path):
    """人工终审（assign_person）→ manual confirmed + 样本沉淀 + 投影创建。"""
    world = _World(tmp_path)
    persons, clusters, photos = world.seed_three_pairs()
    service = world.build_suggest()
    service.execute(StartSuggestPairingsCommand(world._cluster_run.id))
    rows = world.assignment_rows()
    target = rows[0]
    person = next(p for p in persons if p.id == target.person_id)
    photo = next(p for p in photos
                 if p.id == world.photo_of(target))

    result = world.workbench.assign_person(
        AssignClusterPersonCommand(cluster_id=target.cluster_id,
                                   person_id=person.id),
        actor=HUMAN_ACTOR)

    assert result.status == "confirmed"
    # 样本沉淀仅发生在人工终审之后（D1=A/BD-5）。
    assert len(world.repos.person_face_samples.list_by_person(person.id)) == 1
    # 投影仅在人工终审后创建（D1=A）——确认即可归档。
    assert world.repos.recognition.find_projection(photo.id, person.id) is not None


def test_human_reject_then_reexecute_keeps_existing_filter(tmp_path):
    world = _World(tmp_path)
    world.seed_three_pairs()
    service = world.build_suggest()
    service.execute(StartSuggestPairingsCommand(world._cluster_run.id))
    target = world.assignment_rows()[1]

    world.workbench.reject(RejectAssignmentCommand(target.id), actor=HUMAN_ACTOR)
    summary = service.execute(StartSuggestPairingsCommand(world._cluster_run.id))

    assert summary.auto_confirm_blocked_reason == (
        ADMISSION_REASON_REJECTED_POSITIONAL_PAIR)
    assert summary.auto_confirmed == 0
