"""Cluster results dialog — D-4 聚类结果展示 + Ground Truth 标注 + 配对整合.

三种模式（按注入的服务组合自动启用，互不干扰）：

- **只读模式**（缺省）：展示持久化的 ``FaceClusterRun → FaceCluster →
  FaceClusterMember → FaceObservation``：代际选择器、代内簇列表（组号/
  匹配人员/照片数/脸数/首拍）、选中簇的成员明细。
- **Ground Truth 标注模式**（注入 ``calibration_service`` + ``annotator_id``，
  S4-B-1 Checkpoint 7）：追加标注面板，与业务 Assignment 完全隔离；
  标注模式下成员条目隐藏 det/conf（CP7.3 confirmation-bias 防护）。
- **配对整合模式**（界面优化 §5：注入 suggest/workbench/ignore 服务）：
  在聚类结果之上叠加配对操作——目标人员选择器 + 确认/拒绝（作用于
  「簇 × 人员」配对关系）、照片多选 + 忽略/恢复（作用于照片，代际作用
  域）、批量操作逐项提交并如实报告成功/跳过/失败。**没有"解除映射"
  入口**（Owner 决策：全部移除，且不得以同义新按钮绕过）。

展示顺序按（照片路径, 脸序号）确定性排序；照片缩略图经共享异步通道
加载，不阻塞 UI 线程。
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.commands.pairing import (
    AssignClusterPersonCommand,
    ConfirmAssignmentCommand,
    RejectAssignmentCommand,
    StartSuggestPairingsCommand,
)
from photo_archiver.application.commands.photo_ignore import (
    IgnorePhotosCommand,
    RestorePhotosCommand,
)
from photo_archiver.application.dtos.cluster_results import ClusterRunResults
from photo_archiver.application.services import ClusterResultsService
from photo_archiver.application.services.calibration_annotation_service import (
    CalibrationAnnotationService,
)
from photo_archiver.domain import ClusterPersonAssignment
from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.calibration_annotation_panel import (
    CalibrationAnnotationPanel,
)
from photo_archiver.presentation.views.photo_detail_dialog import PhotoDetailDialog
from photo_archiver.presentation.visual_style import ROLE_DANGER, ROLE_PRIMARY, assign_role


def _format_moment(moment) -> str:
    """Render a persisted datetime for the UI（无时区转换，原样展示）。"""
    return moment.strftime("%Y-%m-%d %H:%M") if moment is not None else text.CLUSTER_RESULTS_NO_CAPTURED


class ClusterResultsDialog(QDialog):
    """Read-only / calibration / integrated-pairing view of one recognition run."""

    def __init__(
        self,
        results_service: ClusterResultsService,
        recognition_run_id: UUID,
        parent: QWidget | None = None,
        thumbnail_source=None,
        calibration_service: CalibrationAnnotationService | None = None,
        annotator_id: str | None = None,
        persons_provider=None,
        *,
        suggest_service=None,
        workbench_service=None,
        ignore_service=None,
        list_persons=None,
    ) -> None:
        """Build the dialog; ``thumbnail_source`` is the shared async loader.

        S4-B-1：传入 ``calibration_service`` + ``annotator_id`` +
        ``persons_provider`` 后启用 Ground Truth 标注面板（CP7）；不传
        ``calibration_service`` 则保持纯只读模式。S4-B-2 fail-closed：启用
        Calibration 模式时 ``annotator_id`` 为 None/空白将在构造期抛出
        :class:`ValueError`。

        界面优化 §5：注入 ``suggest_service`` + ``workbench_service``（+
        ``ignore_service``/``list_persons``）后启用配对整合模式。
        """
        super().__init__(parent)
        self.setWindowTitle(text.CLUSTER_RESULTS_TITLE)
        self.setMinimumSize(900, 560)
        self._results_service = results_service
        self._recognition_run_id = recognition_run_id
        self._thumbnail_source = thumbnail_source
        self._calibration_service = calibration_service
        self._persons_provider = persons_provider
        self._calibration_active = calibration_service is not None
        self._calibration_panel: CalibrationAnnotationPanel | None = None
        self._calibration_service_typed = calibration_service
        self._annotator_id_typed: str | None = None
        # 配对整合模式（§5）：suggest + workbench 必须成对注入。
        self._suggest_service = suggest_service
        self._workbench_service = workbench_service
        self._ignore_service = ignore_service
        self._list_persons = list_persons
        self._pairing_active = suggest_service is not None and workbench_service is not None
        if self._calibration_active:
            if annotator_id is None or not annotator_id.strip():
                raise ValueError(text.CALIBRATION_ANNOTATOR_ID_REQUIRED)
            self._annotator_id_typed = annotator_id.strip()
        self._items_by_photo_id: dict[UUID, list[QListWidgetItem]] = {}
        self._thumbnail_paths: dict[UUID, Path] = {}
        self._current: ClusterRunResults | None = None
        self._persons = list_persons.execute() if list_persons is not None else []
        self._detail_dialog: PhotoDetailDialog | None = None
        self._detail_photos: list = []
        self._detail_index = 0
        self._build_ui()
        if thumbnail_source is not None:
            # Connect once — members of many photos register many rows and a
            # per-row connect would multiply every arriving signal.
            thumbnail_source.thumbnail_loaded.connect(self._attach_thumbnail)
        self.refresh()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Lay out the generation row, cluster list and the detail pane."""
        layout = QVBoxLayout(self)

        generation_row = QHBoxLayout()
        generation_row.addWidget(QLabel(text.CLUSTER_RESULTS_GENERATION_LABEL, self))
        self._generation_combo = QComboBox(self)
        self._generation_combo.setMinimumWidth(360)
        self._generation_combo.currentIndexChanged.connect(self._on_generation_selected)
        generation_row.addWidget(self._generation_combo)
        if self._pairing_active:
            self._generate_button = QPushButton(
                text.CLUSTER_PAIRING_GENERATE_BUTTON, self)
            self._generate_button.clicked.connect(self._on_generate_clicked)
            # P5：无代际时禁用（调用侧不再存在静默 no-op 路径）。
            self._generate_button.setEnabled(False)
            assign_role(self._generate_button, ROLE_PRIMARY)
            generation_row.addWidget(self._generate_button)
        generation_row.addStretch()
        layout.addLayout(generation_row)

        self._generation_summary = QLabel(self)
        self._generation_summary.setWordWrap(True)
        layout.addWidget(self._generation_summary)
        self._run_status_label = QLabel(self)
        self._run_status_label.setWordWrap(True)
        self._run_status_label.setVisible(self._pairing_active)
        layout.addWidget(self._run_status_label)
        # 批量操作/生成建议的逐项结果反馈（独立于代际摘要，不随刷新清除）。
        self._feedback_label = QLabel(self)
        self._feedback_label.setWordWrap(True)
        self._feedback_label.setVisible(self._pairing_active)
        layout.addWidget(self._feedback_label)

        body = QHBoxLayout()
        self._cluster_list = QListWidget(self)
        self._cluster_list.setMinimumWidth(300)
        self._cluster_list.currentItemChanged.connect(self._on_cluster_selected)
        if self._pairing_active:
            # 批量确认/拒绝：簇列表支持多选（ExtendedSelection）。
            self._cluster_list.setSelectionMode(
                QAbstractItemView.SelectionMode.ExtendedSelection,
            )
        body.addWidget(self._cluster_list, 2)

        if self._pairing_active:
            body.addWidget(self._build_pairing_pane(), 3)
        else:
            self._member_list = QListWidget(self)
            body.addWidget(self._member_list, 3)
        layout.addLayout(body, 1)

        self._empty_label = QLabel(self)
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        # S4-B-1：Ground Truth 标注面板（仅 calibration 模式）。
        if (
            self._calibration_active
            and self._calibration_service_typed is not None
            and self._annotator_id_typed is not None
        ):
            self._calibration_panel = CalibrationAnnotationPanel(
                calibration_service=self._calibration_service_typed,
                annotator_id=self._annotator_id_typed,
                persons_provider=self._persons_provider,
                parent=self,
            )
            layout.addWidget(self._calibration_panel)

    def _build_pairing_pane(self) -> QWidget:
        """Right pane for pairing mode: info, photo grid, person actions."""
        pane = QWidget(self)
        layout = QVBoxLayout(pane)

        self._detail_info = QLabel(self)
        self._detail_info.setWordWrap(True)
        layout.addWidget(self._detail_info)

        photos_row = QHBoxLayout()
        photos_row.addWidget(QLabel(text.CLUSTER_PAIRING_PHOTOS_LABEL, pane))
        photos_row.addStretch()
        self._detail_prev_button = QPushButton(text.CLUSTER_PAIRING_DETAIL_PREV, pane)
        self._detail_prev_button.clicked.connect(lambda: self._on_detail_prev_next(-1))
        self._detail_next_button = QPushButton(text.CLUSTER_PAIRING_DETAIL_NEXT, pane)
        self._detail_next_button.clicked.connect(lambda: self._on_detail_prev_next(1))
        # P6：详图未打开时导航禁用（消除按钮可点但静默无效的路径）；打开/
        # 关闭随 _open_detail/_on_detail_dialog_finished 联动启停。
        self._detail_prev_button.setEnabled(False)
        self._detail_next_button.setEnabled(False)
        photos_row.addWidget(self._detail_prev_button)
        photos_row.addWidget(self._detail_next_button)
        layout.addLayout(photos_row)
        self._photo_grid = QListWidget(self)
        self._photo_grid.setViewMode(QListWidget.ViewMode.IconMode)
        self._photo_grid.setIconSize(QSize(96, 96))
        self._photo_grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._photo_grid.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection,
        )
        self._photo_grid.itemDoubleClicked.connect(self._on_photo_double_clicked)
        layout.addWidget(self._photo_grid, 1)

        photo_actions = QHBoxLayout()
        self._ignore_button = QPushButton(text.CLUSTER_PAIRING_IGNORE_BUTTON, pane)
        self._ignore_button.clicked.connect(self._on_ignore_clicked)
        assign_role(self._ignore_button, ROLE_DANGER)
        self._restore_button = QPushButton(text.CLUSTER_PAIRING_RESTORE_BUTTON, pane)
        self._restore_button.clicked.connect(self._on_restore_clicked)
        photo_actions.addWidget(self._ignore_button)
        photo_actions.addWidget(self._restore_button)
        photo_actions.addStretch()
        layout.addLayout(photo_actions)

        person_row = QHBoxLayout()
        person_row.addWidget(QLabel(text.CLUSTER_PAIRING_PERSON_LABEL, pane))
        self._person_combo = QComboBox(pane)
        self._person_combo.setMinimumWidth(200)
        person_row.addWidget(self._person_combo)
        self._confirm_button = QPushButton(text.CLUSTER_PAIRING_CONFIRM_BUTTON, pane)
        self._confirm_button.clicked.connect(self._on_confirm_clicked)
        assign_role(self._confirm_button, ROLE_PRIMARY)
        self._reject_button = QPushButton(text.CLUSTER_PAIRING_REJECT_BUTTON, pane)
        self._reject_button.clicked.connect(self._on_reject_clicked)
        assign_role(self._reject_button, ROLE_DANGER)
        person_row.addWidget(self._confirm_button)
        person_row.addWidget(self._reject_button)
        person_row.addStretch()
        layout.addLayout(person_row)

        order_hint = QLabel(text.CLUSTER_PAIRING_ORDER_HINT, pane)
        order_hint.setWordWrap(True)
        layout.addWidget(order_hint)
        return pane

    # ── Data + rendering ────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload the generation list, keeping the current generation selected."""
        # P6：代际列表/簇列表即将重载，旧快照（_detail_photos）随之失效——
        # 先关闭已打开的详图，消除导航打到过期照片的失步路径。
        self._close_detail()
        self._persons = (
            self._list_persons.execute() if self._list_persons is not None else []
        )
        self._render_person_combo()
        selected = self._generation_combo.currentData()
        runs = self._results_service.list_cluster_runs(self._recognition_run_id)
        self._generation_combo.blockSignals(True)
        self._generation_combo.clear()
        for index, run in enumerate(runs):
            label = text.CLUSTER_RESULTS_GENERATION_ENTRY.format(
                created_at=_format_moment(run.created_at),
                status=text.cluster_run_status_label(run.status),
                clusters=run.cluster_count,
                members=run.member_count,
            )
            if index == 0:
                # P7：list_cluster_runs 返回 newest-first，首位即最新代际
                #（单代际同样标注）；纯显示后缀，零业务语义。
                label += text.CLUSTER_RESULTS_GENERATION_LATEST_MARK
            self._generation_combo.addItem(label, run.id)
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
        self._update_generate_button_state()
        if not runs:
            self._current = None
            self._generation_summary.clear()
            self._cluster_list.clear()
            if self._pairing_active:
                self._photo_grid.clear()
            else:
                self._member_list.clear()
            self._empty_label.setText(text.CLUSTER_RESULTS_EMPTY)
            return
        self._empty_label.clear()
        self._on_generation_selected(self._generation_combo.currentIndex())

    def _render_person_combo(self) -> None:
        """Person selector（roster 顺序）；空名单禁用确认/拒绝。"""
        if not self._pairing_active:
            return
        self._person_combo.blockSignals(True)
        self._person_combo.clear()
        for person in self._persons:
            if person.id is not None:
                self._person_combo.addItem(person.name, person.id)
        self._person_combo.blockSignals(False)
        has_persons = bool(self._persons)
        self._person_combo.setEnabled(has_persons)
        self._confirm_button.setEnabled(has_persons)
        self._reject_button.setEnabled(has_persons)

    def _assignments_by_cluster(self) -> dict[UUID, ClusterPersonAssignment]:
        """当前有效指派（suggested/auto_confirmed/confirmed）按 cluster 索引。"""
        cluster_run_id = self._generation_combo.currentData()
        if cluster_run_id is None:
            return {}
        return {
            assignment.cluster_id: assignment
            for assignment in self._results_service.assignments_active(cluster_run_id)
        }

    def _person_name(self, person_id: UUID | None) -> str:
        if person_id is None:
            return "—"
        for person in self._persons:
            if person.id == person_id:
                return person.name
        return "—"

    def _on_generation_selected(self, _index: int) -> None:
        """Load the selected generation's clusters and re-render members."""
        # P6：切换代际 = 照片快照整体失效——先关闭已打开的详图（若在），再
        # 重载；消除 _detail_photos/_detail_index 与新代际的失步。
        self._close_detail()
        self._update_generate_button_state()
        cluster_run_id = self._generation_combo.currentData()
        if cluster_run_id is None:
            self._current = None
            self._cluster_list.clear()
            if self._pairing_active:
                self._photo_grid.clear()
            else:
                self._member_list.clear()
            return
        self._current = self._results_service.results(cluster_run_id)
        self._render_run_status(cluster_run_id)
        self._render_clusters()

    def _render_run_status(self, cluster_run_id: UUID) -> None:
        """§5.3 run 级人脸数与可确定的处理状态（未知不并入 0 脸）。"""
        if not self._pairing_active or self._current is None:
            return
        summary = self._results_service.run_photo_outcome_summary(
            self._current.cluster_run.recognition_run_id,
        )
        self._run_status_label.setText(text.CLUSTER_PAIRING_RUN_STATUS.format(**summary))

    def _render_clusters(self) -> None:
        """Refill the cluster list and the detail pane for the current generation."""
        results = self._current
        self._cluster_list.blockSignals(True)
        self._cluster_list.clear()
        if self._pairing_active:
            self._photo_grid.clear()
            self._items_by_photo_id = {}
        else:
            self._member_list.clear()
            self._items_by_photo_id = {}
        if results is None:
            self._cluster_list.blockSignals(False)
            return
        if not results.clusters:
            self._cluster_list.blockSignals(False)
            self._empty_label.setText(text.CLUSTER_RESULTS_EMPTY_CLUSTERS)
            return
        self._empty_label.clear()
        run = results.cluster_run
        self._generation_summary.setText(
            text.STATUS_CLUSTER_SUMMARY.format(
                clusters=run.cluster_count,
                members=run.member_count,
                excluded=run.excluded_count,
            )
            + f" · {text.cluster_run_status_label(run.status)}"
        )
        assignments = self._assignments_by_cluster() if self._pairing_active else {}
        for detail in results.clusters:
            if self._pairing_active:
                assignment = assignments.get(detail.cluster_id)
                person = (
                    self._person_name(assignment.person_id)
                    if assignment is not None else text.CLUSTER_PAIRING_UNMATCHED
                )
                label = text.CLUSTER_ENTRY_PHOTOS.format(
                    ordinal=detail.ordinal + 1,
                    person=person,
                    photos=detail.photo_count,
                    faces=detail.member_count,
                )
            else:
                label = text.CLUSTER_RESULTS_CLUSTER_ENTRY.format(
                    ordinal=detail.ordinal + 1,
                    count=detail.member_count,
                    time=_format_moment(detail.first_captured_at),
                )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, detail.cluster_id)
            self._cluster_list.addItem(item)
        self._cluster_list.blockSignals(False)
        self._cluster_list.setCurrentRow(0)

    def _on_cluster_selected(self, current, _previous) -> None:
        """Render the selected cluster's details (photos grid / member list)."""
        cluster_id = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        if self._calibration_active and self._calibration_panel is not None:
            # S4-B-1 CP7.15：切换簇时推送新 cluster_id 给标注面板（清残留）。
            self._calibration_panel.set_cluster(cluster_id)
        if self._current is None or current is None:
            return
        detail = next(
            (d for d in self._current.clusters if d.cluster_id == cluster_id), None,
        )
        if detail is None:
            return
        if self._pairing_active:
            self._render_pairing_detail(detail)
        else:
            self._render_member_list(detail)

    def _render_member_list(self, detail) -> None:
        """只读/标注模式的成员明细列表（原行为）。"""
        self._member_list.clear()
        self._items_by_photo_id = {}
        for member in detail.members:
            photo_name = member.photo_path.replace("\\", "/").rsplit("/", 1)[-1]
            if self._calibration_active:
                # CP7.3：标注模式下隐藏 det/conf（confirmation-bias 防护）。
                item = QListWidgetItem(text.CALIBRATION_MEMBER_ENTRY_NEUTRAL.format(
                    photo=photo_name or "—",
                    index=member.face_index + 1,
                ))
            else:
                item = QListWidgetItem(text.CLUSTER_RESULTS_MEMBER_ENTRY.format(
                    photo=photo_name or "—",
                    index=member.face_index + 1,
                    det=member.det_score,
                    conf=member.confidence,
                ))
            self._member_list.addItem(item)
            self._request_row_thumbnail(item, member)

    def _render_pairing_detail(self, detail) -> None:
        """§5.3 右侧详情：决策/人物数/照片与状态/配对状态/异常未决。"""
        self._photo_grid.clear()
        self._items_by_photo_id = {}
        self._thumbnail_paths.clear()
        assignments = self._assignments_by_cluster()
        assignment = assignments.get(detail.cluster_id)
        person_ids = self._results_service.active_person_ids(
            self._generation_combo.currentData(),
        )
        decision_text = (
            text.PAIRING_WORKBENCH_ASSIGNMENT_LABEL.get(assignment.status, "?")
            if assignment is not None else text.CLUSTER_PAIRING_UNMATCHED
        )
        if assignment is not None:
            decision_text = decision_text.format(
                person=self._person_name(assignment.person_id),
            )
        ignored_set = set(detail.ignored_photo_ids)
        ignored_note = (
            f" · 忽略照片 {len(ignored_set)} 张" if ignored_set else ""
        )
        self._detail_info.setText(
            text.CLUSTER_ENTRY_PHOTOS.format(
                ordinal=detail.ordinal + 1,
                person=(
                    self._person_name(assignment.person_id)
                    if assignment is not None else text.CLUSTER_PAIRING_UNMATCHED
                ),
                photos=detail.photo_count,
                faces=detail.member_count,
            )
            + f"\n{text.CLUSTER_PAIRING_DECISIONS_LABEL.format(count=len(person_ids))}"
            + f"\n配对状态：{decision_text}{ignored_note}"
        )
        # 照片网格：按 photo 去重（一张照片多脸只显示一行）。
        seen_photos: set[UUID] = set()
        for member in detail.members:
            if member.photo_id is None or member.photo_id in seen_photos:
                continue
            seen_photos.add(member.photo_id)
            photo_name = member.photo_path.replace("\\", "/").rsplit("/", 1)[-1]
            outcome_label = text.RUN_PHOTO_OUTCOME_LABELS.get(
                member.photo_outcome, text.RUN_PHOTO_OUTCOME_LABELS[None],
            )
            ignored_mark = (
                text.CLUSTER_PAIRING_IGNORED_MARK if member.photo_id in ignored_set else ""
            )
            item = QListWidgetItem(text.CLUSTER_PAIRING_MEMBER_ENTRY.format(
                photo=photo_name or "—",
                index=member.face_index + 1,
                faces=member.photo_face_count,
                outcome=outcome_label,
                ignored=ignored_mark,
            ))
            item.setData(Qt.ItemDataRole.UserRole, member.photo_id)
            item.setToolTip(member.photo_path)
            self._photo_grid.addItem(item)
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
        if isinstance(thumbnail, Path):
            self._thumbnail_paths[photo_id] = Path(thumbnail)
        for item in items:
            item.setIcon(icon)

    # ── 生成建议 ─────────────────────────────────────────────────────────

    def _update_generate_button_state(self) -> None:
        """P5：生成建议按钮仅在存在可操作代际时启用（守卫 getattr 兼容只读模式）。"""
        button = getattr(self, "_generate_button", None)
        if button is None:
            return
        button.setEnabled(self._generation_combo.currentData() is not None)

    def _on_generate_clicked(self) -> None:
        """生成建议（§4.2：采用当前名单顺序；不自动改写既有决策）。"""
        cluster_run_id = self._generation_combo.currentData()
        if cluster_run_id is None:
            # P5：按钮已禁用，此分支仅为防御；仍给可见反馈而非静默。
            self._feedback_label.setText(text.CLUSTER_PAIRING_NO_GENERATION)
            return
        if not self._persons:
            # P5：空名单时给出明确反馈，不再静默产出零建议。
            self._feedback_label.setText(text.CLUSTER_PAIRING_NO_PERSONS)
            return
        summary = self._suggest_service.execute(
            StartSuggestPairingsCommand(cluster_run_id),
        )
        feedback = text.PAIRING_WORKBENCH_SUGGESTED_DONE.format(
            suggestions=summary.suggestions,
            sample_matched=summary.sample_matched,
            ordered=summary.ordered,
        )
        if summary.auto_confirmed:
            feedback += "；" + text.PAIRING_WORKBENCH_AUTO_CONFIRM_DONE.format(
                auto_confirmed=summary.auto_confirmed,
            )
        elif summary.auto_confirm_blocked_reason:
            reason = text.PAIRING_WORKBENCH_AUTO_CONFIRM_BLOCKED_REASONS.get(
                summary.auto_confirm_blocked_reason,
                summary.auto_confirm_blocked_reason,
            )
            feedback += "；" + text.PAIRING_WORKBENCH_AUTO_CONFIRM_BLOCKED.format(
                reason=reason,
            )
        self._feedback_label.setText(feedback)
        self.refresh()

    # ── 确认 / 拒绝（批量，逐项提交） ────────────────────────────────────

    def _selected_cluster_ids(self) -> list[UUID]:
        """Selected clusters（多选批量；单选即为单项）。"""
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self._cluster_list.selectedItems()
            if isinstance(item.data(Qt.ItemDataRole.UserRole), UUID)
        ]

    def _target_person_id(self) -> UUID | None:
        return self._person_combo.currentData()

    def _cluster_labels(self) -> dict[UUID, str]:
        """Cluster id → list entry text (batch plan display)."""
        return {
            item.data(Qt.ItemDataRole.UserRole): item.text()
            for item in (
                self._cluster_list.item(row)
                for row in range(self._cluster_list.count())
            )
        }

    def _plan_confirm(
        self, cluster_ids: list[UUID], person_id: UUID,
    ) -> list[tuple[UUID, str, str, str | None]]:
        """批量确认预演（§3.3：操作前显示将执行与跳过的项目）.

        条目 = (cluster_id, 展示标签, 动作, assignment_id)——confirm 动作
        携带待确认行 id；assign 动作无需行。
        """
        assignments = self._assignments_by_cluster()
        cluster_labels = self._cluster_labels()
        plan: list[tuple[UUID, str, str, str | None]] = []
        for cluster_id in cluster_ids:
            label = cluster_labels.get(cluster_id, str(cluster_id))
            assignment = assignments.get(cluster_id)
            if (
                assignment is not None
                and assignment.person_id == person_id
                and assignment.status == "confirmed"
            ):
                plan.append((cluster_id, label, "skip",
                             text.CLUSTER_PAIRING_CONFIRMED_SKIP))
            elif (
                assignment is not None
                and assignment.person_id == person_id
                and assignment.status == "suggested"
                and assignment.id is not None
            ):
                plan.append((cluster_id, label, "confirm", str(assignment.id)))
            else:
                # 无有效行 / 自动确认行终审 / 改派——人工明确选择即确认。
                plan.append((cluster_id, label, "assign", None))
        return plan

    def _on_confirm_clicked(self) -> None:
        """批量确认（逐项提交；允许部分成功；操作前显示计划）。"""
        cluster_ids = self._selected_cluster_ids()
        person_id = self._target_person_id()
        if person_id is None:
            self._detail_info_missing_target()
            return
        if not cluster_ids:
            self._feedback_label.setText(text.CLUSTER_PAIRING_NO_SELECTION)
            return
        plan = self._plan_confirm(cluster_ids, person_id)
        if not self._show_batch_plan(plan, text.CLUSTER_PAIRING_CONFIRM_BUTTON):
            return
        outcomes: list[str] = []
        succeeded = skipped = failed = 0
        person_name = self._person_combo.currentText()
        for cluster_id, label, action, assignment_id in plan:
            try:
                if action == "confirm" and assignment_id is not None:
                    self._workbench_service.confirm(
                        ConfirmAssignmentCommand(UUID(assignment_id)),
                    )
                elif action == "assign":
                    self._workbench_service.assign_person(
                        AssignClusterPersonCommand(
                            cluster_id=cluster_id, person_id=person_id,
                        ),
                        actor=HUMAN_ACTOR,
                    )
                else:
                    skipped += 1
                    continue
                succeeded += 1
            except Exception as exc:  # noqa: BLE001 - per-item boundary（§3.3）
                failed += 1
                outcomes.append(f"失败[{cluster_id}]: {exc}")
        self._feedback_label.setText(
            text.CLUSTER_PAIRING_BATCH_DONE.format(
                succeeded=succeeded, skipped=skipped, failed=failed,
            )
            + f" → {person_name}"
            + ("；" + "；".join(outcomes) if outcomes else "")
        )
        self.refresh()

    def _on_reject_clicked(self) -> None:
        """批量拒绝（§3.3：作用对象是簇×人员配对；保留既有拒绝规则）。"""
        cluster_ids = self._selected_cluster_ids()
        person_id = self._target_person_id()
        if person_id is None:
            self._detail_info_missing_target()
            return
        if not cluster_ids:
            self._feedback_label.setText(text.CLUSTER_PAIRING_NO_SELECTION)
            return
        assignments = self._assignments_by_cluster()
        person_name = self._person_combo.currentText()
        cluster_labels = self._cluster_labels()
        plan: list[tuple[UUID, str, str, str | None]] = []
        for cluster_id in cluster_ids:
            label = cluster_labels.get(cluster_id, str(cluster_id))
            assignment = assignments.get(cluster_id)
            if assignment is None or assignment.person_id != person_id:
                plan.append((cluster_id, label, "skip",
                             text.CLUSTER_PAIRING_REJECT_NO_PAIR))
            elif assignment.status == "confirmed":
                plan.append((cluster_id, label, "skip",
                             text.CLUSTER_PAIRING_REJECT_CONFIRMED))
            elif assignment.id is not None:
                plan.append((cluster_id, label, "reject", str(assignment.id)))
        if not self._show_batch_plan(
            plan, text.CLUSTER_PAIRING_REJECT_BUTTON,
            extra_note=text.PAIRING_WORKBENCH_REJECT_IMPACT_NOTE,
        ):
            return
        outcomes: list[str] = []
        succeeded = skipped = failed = 0
        for cluster_id, _label, action, assignment_id in plan:
            if action == "skip":
                skipped += 1
                continue
            try:
                if action == "reject" and assignment_id is not None:
                    self._workbench_service.reject(
                        RejectAssignmentCommand(UUID(assignment_id)),
                        actor=HUMAN_ACTOR,
                    )
                succeeded += 1
            except Exception as exc:  # noqa: BLE001 - per-item boundary（§3.3）
                failed += 1
                outcomes.append(f"失败[{cluster_id}]: {exc}")
        self._feedback_label.setText(
            text.CLUSTER_PAIRING_BATCH_DONE.format(
                succeeded=succeeded, skipped=skipped, failed=failed,
            )
            + f" → {person_name}"
            + ("；" + "；".join(outcomes) if outcomes else "")
        )
        self.refresh()

    def _show_batch_plan(
        self,
        plan: list[tuple[UUID, str, str, str | None]],
        action: str,
        extra_note: str | None = None,
    ) -> bool:
        """操作前显示对象范围、目标与将执行/跳过的项目（§3.3 预检）。

        条目 = (cluster_id, 展示标签, 动作, 附加信息)——skip 动作的附加信息
        是跳过原因，其余为待操作行 id 的字符串形态（可为 None）。
        """
        lines = [f"操作：{action}（{len(plan)} 项）"]
        for _cluster_id, label, kind, extra in plan:
            if kind == "skip":
                lines.append(f"· 跳过 {label}（{extra}）")
            else:
                lines.append(f"· 执行 {label}")
        if extra_note:
            lines.append(extra_note)
        box = QMessageBox(self)
        box.setWindowTitle(text.CLUSTER_PAIRING_CONFIRM_PLAN_TITLE)
        box.setText("\n".join(lines))
        box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Ok

    def _detail_info_missing_target(self) -> None:
        self._feedback_label.setText(text.CLUSTER_PAIRING_NO_TARGET)

    # ── 忽略 / 恢复（照片级，逐项提交） ──────────────────────────────────

    def _selected_photo_ids(self) -> list[UUID]:
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self._photo_grid.selectedItems()
            if isinstance(item.data(Qt.ItemDataRole.UserRole), UUID)
        ]

    def _on_ignore_clicked(self) -> None:
        """忽略所选照片（代际作用域；同步撤销既有投影，逐项反馈）。"""
        cluster_run_id = self._generation_combo.currentData()
        photo_ids = self._selected_photo_ids()
        if cluster_run_id is None or not photo_ids:
            self._feedback_label.setText(
                text.CLUSTER_PAIRING_NO_SELECTION if cluster_run_id is not None
                else text.CLUSTER_RESULTS_EMPTY
            )
            return
        if not self._confirm_scope(
            text.CLUSTER_PAIRING_IGNORE_SCOPE.format(count=len(photo_ids)),
        ):
            return
        result = self._ignore_service.ignore_photos(
            IgnorePhotosCommand(cluster_run_id=cluster_run_id, photo_ids=tuple(photo_ids)),
        )
        self._report_ignore_result(result, verb="忽略")
        self.refresh()

    def _on_restore_clicked(self) -> None:
        """恢复所选照片（只恢复参与资格，不回溯投影；逐项反馈）。"""
        cluster_run_id = self._generation_combo.currentData()
        photo_ids = self._selected_photo_ids()
        if cluster_run_id is None or not photo_ids:
            self._feedback_label.setText(
                text.CLUSTER_PAIRING_NO_SELECTION if cluster_run_id is not None
                else text.CLUSTER_RESULTS_EMPTY
            )
            return
        if not self._confirm_scope(
            text.CLUSTER_PAIRING_RESTORE_SCOPE.format(count=len(photo_ids)),
        ):
            return
        result = self._ignore_service.restore_photos(
            RestorePhotosCommand(cluster_run_id=cluster_run_id, photo_ids=tuple(photo_ids)),
        )
        self._report_ignore_result(result, verb="恢复")
        self.refresh()

    def _confirm_scope(self, message: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(text.CLUSTER_PAIRING_CONFIRM_PLAN_TITLE)
        box.setText(message)
        box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Ok

    def _report_ignore_result(self, result, *, verb: str) -> None:
        """逐项结果反馈（§3.3：成功/跳过/失败，不把部分成功报成整批）。"""
        details = []
        for item in result.outcomes:
            if item.outcome == "skipped":
                details.append(f"跳过[{item.reason}]")
            elif item.outcome == "failed":
                details.append(f"失败[{item.reason}]")
            elif verb == "忽略" and item.revoked_projections:
                details.append(f"撤销投影 {item.revoked_projections} 条")
        self._feedback_label.setText(
            text.CLUSTER_PAIRING_BATCH_DONE.format(
                succeeded=result.succeeded_count,
                skipped=result.skipped_count,
                failed=result.failed_count,
            )
            + f"（{verb}）"
            + ("；" + "；".join(details) if details else "")
        )

    # ── 详图（上一张 / 下一张，§5.4） ────────────────────────────────────

    def _on_photo_double_clicked(self, item: QListWidgetItem) -> None:
        """打开非模态详图；上一张/下一张在本组照片间切换。"""
        photo_ids = [
            self._photo_grid.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self._photo_grid.count())
        ]
        photo_id = item.data(Qt.ItemDataRole.UserRole)
        if photo_id not in photo_ids:
            return
        self._detail_photos = photo_ids
        self._detail_index = photo_ids.index(photo_id)
        self._open_detail()

    def _open_detail(self) -> None:
        photo_id = self._detail_photos[self._detail_index]
        photo = self._build_photo_stub(photo_id)
        if photo is None:
            # P6：未命中不再静默——给可见反馈，保持当前详图与索引不动。
            self._show_detail_photo_missing()
            return
        if self._detail_dialog is None:
            self._detail_dialog = PhotoDetailDialog(
                photo,
                thumbnail_path=self._thumbnail_paths.get(photo_id),
                parent=self,
                auto_load_hd=True,
            )
            # P6：详图生命周期绑定导航可用性——任何关闭路径（accept/
            # reject/标题栏/close）经 finished 信号统一回到禁用态。
            self._detail_dialog.finished.connect(self._on_detail_dialog_finished)
        else:
            # replace_photo 自动重启受控解码（导航模式契约）；缩略图已知时
            # 先占位再解码（P12：导航不再白屏等待高清）。
            self._detail_dialog.replace_photo(
                photo, thumbnail_path=self._thumbnail_paths.get(photo_id),
            )
        self._detail_dialog.show()
        self._detail_dialog.raise_()
        self._set_detail_nav_enabled(True)

    def _show_detail_photo_missing(self) -> None:
        """P6：详图目标已不在当前结果快照中——可见反馈，绝不静默。"""
        self._feedback_label.setText(text.CLUSTER_DETAIL_PHOTO_MISSING)

    def _set_detail_nav_enabled(self, enabled: bool) -> None:
        """P6：「上一张/下一张」随详图生命周期启停（仅配对模式存在按钮）。"""
        if not self._pairing_active:
            return
        self._detail_prev_button.setEnabled(enabled)
        self._detail_next_button.setEnabled(enabled)

    def _close_detail(self) -> None:
        """P6：快照失效路径（refresh/切代际）关闭已打开的详图。

        关闭经 QDialog.close() → finished 信号统一走
        :meth:`_on_detail_dialog_finished`，导航按钮同步回到禁用态。
        """
        if self._detail_dialog is not None:
            self._detail_dialog.close()

    def _on_detail_dialog_finished(self, _result: int) -> None:
        """P6：详图任何结束路径——导航回到禁用态并释放对话框引用。"""
        dialog = self._detail_dialog
        self._detail_dialog = None
        self._set_detail_nav_enabled(False)
        if dialog is not None:
            # 无 WA_DeleteOnClose：显式排程销毁，避免反复开关累积隐藏子对话框。
            dialog.deleteLater()

    def _build_photo_stub(self, photo_id: UUID):
        """Construct a display Photo from the loaded member data."""
        from photo_archiver.domain import Photo, PhotoPath, PhotoPathBase

        member = next(
            (
                m for detail in (self._current.clusters if self._current else ())
                for m in detail.members if m.photo_id == photo_id
            ),
            None,
        )
        if member is None or not member.photo_path:
            return None
        try:
            path = PhotoPath(
                Path(member.photo_path), base=PhotoPathBase.ABSOLUTE,
            )
        except Exception:  # noqa: BLE001 - 相对/非法路径不构成详图打开
            return None
        name = member.photo_path.replace("\\", "/").rsplit("/", 1)[-1]
        return Photo(
            path=path, original_name=name, captured_at=member.captured_at,
        )

    def _on_detail_prev_next(self, offset: int) -> None:
        """§5.4 上一张/下一张：在本组照片范围内循环切换。

        P6：目标照片构建不出详图（已不在当前结果中）时给可见反馈且不推进
        索引——连续点击不会越过失效项悄悄跳位，也不会静默无效。
        """
        if self._detail_dialog is None or not self._detail_photos:
            return
        candidate = (self._detail_index + offset) % len(self._detail_photos)
        if self._build_photo_stub(self._detail_photos[candidate]) is None:
            self._show_detail_photo_missing()
            return
        self._detail_index = candidate
        self._open_detail()
