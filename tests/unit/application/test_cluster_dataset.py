"""cluster_dataset resolver tests — 全库最新特征数据集（任务书 §3 A2/D5）.

覆盖：library 口径按"拥有观测的最新运行"归属照片（not_processed 不抢占）、
同照片多版本观测去重、成员快照与观测同源、outcome 汇总取最新一次尝试、
single_run 口径与历史行为逐字段一致。
"""

from uuid import uuid4

from photo_archiver.application.commands.cluster_faces import (
    DATASET_LIBRARY,
    DATASET_SINGLE_RUN,
)
from photo_archiver.application.services.cluster_dataset import (
    is_library_dataset,
    observations_for,
    outcome_summary_for,
    snapshots_for,
)
from photo_archiver.domain import (
    FaceBox,
    FaceEmbedding,
    FaceObservation,
    FaceClusterRun,
    RunPhotoSnapshot,
)


class _FakeRunRepository:
    def __init__(self):
        self._runs: list = []
        self._photos: dict = {}

    def add_run(self, run):
        self._runs.insert(0, run)  # newest first

    def add_run_photos(self, run_id, snapshots):
        self._photos.setdefault(run_id, []).extend(snapshots)

    def list_runs(self):
        return list(self._runs)

    def list_run_photos(self, run_id):
        return list(self._photos.get(run_id, []))


class _FakeObservationRepository:
    def __init__(self):
        self._by_run: dict = {}

    def add(self, run_id, observations):
        self._by_run.setdefault(run_id, []).extend(observations)

    def list_by_run(self, run_id):
        return list(self._by_run.get(run_id, []))


class _RunStub:
    def __init__(self, parameters=None):
        self.id = uuid4()
        self.parameters = parameters or {}


def _cluster_run(dataset=None) -> FaceClusterRun:
    parameters = {"algorithm_version": "v1"}
    if dataset is not None:
        parameters["dataset"] = dataset
    return FaceClusterRun(
        recognition_run_id=uuid4(), algorithm_version="v1", parameters=parameters,
    )


def _observation(run_id, photo_id, face_index=0, angle=0.0) -> FaceObservation:
    return FaceObservation(
        run_id=run_id, photo_id=photo_id, face_index=face_index,
        photo_face_count=face_index + 1, det_score=0.9,
        box=FaceBox(0, 0, 10, 10), embedding=FaceEmbedding(vector=(angle, 1.0)),
        scope_verdict="in_selected_scope", quality_score=0.9,
    )


def _snapshot(photo_id, path, outcome="faces") -> RunPhotoSnapshot:
    return RunPhotoSnapshot(uuid4(), photo_id, path, None, photo_outcome=outcome)


def test_library_mode_dedupes_by_photo_latest_run_wins():
    runs = _FakeRunRepository()
    observations = _FakeObservationRepository()
    old_run, new_run = _RunStub(), _RunStub()
    runs.add_run(old_run)   # 先插入 → list_runs 中排后（更旧）
    runs.add_run(new_run)
    photo = uuid4()
    observations.add(old_run.id, [_observation(old_run.id, photo, angle=1.0)])
    observations.add(new_run.id, [_observation(new_run.id, photo, angle=2.0)])

    result = observations_for(_cluster_run(DATASET_LIBRARY), runs, observations)

    assert len(result) == 1
    assert list(result.values())[0].embedding.vector == (2.0, 1.0)


def test_library_mode_ownership_by_observation_presence_not_run_photos():
    """未产出观测的运行（取消/not_processed）不抢占既有有效特征。"""
    runs = _FakeRunRepository()
    observations = _FakeObservationRepository()
    feature_run, cancelled_run = _RunStub(), _RunStub()
    runs.add_run(feature_run)
    runs.add_run(cancelled_run)  # 更新，但无观测
    photo = uuid4()
    observations.add(feature_run.id, [_observation(feature_run.id, photo)])
    runs.add_run_photos(cancelled_run.id, [_snapshot(photo, "photos/p.jpg")])

    result = observations_for(_cluster_run(DATASET_LIBRARY), runs, observations)

    assert len(result) == 1
    assert list(result.values())[0].run_id == feature_run.id


def test_single_run_mode_reads_anchor_only():
    runs = _FakeRunRepository()
    observations = _FakeObservationRepository()
    anchor, other = _RunStub(), _RunStub()
    runs.add_run(other)
    runs.add_run(anchor)
    photo_a, photo_b = uuid4(), uuid4()
    observations.add(anchor.id, [_observation(anchor.id, photo_a)])
    observations.add(other.id, [_observation(other.id, photo_b)])

    cluster_run = _cluster_run(DATASET_SINGLE_RUN)
    cluster_run.recognition_run_id = anchor.id

    result = observations_for(cluster_run, runs, observations)

    assert {o.run_id for o in result.values()} == {anchor.id}
    assert is_library_dataset(cluster_run) is False


def test_library_mode_snapshots_follow_the_owning_run():
    runs = _FakeRunRepository()
    observations = _FakeObservationRepository()
    old_run, new_run = _RunStub(), _RunStub()
    runs.add_run(old_run)
    runs.add_run(new_run)
    photo = uuid4()
    observations.add(old_run.id, [_observation(old_run.id, photo)])
    observations.add(new_run.id, [_observation(new_run.id, photo)])
    runs.add_run_photos(old_run.id, [_snapshot(photo, "photos/old.jpg")])
    runs.add_run_photos(new_run.id, [_snapshot(photo, "photos/new.jpg")])

    result = snapshots_for(_cluster_run(DATASET_LIBRARY), runs, observations)

    assert result[photo].raw_path == "photos/new.jpg"


def test_library_mode_snapshot_falls_back_to_latest_attempt():
    """归属运行缺快照行（防御路径）时退回最新一次尝试的快照。"""
    runs = _FakeRunRepository()
    observations = _FakeObservationRepository()
    feature_run = _RunStub()
    runs.add_run(feature_run)
    photo = uuid4()
    observations.add(feature_run.id, [_observation(feature_run.id, photo)])
    # 观测在 feature_run，但快照行记在另一运行（异常数据）。
    other = _RunStub()
    runs.add_run(other)
    runs.add_run_photos(other.id, [_snapshot(photo, "photos/fallback.jpg")])

    result = snapshots_for(_cluster_run(DATASET_LIBRARY), runs, observations)

    assert result[photo].raw_path == "photos/fallback.jpg"


def test_outcome_summary_library_counts_latest_attempt():
    runs = _FakeRunRepository()
    photo = uuid4()
    old_run, new_run = _RunStub(), _RunStub()
    runs.add_run(old_run)
    runs.add_run(new_run)
    runs.add_run_photos(old_run.id, [_snapshot(photo, "photos/p.jpg", outcome="faces")])
    runs.add_run_photos(new_run.id, [_snapshot(photo, "photos/p.jpg", outcome="unreadable")])

    summary = outcome_summary_for(_cluster_run(DATASET_LIBRARY), runs)

    # 最新一次尝试如实计数（unreadable），不并入历史成功。
    assert summary["total"] == 1
    assert summary["unreadable"] == 1
    assert summary["faces"] == 0


def test_outcome_summary_single_run_counts_anchor_rows():
    runs = _FakeRunRepository()
    anchor = _RunStub()
    runs.add_run(anchor)
    runs.add_run_photos(anchor.id, [
        _snapshot(uuid4(), "photos/a.jpg", outcome="faces"),
        _snapshot(uuid4(), "photos/b.jpg", outcome=None),
    ])

    cluster_run = _cluster_run(DATASET_SINGLE_RUN)
    cluster_run.recognition_run_id = anchor.id
    summary = outcome_summary_for(cluster_run, runs)

    assert summary["total"] == 2
    assert summary["faces"] == 1
    assert summary["unknown"] == 1


def test_missing_dataset_parameter_defaults_to_single_run():
    cluster_run = _cluster_run(None)
    assert cluster_run.parameters.get("dataset") is None
    assert is_library_dataset(cluster_run) is False
