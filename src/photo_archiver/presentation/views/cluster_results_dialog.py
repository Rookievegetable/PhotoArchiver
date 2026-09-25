"""Cluster results dialog — D-4 聚类结果的只读展示.

展示持久化的 ``FaceClusterRun → FaceCluster → FaceClusterMember →
FaceObservation`` 数据：代际选择器（同一识别运行的每次聚类一代）、代内
簇列表（组号/成员数/首拍时间）、选中簇的成员明细（照片缩略图经共享异步
通道加载，不阻塞 UI 线程）。**不含任何人员归属**——Person assignment 属
Stage E；也不读取 legacy MatchPersons 数据。
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.dtos.cluster_results import ClusterRunResults
from photo_archiver.application.services import ClusterResultsService
from photo_archiver.presentation import ui_text as text


def _format_moment(moment) -> str:
    """Render a persisted datetime for the UI（无时区转换，原样展示）。"""
    return moment.strftime("%Y-%m-%d %H:%M") if moment is not None else text.CLUSTER_RESULTS_NO_CAPTURED


class ClusterResultsDialog(QDialog):
    """Read-only view of one recognition run's clustering generations."""

    def __init__(
        self,
        results_service: ClusterResultsService,
        recognition_run_id: UUID,
        parent: QWidget | None = None,
        thumbnail_source=None,
    ) -> None:
        """Build the dialog; ``thumbnail_source`` is the shared async loader."""
        super().__init__(parent)
        self.setWindowTitle(text.CLUSTER_RESULTS_TITLE)
        self.setMinimumSize(720, 480)
        self._results_service = results_service
        self._recognition_run_id = recognition_run_id
        self._thumbnail_source = thumbnail_source
        self._items_by_photo_id: dict[UUID, list[QListWidgetItem]] = {}
        self._current: ClusterRunResults | None = None
        self._build_ui()
        if thumbnail_source is not None:
            # Connect once — members of many photos register many rows and a
            # per-row connect would multiply every arriving signal.
            thumbnail_source.thumbnail_loaded.connect(self._attach_thumbnail)
        self.refresh()

    def _build_ui(self) -> None:
        """Lay out the generation selector, cluster list and member list."""
        layout = QVBoxLayout(self)

        generation_row = QHBoxLayout()
        generation_row.addWidget(QLabel(text.CLUSTER_RESULTS_GENERATION_LABEL, self))
        self._generation_combo = QComboBox(self)
        self._generation_combo.setMinimumWidth(360)
        self._generation_combo.currentIndexChanged.connect(self._on_generation_selected)
        generation_row.addWidget(self._generation_combo)
        generation_row.addStretch()
        layout.addLayout(generation_row)

        self._generation_summary = QLabel(self)
        self._generation_summary.setWordWrap(True)
        layout.addWidget(self._generation_summary)

        body = QHBoxLayout()
        self._cluster_list = QListWidget(self)
        self._cluster_list.setMinimumWidth(280)
        self._cluster_list.currentItemChanged.connect(self._on_cluster_selected)
        body.addWidget(self._cluster_list, 2)
        self._member_list = QListWidget(self)
        body.addWidget(self._member_list, 3)
        layout.addLayout(body, 1)

        self._empty_label = QLabel(self)
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

    # ── Data + rendering ────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload the generation list, keeping the current generation selected."""
        selected = self._generation_combo.currentData()
        runs = self._results_service.list_cluster_runs(self._recognition_run_id)
        self._generation_combo.blockSignals(True)
        self._generation_combo.clear()
        for run in runs:
            self._generation_combo.addItem(
                text.CLUSTER_RESULTS_GENERATION_ENTRY.format(
                    created_at=_format_moment(run.created_at),
                    status=text.cluster_run_status_label(run.status),
                    clusters=run.cluster_count,
                    members=run.member_count,
                ),
                run.id,
            )
        if selected is not None:
            # findData 对值相等但非同一实例的 UUID 不可靠（QVariant 比较），
            # 代际保持用值扫描。
            for index in range(self._generation_combo.count()):
                if self._generation_combo.itemData(index) == selected:
                    self._generation_combo.setCurrentIndex(index)
                    break
        if self._generation_combo.currentIndex() < 0 and self._generation_combo.count():
            self._generation_combo.setCurrentIndex(0)
        self._generation_combo.blockSignals(False)
        if not runs:
            self._current = None
            self._generation_summary.clear()
            self._cluster_list.clear()
            self._member_list.clear()
            self._empty_label.setText(text.CLUSTER_RESULTS_EMPTY)
            return
        self._empty_label.clear()
        self._on_generation_selected(self._generation_combo.currentIndex())

    def _on_generation_selected(self, _index: int) -> None:
        """Load the selected generation's clusters and re-render members."""
        cluster_run_id = self._generation_combo.currentData()
        if cluster_run_id is None:
            self._current = None
            self._cluster_list.clear()
            self._member_list.clear()
            return
        self._current = self._results_service.results(cluster_run_id)
        self._render_clusters()

    def _render_clusters(self) -> None:
        """Refill the cluster list and the member pane for the current generation."""
        results = self._current
        self._cluster_list.blockSignals(True)
        self._cluster_list.clear()
        self._member_list.clear()
        self._items_by_photo_id = {}
        if results is None:
            self._cluster_list.blockSignals(False)
            return
        run = results.cluster_run
        self._generation_summary.setText(
            text.STATUS_CLUSTER_SUMMARY.format(
                clusters=run.cluster_count,
                members=run.member_count,
                excluded=run.excluded_count,
            )
            + f" · {text.cluster_run_status_label(run.status)}"
        )
        if not results.clusters:
            self._empty_label.setText(text.CLUSTER_RESULTS_EMPTY_CLUSTERS)
            self._cluster_list.blockSignals(False)
            return
        self._empty_label.clear()
        for detail in results.clusters:
            item = QListWidgetItem(text.CLUSTER_RESULTS_CLUSTER_ENTRY.format(
                ordinal=detail.ordinal + 1,
                count=detail.member_count,
                time=_format_moment(detail.first_captured_at),
            ))
            item.setData(Qt.ItemDataRole.UserRole, detail.cluster_id)
            self._cluster_list.addItem(item)
        self._cluster_list.blockSignals(False)
        self._cluster_list.setCurrentRow(0)

    def _on_cluster_selected(self, current, _previous) -> None:
        """Render the selected cluster's member details (thumbnails requested)."""
        self._member_list.clear()
        self._items_by_photo_id = {}
        if self._current is None or current is None:
            return
        cluster_id = current.data(Qt.ItemDataRole.UserRole)
        detail = next(
            (d for d in self._current.clusters if d.cluster_id == cluster_id), None,
        )
        if detail is None:
            return
        for member in detail.members:
            photo_name = member.photo_path.replace("\\", "/").rsplit("/", 1)[-1]
            item = QListWidgetItem(text.CLUSTER_RESULTS_MEMBER_ENTRY.format(
                photo=photo_name or "—",
                index=member.face_index + 1,
                det=member.det_score,
                conf=member.confidence,
            ))
            self._member_list.addItem(item)
            self._request_row_thumbnail(item, member)

    def _request_row_thumbnail(self, item: QListWidgetItem, member) -> None:
        """Route one member's photo thumbnail through the shared async loader."""
        photo_id = member.photo_id
        if self._thumbnail_source is None or not member.photo_path or photo_id is None:
            return
        self._items_by_photo_id.setdefault(photo_id, []).append(item)
        self._thumbnail_source.load_thumbnail(photo_id, Path(member.photo_path))

    def _attach_thumbnail(self, photo_id: object, thumbnail: object) -> None:
        """Attach an arrived thumbnail to every row of that photo (no-op on miss)."""
        if not isinstance(photo_id, UUID) or thumbnail is None:
            return
        items = self._items_by_photo_id.get(photo_id)
        if not items:
            return
        icon = QIcon(str(thumbnail))
        for item in items:
            item.setIcon(icon)
