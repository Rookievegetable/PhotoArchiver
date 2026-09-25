"""ClusterResultsService tests — D-4 只读结果装配（不重算聚类）."""

from datetime import datetime
from uuid import uuid4

from photo_archiver.application.services import (
    ClusterResultsService,
    ListRecognitionRunsService,
)
from photo_archiver.domain import (
    FaceBox,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceEmbedding,
    FaceObservation,
    RecognitionRun,
    RunPhotoSnapshot,
)
from photo_archiver.infrastructure import (
    InMemoryFaceClusterRepository,
    InMemoryFaceObservationRepository,
    InMemoryRecognitionRunRepository,
)


class _RunRepoWithPhotos(InMemoryRecognitionRunRepository):
    def __init__(self):
        super().__init__()
        self._run_photos: dict = {}

    def add_run_photos(self, run_id, snapshots):
        self._run_photos.setdefault(run_id, []).extend(snapshots)

    def list_run_photos(self, run_id):
        return list(self._run_photos.get(run_id, []))


class _Harness:
    """Seed persisted cluster data end-to-end via the real repositories."""

    def __init__(self):
        self.runs = _RunRepoWithPhotos()
        self.observations = InMemoryFaceObservationRepository()
        self.clusters = InMemoryFaceClusterRepository()
        self.service = ClusterResultsService(
            self.runs, self.observations, self.clusters,
        )
        self.runs_service = ListRecognitionRunsService(self.runs)

    def seed_observation(self, run_id, photo_id, index, angle, quality=0.9):
        import math
        radians = math.radians(angle)
        observation = FaceObservation(
            run_id=run_id,
            photo_id=photo_id,
            face_index=index,
            photo_face_count=index + 1,
            det_score=0.9,
            box=FaceBox(index, 0, index + 10, 10),
            embedding=FaceEmbedding((math.cos(radians), math.sin(radians))),
            scope_verdict="in_selected_scope",
            quality_score=quality,
        )
        self.observations.add_many([observation])
        return observation


def test_list_recognition_runs_returns_runs_newest_first():
    harness = _Harness()
    ids = []
    for index in range(3):
        run = RecognitionRun(parameters={}, created_at=datetime(2026, 1, index + 1))
        harness.runs.add_run(run)
        ids.append(run.id)

    runs = harness.runs_service.execute()

    assert [run.id for run in runs] == ids[::-1]  # newest first


def test_results_assembles_members_from_persisted_data():
    harness = _Harness()
    run = RecognitionRun(parameters={})
    harness.runs.add_run(run)
    photo_a, photo_b = uuid4(), uuid4()
    harness.runs.add_run_photos(run.id, [
        RunPhotoSnapshot(run.id, photo_a, "photos/合影.jpg", datetime(2026, 1, 1)),
        RunPhotoSnapshot(run.id, photo_b, "photos/单人.jpg", datetime(2026, 2, 1)),
    ])
    o1 = harness.seed_observation(run.id, photo_a, 0, 0.0)
    o2 = harness.seed_observation(run.id, photo_b, 0, 5.0)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="v1")
    harness.clusters.add_cluster_run(cluster_run)
    cluster = FaceCluster(
        cluster_run_id=cluster_run.id, run_id=run.id, ordinal=0,
        member_count=2, sort_key="k", first_captured_at=datetime(2026, 1, 1),
    )
    harness.clusters.add_clusters([cluster])
    harness.clusters.add_members([
        FaceClusterMember(cluster_id=cluster.id, observation_id=o1.id, confidence=1.0),
        FaceClusterMember(cluster_id=cluster.id, observation_id=o2.id, confidence=0.87),
    ])

    view = harness.service.results(cluster_run.id)

    assert view is not None
    assert view.cluster_run.id == cluster_run.id
    assert len(view.clusters) == 1
    detail = view.clusters[0]
    assert detail.member_count == 2
    assert detail.first_captured_at == datetime(2026, 1, 1)
    # 展示顺序按（照片路径, 脸序号）确定性排序（码点序：单 < 合）。
    by_observation = {member.observation_id: member for member in detail.members}
    member_a, member_b = by_observation[o1.id], by_observation[o2.id]
    assert member_a.photo_path == "photos/合影.jpg"
    assert member_a.photo_id == photo_a
    assert member_a.face_index == 0
    assert member_a.det_score == 0.9
    assert member_a.confidence == 1.0
    assert member_a.captured_at == datetime(2026, 1, 1)
    assert member_b.photo_path == "photos/单人.jpg"
    assert member_b.confidence == 0.87
    assert [m.photo_path for m in detail.members] == [
        "photos/单人.jpg", "photos/合影.jpg",
    ]


def test_results_for_unknown_cluster_run_returns_none():
    harness = _Harness()
    assert harness.service.results(uuid4()) is None


def test_results_empty_generation_has_no_clusters():
    harness = _Harness()
    run = RecognitionRun(parameters={})
    harness.runs.add_run(run)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="v1")
    harness.clusters.add_cluster_run(cluster_run)

    view = harness.service.results(cluster_run.id)

    assert view is not None
    assert view.clusters == ()


def test_member_referencing_missing_observation_is_skipped_defensively():
    """正常流程不会发生（FK 级联同步删成员行）；InMemory 无 FK 故防御性跳过。"""
    harness = _Harness()
    run = RecognitionRun(parameters={})
    harness.runs.add_run(run)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="v1")
    harness.clusters.add_cluster_run(cluster_run)
    cluster = FaceCluster(
        cluster_run_id=cluster_run.id, run_id=run.id, ordinal=0,
        member_count=1, sort_key="k",
    )
    harness.clusters.add_clusters([cluster])
    harness.clusters.add_members([
        FaceClusterMember(cluster_id=cluster.id, observation_id=uuid4()),
    ])

    view = harness.service.results(cluster_run.id)

    assert view is not None
    assert view.clusters[0].members == ()
