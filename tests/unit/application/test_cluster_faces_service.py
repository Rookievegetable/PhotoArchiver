"""ClusterFacesService tests — Stage D 聚类编排与可追溯性.

用真实 InMemory 仓储 + 真实 numpy kernel（确定性）覆盖：完整追溯链
（ClusterRun → RecognitionRun；Member → Observation）、范围过滤与
excluded_count、rerun 新代际不覆盖、空输入、取消（算法期）、失败隔离、
参数快照、§D-3 排序键（中文路径、无时间排末）、粗粒度进度。
"""

import math
from datetime import datetime, timedelta, timezone
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
    assert rows[0].sort_key.startswith("2026-01-01T00:00:00.000000|photos/早.jpg")
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


def test_same_instant_earliest_time_orders_by_path_key():
    """§D-3 同刻决胜：两簇最早时间相等时按路径键字典序决定位次。

    观测插入顺序 b 先 a 后（与路径序 a < b 相反）；无论内部确定性序
    （det_score/bbox/id 兜底）产生的创建序如何，同刻簇的 ordinal 必须
    由路径键决定——a 簇在前。
    """
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("b_first", "photos/b.jpg", datetime(2026, 1, 1, 8, 0, 0))
    harness.add_photo("a_second", "photos/a.jpg", datetime(2026, 1, 1, 8, 0, 0))
    harness.add_observation("b_first", 0, 0.0)
    harness.add_observation("a_second", 0, 120.0)  # 正交嵌入 → 两个独立簇

    cluster_run = harness.service.execute(StartClusteringRunCommand(run.id))

    rows = harness.clusters.list_clusters(cluster_run.id)
    assert len(rows) == 2
    assert all(row.first_captured_at == datetime(2026, 1, 1, 8, 0, 0) for row in rows)
    assert rows[0].sort_key.startswith("2026-01-01T08:00:00.000000|photos/a.jpg|")
    assert rows[1].sort_key.startswith("2026-01-01T08:00:00.000000|photos/b.jpg|")


def test_second_precision_orders_before_microsecond_same_wall_clock():
    """秒级 EXIF 形态与微秒 mtime 形态同 wall-clock 组合按时间值保序。

    路径序 a < b 与时间序 b(整秒) < a(+0.5s) 刻意相反：位次必须由时间值
    决定、不得被路径序掩盖（保序回归锁定；纯 naive 下文本序与时间序本就
    一致——P2-O-2 界定，本用例非新旧实现判别器）。
    """
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("micro_a", "photos/a.jpg", datetime(2026, 1, 1, 8, 0, 0, 500000))
    harness.add_photo("second_b", "photos/b.jpg", datetime(2026, 1, 1, 8, 0, 0))
    harness.add_observation("micro_a", 0, 0.0)
    harness.add_observation("second_b", 0, 120.0)

    cluster_run = harness.service.execute(StartClusteringRunCommand(run.id))

    rows = harness.clusters.list_clusters(cluster_run.id)
    assert len(rows) == 2
    assert rows[0].first_captured_at == datetime(2026, 1, 1, 8, 0, 0)
    assert rows[0].sort_key.startswith("2026-01-01T08:00:00.000000|photos/b.jpg|")
    assert rows[1].first_captured_at == datetime(2026, 1, 1, 8, 0, 0, 500000)
    assert rows[1].sort_key.startswith("2026-01-01T08:00:00.500000|photos/a.jpg|")


def test_mixed_naive_aware_same_cluster_fails_run_closed():
    """同簇 naive/aware 混型时间 → datetime 值比较抛 TypeError → run=failed
    且零 Cluster/Member 落库（fail-closed 契约保护）。

    保证范围仅限同簇内实际发生混型比较；簇间各自同型、簇间异型的极端
    输入不在本测试与实现保证范围（P2 修订版统一表述）。
    """
    # 前置校验轮（P2 复审 N-1）：同构造双 naive 确认两照片聚为单一双成员簇。
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("p1", "photos/p1.jpg", datetime(2026, 1, 1))
    harness.add_photo("p2", "photos/p2.jpg", datetime(2026, 1, 3))
    harness.add_observation("p1", 0, 0.0)
    harness.add_observation("p2", 0, 8.0)  # 同人：相似嵌入跨照片成簇（:279 先例同构造）
    pre = harness.service.execute(StartClusteringRunCommand(run.id))
    assert pre.status == "completed"
    pre_rows = harness.clusters.list_clusters(pre.id)
    assert len(pre_rows) == 1 and pre_rows[0].member_count == 2

    # 正式轮：同一构造，一 naive 一 aware → 混型比较失败且零落库。
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo("p1", "photos/p1.jpg", datetime(2026, 1, 2))
    harness.add_photo("p2", "photos/p2.jpg", datetime(2026, 1, 2, tzinfo=timezone.utc))
    harness.add_observation("p1", 0, 0.0)
    harness.add_observation("p2", 0, 8.0)

    with pytest.raises(TypeError):
        harness.service.execute(StartClusteringRunCommand(run.id))

    failed = harness.clusters.list_cluster_runs(run.id)[0]
    assert failed.status == "failed"
    assert harness.clusters.list_clusters(failed.id) == []
    assert harness.clusters.list_members(failed.id) == []


def test_cross_offset_aware_clusters_order_by_absolute_time():
    """T9：跨 UTC 偏移的 aware 簇按绝对时间排序（A-min）。

    A=`09:00+08:00`(01:00Z 早)、B=`02:00+00:00`(02:00Z 晚)；路径序 a<b 与
    时间序 A<B 刻意相反——修复前原始偏移文本字典序会把 B 排前（缺陷），
    修复后排序时间文本归一为 UTC，必须按绝对时间序 A 在前。
    """
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo(
        "late_b", "photos/a.jpg",
        datetime(2026, 1, 1, 2, 0, 0, tzinfo=timezone.utc),
    )
    harness.add_photo(
        "early_a", "photos/z.jpg",
        datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone(timedelta(hours=8))),
    )
    harness.add_observation("late_b", 0, 0.0)
    harness.add_observation("early_a", 0, 120.0)  # 正交嵌入 → 两个独立簇

    cluster_run = harness.service.execute(StartClusteringRunCommand(run.id))

    rows = harness.clusters.list_clusters(cluster_run.id)
    assert len(rows) == 2
    assert rows[0].first_captured_at == datetime(
        2026, 1, 1, 9, 0, 0, tzinfo=timezone(timedelta(hours=8)),
    )
    assert rows[0].sort_key.startswith(
        "2026-01-01T01:00:00.000000+00:00|photos/z.jpg|")
    assert rows[1].first_captured_at == datetime(
        2026, 1, 1, 2, 0, 0, tzinfo=timezone.utc)
    assert rows[1].sort_key.startswith(
        "2026-01-01T02:00:00.000000+00:00|photos/a.jpg|")


def test_same_instant_cross_offset_falls_back_to_path_key():
    """T10：同一瞬间不同偏移表述 → 排序时间文本恒等 → 按路径键决胜。

    X=`09:00+08:00`(photos/a.jpg) 与 Y=`01:00+00:00`(photos/b.jpg) 同为
    01:00Z；归一后时间分量相同，X 因路径 a<b 在前；first_captured_at 保留
    各簇原始 datetime（不因排序文本归一被替换为 UTC）。
    """
    harness = _Harness()
    run = harness.add_run()
    harness.add_photo(
        "x", "photos/a.jpg",
        datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone(timedelta(hours=8))),
    )
    harness.add_photo(
        "y", "photos/b.jpg",
        datetime(2026, 1, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    harness.add_observation("x", 0, 0.0)
    harness.add_observation("y", 0, 120.0)

    cluster_run = harness.service.execute(StartClusteringRunCommand(run.id))

    rows = harness.clusters.list_clusters(cluster_run.id)
    assert len(rows) == 2
    assert rows[0].sort_key.startswith(
        "2026-01-01T01:00:00.000000+00:00|photos/a.jpg|")
    assert rows[1].sort_key.startswith(
        "2026-01-01T01:00:00.000000+00:00|photos/b.jpg|")
    assert rows[0].first_captured_at == datetime(
        2026, 1, 1, 9, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    assert rows[1].first_captured_at == datetime(
        2026, 1, 1, 1, 0, 0, tzinfo=timezone.utc)


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
