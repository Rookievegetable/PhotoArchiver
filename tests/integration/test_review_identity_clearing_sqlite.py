"""LOGIC-01 — 无身份人工批准必须清除 matcher 猜测身份（真实 SQLite 集成测试).

契约（``ReviewRecognitionService`` docstring / 009 迁移）：不带身份批准的落点
是「匿名孤儿」态——``person_id``/``assignment_id`` 均 NULL、不可归档、不被
reconcile 消费。matcher 为审核预览候选合法写入的猜测 ``person_id`` 不得在该
路径下残留为人工裁决。

全部使用 tmp_path 隔离数据库；不触碰生产库。
"""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from photo_archiver.application.services import ReviewRecognitionService
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.services.identity_decision_service import (
    IdentityDecisionService,
)
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
)
from photo_archiver.domain import (
    FaceBox,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceEmbedding,
    FaceObservation,
    MatchStatus,
    Person,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionResult,
    RecognitionRun,
)
from photo_archiver.infrastructure import SQLiteUnitOfWork

_BASE = datetime(2026, 1, 1, 8, 0, 0)


class _World:
    """真实 SQLite 世界：persons + run/photo + recognition 行（按需含聚类）。"""

    def __init__(self, tmp_path: Path):
        self.repos = build_sqlite_repositories(tmp_path / "logic01.sqlite3")
        self.provider = self.repos._connection_provider
        self.uow = SQLiteUnitOfWork(self.provider)
        run = RecognitionRun(parameters={})
        self.repos.recognition_runs.add_run(run)
        self.run = run
        self.reconciler = ProjectionReconciler(
            recognition_repository=self.repos.recognition,
            assignment_repository=self.repos.cluster_assignments,
            cluster_repository=self.repos.face_clusters,
            observation_repository=self.repos.face_observations,
        )
        self.identity_decisions = IdentityDecisionService(
            recognition_repository=self.repos.recognition,
            assignment_repository=self.repos.cluster_assignments,
            cluster_repository=self.repos.face_clusters,
            observation_repository=self.repos.face_observations,
            person_repository=self.repos.people,
            sample_repository=self.repos.person_face_samples,
            reconciler=self.reconciler,
            transaction_runner=self.provider.run_immediate,
        )
        self.service = ReviewRecognitionService(
            self.repos.recognition,
            unit_of_work=self.uow,
            identity_decision_service=self.identity_decisions,
        )

    def add_person(self, name: str, roster_order: int) -> Person:
        person = Person(name=name, roster_order=roster_order)
        self.repos.people.add(person)
        return person

    def add_photo(self):
        path = Path(self.provider.database_path).parent / (
            f"photo_{uuid4().hex[:8]}.jpg"
        )
        photo = Photo(path=PhotoPath(path, PhotoPathBase.ABSOLUTE), captured_at=_BASE)
        self.repos.photos.add(photo)
        return photo

    def add_pending_result(self, photo, guessed_person_id):
        """matcher 风格的 pending 行：携带猜测身份（审核预览候选功能）。"""
        result = RecognitionResult(
            photo_id=photo.id, confidence=0.42, person_id=guessed_person_id,
        )
        self.repos.recognition.add(result)
        return result

    def add_clustered_observation(self, photo):
        """一张脸入一个簇（最新代际唯一锚点，供带身份批准走决策链）。"""
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
        return cluster


def test_approve_without_identity_clears_guessed_identity_in_sqlite(tmp_path):
    """无身份批准后：DB 行 person_id IS NULL、assignment_id IS NULL、不可归档。"""
    world = _World(tmp_path)
    person = world.add_person("人员甲", 1)
    photo = world.add_photo()
    result = world.add_pending_result(photo, guessed_person_id=person.id)

    refreshed = world.service.approve(result.id)

    assert refreshed is not None
    row = world.repos.recognition.find_by_id(result.id)
    assert row.status is MatchStatus.APPROVED
    # 数据库最终状态：猜测身份被清除，落点为匿名孤儿态（LOGIC-01 契约）。
    assert row.person_id is None
    assert row.assignment_id is None
    # 归档资格：list_approved_by_person（归档口径 person_id+approved）不得命中。
    assert world.repos.recognition.list_approved_by_person(person.id) == []


def test_approve_with_identity_via_decision_chain_unchanged(tmp_path):
    """带身份批准走 S1-F 决策链：投影行 approved+assignment_id，身份归属可归档（回归）。

    决策链既有语义：投影是 reconciler 物化的行（find_projection/create_projection），
    原.pending 占位行的处置由 test_s1f_review_identity_chain 覆盖——本测试只
    断言带身份批准的返回聚合与归档资格不受 R0-A 改动影响。
    """
    world = _World(tmp_path)
    person = world.add_person("人员乙", 1)
    photo = world.add_photo()
    world.add_clustered_observation(photo)
    result = world.add_pending_result(photo, guessed_person_id=person.id)

    refreshed = world.service.approve(result.id, person_id=person.id)

    assert refreshed is not None
    assert refreshed.status is MatchStatus.APPROVED
    assert refreshed.person_id == person.id
    assert refreshed.assignment_id is not None
    approved = world.repos.recognition.list_approved_by_person(person.id)
    assert refreshed.id in [r.id for r in approved]


def test_reject_keeps_guessed_identity_untouched_in_sqlite(tmp_path):
    """reject 保持既有语义：身份列不被触碰（UNSET 缺省，非清除）。"""
    world = _World(tmp_path)
    person = world.add_person("人员丙", 1)
    photo = world.add_photo()
    result = world.add_pending_result(photo, guessed_person_id=person.id)

    refreshed = world.service.reject(result.id)

    assert refreshed is not None
    row = world.repos.recognition.find_by_id(result.id)
    assert row.status is MatchStatus.REJECTED
    assert row.person_id == person.id
