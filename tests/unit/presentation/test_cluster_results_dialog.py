"""ClusterResultsDialog tests — D-4 代际/簇/成员展示与空态."""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from uuid import uuid4

from photo_archiver.application.services import ClusterResultsService
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
from photo_archiver.presentation.views.cluster_results_dialog import ClusterResultsDialog

# 1×1 PNG（真实文件——QIcon 从不存在的路径构造会得到 null icon）。
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082",
)


class _RunRepoWithPhotos(InMemoryRecognitionRunRepository):
    def __init__(self):
        super().__init__()
        self._run_photos: dict = {}

    def add_run_photos(self, run_id, snapshots):
        self._run_photos.setdefault(run_id, []).extend(snapshots)

    def list_run_photos(self, run_id):
        return list(self._run_photos.get(run_id, []))


class _StubThumbnailSource:
    """Async-channel double: records requests so tests can replay arrivals."""

    def __init__(self):
        from PySide6.QtCore import QObject, Signal

        class _Signals(QObject):
            thumbnail_loaded = Signal(object, object)

        self._signals = _Signals()
        self.thumbnail_loaded = self._signals.thumbnail_loaded
        self.requests: list[tuple] = []

    def load_thumbnail(self, photo_id, source_path):
        self.requests.append((photo_id, source_path))


class _Harness:
    """One recognition run with three observations across two photos."""

    def __init__(self):
        self.runs = _RunRepoWithPhotos()
        self.observations = InMemoryFaceObservationRepository()
        self.clusters = InMemoryFaceClusterRepository()
        self.service = ClusterResultsService(self.runs, self.observations, self.clusters)
        self.recognition_run = RecognitionRun(parameters={})
        self.runs.add_run(self.recognition_run)
        self.photo_a, self.photo_b = uuid4(), uuid4()
        self.runs.add_run_photos(self.recognition_run.id, [
            RunPhotoSnapshot(self.recognition_run.id, self.photo_a,
                             "photos/合影.jpg", None),
            RunPhotoSnapshot(self.recognition_run.id, self.photo_b,
                             "photos/单人.jpg", None),
        ])
        self.o1 = self._observation(self.photo_a, 0, 0.0)
        self.o2 = self._observation(self.photo_b, 0, 6.0)
        self.o3 = self._observation(self.photo_a, 1, 180.0)

    def _observation(self, photo_id, index, angle):
        import math
        observation = FaceObservation(
            run_id=self.recognition_run.id,
            photo_id=photo_id,
            face_index=index,
            photo_face_count=index + 1,
            det_score=0.9,
            box=FaceBox(index, 0, index + 10, 10),
            embedding=FaceEmbedding((math.cos(math.radians(angle)), math.sin(math.radians(angle)))),
            scope_verdict="in_selected_scope",
        )
        self.observations.add_many([observation])
        return observation

    def add_generation(self, *, complete=True, created_at=None) -> FaceClusterRun:
        cluster_run = FaceClusterRun(recognition_run_id=self.recognition_run.id,
                                     algorithm_version="v1", created_at=created_at)
        self.clusters.add_cluster_run(cluster_run)
        cluster = FaceCluster(
            cluster_run_id=cluster_run.id, run_id=self.recognition_run.id,
            ordinal=0, member_count=2, sort_key="k",
        )
        self.clusters.add_clusters([cluster])
        self.clusters.add_members([
            FaceClusterMember(cluster_id=cluster.id, observation_id=self.o1.id,
                              confidence=1.0),
            FaceClusterMember(cluster_id=cluster.id, observation_id=self.o2.id,
                              confidence=0.87),
        ])
        if complete:
            cluster_run.start()
            cluster_run.complete(1, 2, 1)
        return cluster_run

    def build_dialog(self, qtbot, thumbnail_source=None) -> ClusterResultsDialog:
        dialog = ClusterResultsDialog(
            self.service, self.recognition_run.id,
            thumbnail_source=thumbnail_source,
        )
        qtbot.addWidget(dialog)
        return dialog


def test_generation_combo_lists_runs_and_summary_shows_counts(qtbot) -> None:
    harness = _Harness()
    harness.add_generation()
    dialog = harness.build_dialog(qtbot)

    assert dialog._generation_combo.count() == 1
    entry = dialog._generation_combo.itemText(0)
    assert "已完成" in entry and "1 簇" in entry and "2 张脸" in entry
    summary = dialog._generation_summary.text()
    assert "1 簇 · 2 张脸 · 排除 1 张观测" in summary


def test_clusters_and_members_render_persisted_data(qtbot) -> None:
    harness = _Harness()
    harness.add_generation()
    dialog = harness.build_dialog(qtbot)

    assert dialog._cluster_list.count() == 1
    cluster_item = dialog._cluster_list.item(0)
    assert "第 1 组" in cluster_item.text() and "2 张脸" in cluster_item.text()
    members = [dialog._member_list.item(i).text() for i in range(dialog._member_list.count())]
    assert len(members) == 2
    assert any("合影.jpg" in m and "脸 1" in m for m in members)
    assert any("单人.jpg" in m and "检测 0.90" in m and "证据 0.87" in m for m in members)
    # D-4 边界：不含任何人员归属信息。
    assert not any("人员" in m or "分配" in m for m in members)


def test_generation_switch_reloads_data(qtbot) -> None:
    from datetime import datetime, timedelta

    harness = _Harness()
    first = harness.add_generation(created_at=datetime(2026, 1, 1))
    second = harness.add_generation(
        created_at=datetime(2026, 1, 1) + timedelta(minutes=5),
    )
    dialog = harness.build_dialog(qtbot)
    assert dialog._generation_combo.currentData() == second.id  # 默认选最新代

    index = dialog._generation_combo.findData(first.id)
    dialog._generation_combo.setCurrentIndex(index)

    assert dialog._generation_combo.currentData() == first.id
    assert dialog._generation_summary.text().startswith("1 簇")


def test_no_generations_shows_empty_state(qtbot) -> None:
    harness = _Harness()
    dialog = harness.build_dialog(qtbot)

    assert dialog._generation_combo.count() == 0
    assert "尚无聚类结果" in dialog._empty_label.text()
    assert dialog._cluster_list.count() == 0


def test_generation_without_clusters_shows_empty_state(qtbot) -> None:
    harness = _Harness()
    cluster_run = FaceClusterRun(recognition_run_id=harness.recognition_run.id,
                                 algorithm_version="v1")
    harness.clusters.add_cluster_run(cluster_run)
    cluster_run.start()
    cluster_run.complete(0, 0, 3)
    dialog = harness.build_dialog(qtbot)

    assert "没有产生任何簇" in dialog._empty_label.text()
    assert dialog._cluster_list.count() == 0


def test_member_rows_request_thumbnails_through_shared_channel(qtbot, tmp_path) -> None:
    harness = _Harness()
    harness.add_generation()
    source = _StubThumbnailSource()
    dialog = harness.build_dialog(qtbot, thumbnail_source=source)

    requests = {photo_id for photo_id, _ in source.requests}
    assert requests == {harness.photo_a, harness.photo_b}
    # 缩略图到达后按 photo id 附加；QIcon 只有加载真实文件才非 null。
    thumb_a = tmp_path / "a.png"
    thumb_b = tmp_path / "b.png"
    thumb_a.write_bytes(_PNG_BYTES)
    thumb_b.write_bytes(_PNG_BYTES)
    # 成员展示按（照片路径, 脸序号）排序：item(0)=单人.jpg(photo_b)。
    dialog._attach_thumbnail(harness.photo_b, thumb_b)
    assert not dialog._member_list.item(0).icon().isNull()
    assert dialog._member_list.item(1).icon().isNull()  # 另一照片尚未到达
    dialog._attach_thumbnail(harness.photo_a, thumb_a)
    assert not dialog._member_list.item(1).icon().isNull()
