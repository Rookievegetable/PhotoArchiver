"""ClusterFacesService tests — Stage D 聚类编排与可追溯性.

用真实 InMemory 仓储 + 真实 numpy kernel（确定性）覆盖：完整追溯链
（ClusterRun → RecognitionRun；Member → Observation）、范围过滤与
excluded_count、rerun 新代际不覆盖、空输入、取消（算法期）、失败隔离、
参数快照、§D-3 排序键（中文路径、无时间排末）、粗粒度进度。
"""

import math
from datetime import datetime
from uuid import uuid4

import pytest

from photo_archiver.application import StartClusteringRunCommand
from photo_archiver.application.services import ClusterFacesService
from photo_archiver.domain import (
    FaceBox,
    FaceEmbedding,
    FaceObservation,
    RecognitionRun,
    RunPhotoSnapshot,
    ValidationError,
)
from photo_archiver.infrastructure import (
    InMemoryFaceClusterRepository,
    InMemoryFaceObservationRepository,
    InMemoryRecognitionRunRepository,
    NumpyCosineSimilarityFactory,
)


class _RunRepositoryWithPhotos(InMemoryRecognitionRunRepository):
    """InMemory run repo + run_photos 快照（聚类需要 captured_at / 路径键）。"""

    def __init__(self):
        super().__init__()
        self._run_photos: dict = {}

    def add_run_photos(self, run_id, snapshots):
        self._run_photos.setdefault(run_id, []).extend(snapshots)

    def list_run_photos(self, run_id):
        return list(self._run_photos.get(run_id, []))


class _Harness:
    """聚类服务测试装置：真实 InMemory 仓储 + numpy kernel。"""

    def __init__(self, reporter=None):
        self.runs = _RunRepositoryWithPhotos()
        self.observations = InMemoryFaceObservationRepository()
        self.clusters = InMemoryFaceClusterRepository()
        self.service = ClusterFacesService(
            self.runs, self.observations, self.clusters,
            NumpyCosineSimilarityFactory(), progress_reporter=reporter,
        )
        self._photos: dict[str, object] = {}

    def add_run(self) -> object:
        run = RecognitionRun(parameters={})
        self.runs.add_run(run)
        return run

    def add_photo(self, key: str, path: str, captured_at=None) -> None:
        photo_id = uuid4()
        self._photos[key] = photo_id
        self.runs.add_run_photos(
            self._current_run_id(),
            [RunPhotoSnapshot(self._current_run_id(), photo_id, path, captured_at)],
        )

    def add_observation(self, photo_key: str, face_index: int, angle: float, *,
                        scope: str = "in_selected_scope", quality: float | None = 0.9):
        run_id = self._current_run_id()
        observation = FaceObservation(
            run_id=run_id,
            photo_id=self._photos[photo_key],
            face_index=face_index,
            photo_face_count=face_index + 1,
            det_score=0.9,
            box=FaceBox(face_index, 0, face_index + 10, 10),
            embedding=_embedding(angle),
            scope_verdict=scope,
            quality_score=quality,
        )
        self.observations.add_many([observation])
        return observation

    def _current_run_id(self):
        runs = self.runs.list_runs()
        assert runs, "add_run() must be called before add_photo/add_observation"
        return runs[0].id  # list_runs newest first —— 单 run 场景即当前 run


def _embedding(angle: float) -> FaceEmbedding:
    radians = math.radians(angle)
    return FaceEmbedding((math.cos(radians), math.sin(radians)))


def test_full_flow_clusters_similar_and_dissimilar_faces():
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("a", "photos/a.jpg", datetime(2026, 1, 1))
    harness.add_photo("b", "photos/b.jpg", datetime(2026, 1, 2))
    harness.add_observation("a", 0, 0.0)
    harness.add_observation("b", 0, 10.0)
    harness.add_observation("a", 1, 90.0)

    cluster_run = harness.service.execute(StartClusteringRunCommand(run.id))

    assert cluster_run.status == "completed"
    assert cluster_run.recognition_run_id == run.id
    assert (cluster_run.cluster_count, cluster_run.member_count) == (2, 3)
    assert cluster_run.excluded_count == 0
    rows = harness.clusters.list_clusters(cluster_run.id)
    assert len(rows) == 2
    assert all(row.status == "pending" for row in rows)
    assert [row.ordinal for row in rows] == [0, 1]
    members = harness.clusters.list_members(cluster_run.id)
    assert len(members) == 3
    assert all(member.source == "auto" for member in members)
    # 追溯链：member → observation（同 run）→ cluster_run → recognition run。
    observation_ids = {observation.id for observation in harness.observations.list_by_run(run.id)}
    assert {member.observation_id for member in members} == observation_ids


def test_out_of_scope_observations_excluded_and_counted():
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("a", "photos/a.jpg")
    harness.add_observation("a", 0, 0.0)
    harness.add_observation("a", 1, 10.0, scope="out_of_selected_scope")

    cluster_run = harness.service.execute(StartClusteringRunCommand(run.id))

    assert cluster_run.excluded_count == 1
    assert cluster_run.member_count == 1
    assert len(harness.clusters.list_members(cluster_run.id)) == 1


def test_no_observations_completes_with_zero_clusters():
    harness = _Harness()
    run = harness.add_run()

    cluster_run = harness.service.execute(StartClusteringRunCommand(run.id))

    assert cluster_run.status == "completed"
    assert (cluster_run.cluster_count, cluster_run.member_count) == (0, 0)
    assert harness.clusters.list_clusters(cluster_run.id) == []


def test_missing_recognition_run_raises_validation_error():
    harness = _Harness()

    with pytest.raises(ValidationError, match="does not exist"):
        harness.service.execute(StartClusteringRunCommand(uuid4()))


def test_rerun_creates_new_generation_and_keeps_history():
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("a", "photos/a.jpg")
    harness.add_observation("a", 0, 0.0)
    harness.add_observation("a", 1, 10.0)
    command = StartClusteringRunCommand(run.id)

    first = harness.service.execute(command)
    second = harness.service.execute(command)

    assert first.id != second.id
    assert harness.clusters.list_clusters(first.id)  # 旧代际原样保留
    assert harness.clusters.list_clusters(second.id)
    assert len(harness.clusters.list_cluster_runs(run.id)) == 2


def test_stale_cancel_request_does_not_affect_new_run():
    """execute() 清除陈旧取消请求（对齐 Stage C：新 run 不继承上次取消），
    运行期取消经 should_cancel 钩子生效（见 kernel hook 测试）。"""
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("a", "photos/a.jpg")
    harness.add_observation("a", 0, 0.0)

    harness.service.cancel()  # 上一次任务的陈旧取消请求
    cluster_run = harness.service.execute(StartClusteringRunCommand(run.id))

    assert cluster_run.status == "completed"
    assert harness.clusters.list_clusters(cluster_run.id)


def test_cancel_via_kernel_hook_propagates_to_run():
    """kernel 构建后立即取消 → 算法起点抛 ClusteringCancelled → run 置 cancelled。"""
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("a", "photos/a.jpg")
    harness.add_observation("a", 0, 0.0)
    harness.add_observation("a", 1, 5.0)

    original_build = harness.service._similarity_factory.build  # noqa: SL001

    class _CancellingFactory:
        def build(self, embeddings):
            lookup = original_build(embeddings)
            harness.service.cancel()
            return lookup

    harness.service._similarity_factory = _CancellingFactory()  # noqa: SL001

    cluster_run = harness.service.execute(StartClusteringRunCommand(run.id))

    assert cluster_run.status == "cancelled"
    assert harness.clusters.list_clusters(cluster_run.id) == []


def test_kernel_failure_marks_cluster_run_failed_and_reraises():
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("a", "photos/a.jpg")
    harness.add_observation("a", 0, 0.0)

    class _ExplodingFactory:
        def build(self, embeddings):
            raise RuntimeError("kernel exploded")

    harness.service._similarity_factory = _ExplodingFactory()  # noqa: SL001

    with pytest.raises(RuntimeError, match="kernel exploded"):
        harness.service.execute(StartClusteringRunCommand(run.id))

    failed = harness.clusters.list_cluster_runs(run.id)[0]
    assert failed.status == "failed"
    assert "kernel exploded" in failed.error


def test_parameters_snapshot_records_algorithm_and_thresholds():
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("a", "photos/a.jpg")
    harness.add_observation("a", 0, 0.0)

    cluster_run = harness.service.execute(
        StartClusteringRunCommand(run.id, cluster_sim_threshold=0.6),
    )

    assert cluster_run.parameters["algorithm_version"] == "cosine-centroid-completelink-v1"
    assert cluster_run.parameters["cluster_sim_threshold"] == 0.6
    assert cluster_run.parameters["consistency_threshold"] == 0.4
    assert cluster_run.parameters["low_quality_threshold"] == 0.0
    assert cluster_run.parameters["scope_filter"] == "in_selected_scope"


def test_sort_key_orders_by_captured_at_with_missing_times_last():
    """§D-3：最早非空 captured_at 升序，无时间排末；中文路径作稳定路径键。"""
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("early", "photos/早.jpg", datetime(2026, 1, 1))
    harness.add_photo("late", "photos/晚.jpg", datetime(2026, 3, 1))
    harness.add_photo("none", "photos/无时间.jpg", None)
    harness.add_observation("early", 0, 0.0)
    harness.add_observation("late", 0, 120.0)
    harness.add_observation("none", 0, 240.0)

    cluster_run = harness.service.execute(StartClusteringRunCommand(run.id))

    rows = harness.clusters.list_clusters(cluster_run.id)
    assert len(rows) == 3
    assert rows[0].first_captured_at == datetime(2026, 1, 1)
    assert rows[1].first_captured_at == datetime(2026, 3, 1)
    assert rows[2].first_captured_at is None  # 无时间组排末
    assert rows[0].sort_key.startswith("2026-01-01T00:00:00|photos/早.jpg")
    assert rows[2].sort_key.startswith("~")


def test_earliest_captured_at_crosses_photos_within_cluster():
    """同人跨照片成簇时 first_captured_at 取成员中最早的非空拍摄时间。"""
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("late_a", "photos/a.jpg", datetime(2026, 5, 1))
    harness.add_photo("early_b", "photos/b.jpg", datetime(2026, 2, 1))
    harness.add_observation("late_a", 0, 0.0)
    harness.add_observation("early_b", 0, 8.0)  # 同人：相似嵌入跨照片成簇

    cluster_run = harness.service.execute(StartClusteringRunCommand(run.id))

    rows = harness.clusters.list_clusters(cluster_run.id)
    assert len(rows) == 1
    assert rows[0].first_captured_at == datetime(2026, 2, 1)


def test_progress_reports_coarse_stages():
    events: list[tuple[int, int, str]] = []

    class _Reporter:
        def report(self, current, total, message):
            events.append((current, total, message))

    harness = _Harness(reporter=_Reporter())
    run = harness.add_run()
    harness.add_photo("a", "photos/a.jpg")
    harness.add_observation("a", 0, 0.0)
    harness.add_observation("a", 1, 5.0)
    harness.service.execute(StartClusteringRunCommand(run.id))

    assert events[-1] == (2, 2, "Persisting clusters")
    assert any("Clustering face observations" in message for _, _, message in events)


def test_every_participating_observation_assigned_exactly_once():
    """P2-b 对抗性：同一 Observation 在同一 ClusterRun 中至多归属一个
    Cluster，且全部范围内观测都被覆盖（不重不漏）。

    混合数据：三人各跨照片 + 一张范围外观测，多簇多成员场景下逐条校验。
    """
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("a", "photos/a.jpg", datetime(2026, 1, 1))
    harness.add_photo("b", "photos/b.jpg", datetime(2026, 1, 2))
    harness.add_photo("c", "photos/c.jpg", datetime(2026, 1, 3))
    # 人1：0°/6°/12°（跨三张照片），人2：90°/96°（跨两张），人3：180°（单张）。
    harness.add_observation("a", 0, 0.0)
    harness.add_observation("b", 0, 6.0)
    harness.add_observation("c", 0, 12.0)
    harness.add_observation("a", 1, 90.0)
    harness.add_observation("b", 1, 96.0)
    harness.add_observation("c", 1, 180.0)
    harness.add_observation("a", 2, 270.0, scope="out_of_selected_scope")  # 不参与

    cluster_run = harness.service.execute(StartClusteringRunCommand(run.id))

    members = harness.clusters.list_members(cluster_run.id)
    member_observation_ids = [member.observation_id for member in members]
    assert len(member_observation_ids) == len(set(member_observation_ids)), (
        "同一 Observation 被归属到多个 Cluster"
    )
    participating_ids = {
        observation.id for observation in harness.observations.list_by_run(run.id)
        if observation.scope_verdict == "in_selected_scope"
    }
    assert set(member_observation_ids) == participating_ids  # 不重不漏
    # 每条成员的 cluster 都属于本 cluster run（追溯闭合）。
    cluster_ids = {cluster.id for cluster in harness.clusters.list_clusters(cluster_run.id)}
    assert all(member.cluster_id in cluster_ids for member in members)
