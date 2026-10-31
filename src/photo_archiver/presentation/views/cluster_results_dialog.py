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
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.commands.pairing import (
    RejectAssignmentCommand,
    StartSuggestPairingsCommand,
)
from photo_archiver.application.commands.photo_ignore import (
    IgnorePhotosCommand,
    RestorePhotosCommand,
)
from loguru import logger
from photo_archiver.application.dtos.cluster_results import ClusterRunResults
from photo_archiver.application.services import ClusterResultsService
from photo_archiver.presentation.task_coordinator import TaskCoordinator
from photo_archiver.workers.application_tasks import (
    PairingBatchFinalizeTask,
    PairingBatchItem,
    PairingBatchOutcome,
)
from photo_archiver.workers.events import (
    TaskCancelled,
    TaskCompleted,
    TaskFailed,
    TaskProgress,
    TaskStarted,
)
from photo_archiver.workers.qt_executor import QtWorkerExecutor, QtWorkerRunnable
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
from photo_archiver.presentation.visual_style import (
    ROLE_DANGER,
    ROLE_PRIMARY,
    ROLE_SUCCESS,
    assign_role,
    set_badge_severity,
    style_card,
    style_card_list,
)


def _format_moment(moment) -> str:
    """Render a persisted datetime for the UI（无时区转换，原样展示）。"""
    return moment.strftime("%Y-%m-%d %H:%M") if moment is not None else text.CLUSTER_RESULTS_NO_CAPTURED


# M20 run 状态徽章 severity 映射（taskbook-4 v2 §3；文字承载状态 §10-7，
# 不可点击 DEC-08=A）。未知状态回退 neutral（不崩溃）。
_RUN_STATUS_SEVERITY = {
    "created": "neutral",
    "running": "info",
    "completed": "success",
    "failed": "danger",
    "cancelled": "warning",
}

# 配对决策五态 → Badge severity（taskbook-5 §2.1 派生提案；rejected 态在
# active 集合外实际不出现，映射仅登记；未知状态回退 neutral 不崩溃）。
_ASSIGNMENT_SEVERITY = {
    "suggested": "warning",
    "auto_confirmed": "info",
    "confirmed": "success",
    "rejected": "danger",
    "unassigned": "neutral",
}


class _DetailIgnoreController:
    """详图忽略/恢复控制器（Owner 2026-10-31）。

    把 :class:`PhotoDetailDialog` 的忽略/恢复按钮接到宿主
    :class:`ClusterResultsDialog` 的代际作用域服务：查询态＝当前选中簇的
    ignored 集合；切换＝单照片服务调用＋原位重渲染（不关详图）。协议与
    photo_detail_dialog 的 ``ignore_controller`` 参数对齐。
    """

    def __init__(self, dialog: "ClusterResultsDialog") -> None:
        self._dialog = dialog

    def is_ignored(self, photo_id) -> bool:
        detail = self._dialog.current_cluster_detail()
        return detail is not None and photo_id in set(detail.ignored_photo_ids)

    def toggle(self, photo_id, ignore: bool) -> str | None:
        return self._dialog.toggle_detail_ignore(photo_id, ignore)


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
        task_coordinator: TaskCoordinator | None = None,
        task_executor: QtWorkerExecutor | None = None,
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
        # 批量终审后台化（Owner 2026-10-31 卡顿修复·A）：注入协调器+执行器后
        # 批量确认/批量通过走任务管线（进度/取消/忙碌准入）；缺省 None 保持
        # 同步回退路径（既有测试与独立使用零变化）。
        self._task_coordinator = task_coordinator
        self._task_executor = task_executor
        self._busy = False
        self._batch_person_suffix = ""
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
        # Owner 2026-10-31：详图内忽略/恢复——控制器把详图按钮接到本对话框
        # 的代际作用域服务（未注入忽略服务时按钮自动隐藏）。
        self._detail_ignore = _DetailIgnoreController(self)
        self._build_ui()
        if thumbnail_source is not None:
            # Connect once — members of many photos register many rows and a
            # per-row connect would multiply every arriving signal.
            thumbnail_source.thumbnail_loaded.connect(self._attach_thumbnail)
        self.refresh()
        # Owner 2026-10-31：批量终审 UX 挂协调器信号（单一来源、可重连）——
        # 模态对话框关闭后任务继续在后台执行，重开对话框自动重新附着到
        # 在跑批次（此前 UX 连在 runnable 信号上，重开即全部失联：进度条
        # 不显示 + 点击只剩准入拒绝提示）。
        if self._task_coordinator is not None:
            self._task_coordinator.started.connect(self._on_batch_started)
            self._task_coordinator.progress.connect(self._on_batch_progress)
            self._task_coordinator.terminal.connect(self._on_batch_terminal)
            self._reattach_running_batch()

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

        # M2/M20（参考图基线）：摘要行（计数）＋run 状态徽章（severity 映射
        # 见 _RUN_STATUS_SEVERITY；文字承载状态，不可点击 DEC-08=A）。
        summary_row = QHBoxLayout()
        self._generation_summary = QLabel(self)
        self._generation_summary.setWordWrap(True)
        summary_row.addWidget(self._generation_summary)
        summary_row.addStretch()
        self._run_status_badge = QLabel(self)
        set_badge_severity(self._run_status_badge, "neutral")
        self._run_status_badge.setVisible(False)
        summary_row.addWidget(self._run_status_badge)
        layout.addLayout(summary_row)
        # 落点 4（taskbook-5 §5）：run 照片处理状态行单一 neutral 徽章化
        # （整行不拆分、不可点击 DEC-08=A；七计数文本语义零变化）。
        self._run_status_label = QLabel(self)
        set_badge_severity(self._run_status_label, "neutral")
        self._run_status_label.setWordWrap(True)
        self._run_status_label.setVisible(self._pairing_active)
        layout.addWidget(self._run_status_label)
        # 批量操作/生成建议的逐项结果反馈（独立于代际摘要，不随刷新清除）。
        # 落点 5（taskbook-5 §5）：反馈行 Card 容器化（文字零变化）。
        self._feedback_card = QFrame(self)
        style_card(self._feedback_card)
        feedback_layout = QVBoxLayout(self._feedback_card)
        feedback_layout.setContentsMargins(8, 6, 8, 6)
        # 批量终审进度条（Owner 2026-10-31：移入反馈卡＝「已有批量终审在
        # 执行…」同一位置）：执行期显示（started→可见，首个进度前＝脉冲
        # 未知态；completed/failed/cancelled→隐藏），文字行在其下方。
        self._batch_progress = QProgressBar(self._feedback_card)
        self._batch_progress.setObjectName("BatchProgress")
        self._batch_progress.setFormat("%v / %m（%p%）")
        self._batch_progress.setVisible(False)
        feedback_layout.addWidget(self._batch_progress)
        self._feedback_label = QLabel(self._feedback_card)
        self._feedback_label.setWordWrap(True)
        self._feedback_label.setVisible(self._pairing_active)
        feedback_layout.addWidget(self._feedback_label)
        self._feedback_card.setVisible(self._pairing_active)
        layout.addWidget(self._feedback_card)

        body = QHBoxLayout()
        self._cluster_list = QListWidget(self)
        self._cluster_list.setMinimumWidth(300)
        # M9（布局重组解释内的容器样式化）：簇列表卡片化（QSS #CardList）。
        style_card_list(self._cluster_list)
        # Owner 2026-10-31：不取键盘焦点——原生焦点矩形在选中卡片内缘画黑框
        # （outline:none 双保险于 QSS）；鼠标选择/高亮语义不变。
        self._cluster_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
            style_card_list(self._member_list)
            self._member_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
        # 落点 3（taskbook-5 §5）：配对状态行徽章化——severity 按决策五态映射，
        # 状态文字保留在徽章内（§10-7 非仅色）；confirmed 扩散通道零触碰。
        decision_row = QHBoxLayout()
        decision_row.addWidget(QLabel(text.CLUSTER_PAIRING_DECISION_STATUS_LABEL, pane))
        self._decision_badge = QLabel(pane)
        set_badge_severity(self._decision_badge, "neutral")
        decision_row.addWidget(self._decision_badge)
        decision_row.addStretch()
        layout.addLayout(decision_row)

        photos_row = QHBoxLayout()
        photos_row.addWidget(QLabel(text.CLUSTER_PAIRING_PHOTOS_LABEL, pane))
        photos_row.addStretch()
        # 任务书阶段 C（D4=B1）：上一张/下一张移入详图对话框（覆盖式 ‹ › +
        # ←/→ + 计数），面板不再持有常驻导航按钮（P6 生命周期语义随之内化）。
        layout.addLayout(photos_row)
        self._photo_grid = QListWidget(self)
        self._photo_grid.setViewMode(QListWidget.ViewMode.IconMode)
        self._photo_grid.setIconSize(QSize(96, 96))
        self._photo_grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._photo_grid.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection,
        )
        self._photo_grid.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._photo_grid.itemDoubleClicked.connect(self._on_photo_double_clicked)
        layout.addWidget(self._photo_grid, 1)

        # Owner 2026-10-31：忽略/恢复面板按钮撤除（详情内入口保留）。
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
        # 批量通过（Owner 2026-10-31 移至本行右侧标记位）：左侧簇列表多选后
        # 启用，确认前预演各组信息。
        self._batch_pass_button = QPushButton(
            text.CLUSTER_PAIRING_BATCH_PASS_BUTTON, pane,
        )
        self._batch_pass_button.clicked.connect(self._on_batch_pass_clicked)
        assign_role(self._batch_pass_button, ROLE_SUCCESS)
        self._batch_pass_button.setEnabled(False)
        self._cluster_list.itemSelectionChanged.connect(
            self._render_batch_pass_state,
        )
        person_row.addWidget(self._confirm_button)
        person_row.addWidget(self._reject_button)
        person_row.addWidget(self._batch_pass_button)
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
            self._run_status_badge.setVisible(False)
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
            self._run_status_badge.setVisible(False)
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
        """§5.3 数据集级人脸数与可确定的处理状态（未知不并入 0 脸）。

        任务书 §3 A2：口径随代际数据集（single_run=锚点运行；library=各照片
        最新一次尝试），由结果服务按 cluster_run 参数分派。
        """
        if not self._pairing_active or self._current is None:
            return
        summary = self._results_service.run_photo_outcome_summary(
            self._current.cluster_run,
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
        self._generation_summary.setText(text.STATUS_CLUSTER_SUMMARY.format(
            clusters=run.cluster_count,
            members=run.member_count,
            excluded=run.excluded_count,
        ))
        # M20：run 状态从摘要后缀改为独立徽章（文字承载，severity 映射确定性）。
        self._run_status_badge.setText(text.cluster_run_status_label(run.status))
        set_badge_severity(
            self._run_status_badge,
            _RUN_STATUS_SEVERITY.get(run.status, "neutral"),
        )
        self._run_status_badge.setVisible(True)
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
        # Owner 2026-10-31：切簇时目标人员自动跟随该组当前指派（suggested/
        # auto_confirmed/confirmed）——按 person_id 值扫描选中（QVariant
        # findData 对 UUID 不可靠，同 _render_batch_combo 教训）；未指派组
        # 保持当前选择不动。
        if assignment is not None and assignment.person_id is not None:
            for index in range(self._person_combo.count()):
                if self._person_combo.itemData(index) == assignment.person_id:
                    self._person_combo.setCurrentIndex(index)
                    break
        decision_text = (
            text.PAIRING_WORKBENCH_ASSIGNMENT_LABEL.get(assignment.status, "?")
            if assignment is not None else text.CLUSTER_PAIRING_UNMATCHED
        )
        assignment_status = assignment.status if assignment is not None else "unassigned"
        if assignment is not None:
            # 建议行模板携带来源与分值占位（实机曾因缺 kwargs 渲染崩溃）。
            if assignment.status == "suggested":
                decision_text = decision_text.format(
                    source=text.PAIRING_WORKBENCH_SOURCE_LABELS.get(
                        assignment.source, assignment.source,
                    ),
                    score=(
                        f"{assignment.score:.2f}"
                        if assignment.score is not None else "—"
                    ),
                )
            else:
                decision_text = decision_text.format(
                    person=self._person_name(assignment.person_id),
                )
        # 落点 3：配对状态行徽章化——状态文字整体进徽章（含 person 填充），
        # severity 按五态映射；忽略照片备注保留在详情信息行（文字承载）。
        self._decision_badge.setText(decision_text)
        set_badge_severity(
            self._decision_badge,
            _ASSIGNMENT_SEVERITY.get(assignment_status, "neutral"),
        )
        # Owner 2026-10-31 防呆：已确认组＝确认键变「已确认」且不可点
        # （改派仍可经目标人员+确认走人工路径？不——confirmed 行的再次确认
        # 无意义，确认键保持禁用；改派需先经未来「解除」入口，此处不扩权）。
        if assignment_status == "confirmed":
            self._confirm_button.setText(text.CLUSTER_PAIRING_CONFIRMED_BUTTON)
            self._confirm_button.setEnabled(False)
        else:
            self._confirm_button.setText(text.CLUSTER_PAIRING_CONFIRM_BUTTON)
            self._confirm_button.setEnabled(bool(self._persons))
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
            + ignored_note
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
        # Owner 2026-10-31 卡顿修复·A：批量执行下放后台任务管线（进度/取消/
        # 忙碌准入）；未注入协调器（测试/独立使用）保持同步回退。
        self._dispatch_batch(
            text.CLUSTER_PAIRING_CONFIRM_BUTTON,
            self._items_from_plan(plan, person_id=str(person_id)),
            person_name=self._person_combo.currentText(),
        )

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
        exec_lines: list[str] = []
        skip_by_reason: dict[str, list[str]] = {}
        for _cluster_id, label, kind, extra in plan:
            if kind == "skip":
                reason = extra if extra is not None else "—"
                skip_by_reason.setdefault(reason, []).append(label)
            else:
                exec_lines.append(f"· 执行 {label}")
        lines = [
            f"操作：{action}（共 {len(plan)} 项：执行 {len(exec_lines)}、"
            f"跳过 {len(plan) - len(exec_lines)}）",
        ]
        lines.extend(exec_lines)
        # Owner 2026-10-31 防呆：已通过的组按原因归组提示（如「已确认，
        # 无需重复」＝已通过；「未指派人员」＝无法直接通过），只确认其余。
        for reason, labels in skip_by_reason.items():
            lines.append(f"· 跳过（{reason}）：{'、'.join(labels)}")
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

    # ── 批量通过（Owner 2026-10-31：组级人工终审）────────────────────────

    def _render_batch_pass_state(self) -> None:
        """批量通过随簇多选启用/禁用（0 选区或全为已确认组＝禁用，防呆）。"""
        selected = self._selected_cluster_ids()
        if not selected:
            self._batch_pass_button.setEnabled(False)
            return
        assignments = self._assignments_by_cluster()
        actionable = any(
            (assignment := assignments.get(cluster_id)) is not None
            and assignment.status != "confirmed"
            for cluster_id in selected
        )
        self._batch_pass_button.setEnabled(actionable)

    def _plan_batch_pass(
        self, cluster_ids: list[UUID],
    ) -> list[tuple[UUID, str, str, str | None]]:
        """批量通过预演（§3.3：操作前显示将执行与跳过的组）。

        每组：suggested → confirm（确认建议行）；auto_confirmed → 按本组
        当前指派人 assign_person（人工明确选择＝终审，同批量确认对自动确认
        行的既有路径）；confirmed / 未指派 / 已拒绝 → 跳过（原因进预演）。
        条目 = (cluster_id, 展示标签, 动作, 附加信息)——confirm 携建议行 id、
        promote 携本组指派人 id（字符串形态），skip 携原因。
        """
        assignments = self._assignments_by_cluster()
        cluster_labels = self._cluster_labels()
        plan: list[tuple[UUID, str, str, str | None]] = []
        for cluster_id in cluster_ids:
            label = cluster_labels.get(cluster_id, str(cluster_id))
            assignment = assignments.get(cluster_id)
            if assignment is not None and assignment.status == "confirmed":
                plan.append((cluster_id, label, "skip",
                             text.CLUSTER_PAIRING_PASS_SKIP_CONFIRMED))
            elif (
                assignment is not None
                and assignment.status == "suggested"
                and assignment.id is not None
            ):
                plan.append((cluster_id, label, "confirm", str(assignment.id)))
            elif (
                assignment is not None
                and assignment.status == "auto_confirmed"
                and assignment.person_id is not None
            ):
                plan.append((cluster_id, label, "promote", str(assignment.person_id)))
            else:
                plan.append((cluster_id, label, "skip",
                             text.CLUSTER_PAIRING_PASS_SKIP_UNASSIGNED))
        return plan

    def _on_batch_pass_clicked(self) -> None:
        """批量通过：把选中各组标记为人工处理完成（逐项提交；允许部分成功）。

        确认前经 _show_batch_plan 预演各组信息；执行后统计进反馈行并刷新。
        """
        cluster_ids = self._selected_cluster_ids()
        if not cluster_ids:
            self._feedback_label.setText(text.CLUSTER_PAIRING_NO_SELECTION)
            return
        plan = self._plan_batch_pass(cluster_ids)
        if not self._show_batch_plan(plan, text.CLUSTER_PAIRING_BATCH_PASS_BUTTON):
            return
        self._dispatch_batch(
            text.CLUSTER_PAIRING_BATCH_PASS_BUTTON,
            self._items_from_plan(plan),
        )

    # ── 批量终审执行（Owner 2026-10-31 卡顿修复·A：后台管线 + 同步回退）──

    def _items_from_plan(
        self,
        plan: list[tuple[UUID, str, str, str | None]],
        person_id: str | None = None,
    ) -> tuple[PairingBatchItem, ...]:
        """把预演条目转成任务层计划项（action/payload/person_id 同构）。"""
        return tuple(
            PairingBatchItem(
                action=action,
                cluster_id=cluster_id,
                label=label,
                payload=payload,
                person_id=person_id,
            )
            for cluster_id, label, action, payload in plan
        )

    def _dispatch_batch(
        self,
        action: str,
        items: tuple[PairingBatchItem, ...],
        person_name: str = "",
    ) -> None:
        """执行一批终审项：注入协调器＝后台任务管线，否则同步回退。

        后台路径经 TaskCoordinator 准入（忙碌拒绝）、簇粒度进度进反馈行、
        终态（完成/失败/取消）后对话框自行刷新；主窗口经既有通用接线刷新
        照片墙与工作区状态。
        """
        if self._busy:
            logger.info(
                "PairingBatch dispatch ignored (busy): action={}", action,
            )
            return
        if self._task_coordinator is None or self._task_executor is None:
            logger.info(
                "PairingBatch sync fallback: action={} items={}", action, len(items),
            )
            self._execute_batch_now(action, items, person_name)
            return
        reservation = self._task_coordinator.reserve(action)
        if reservation is None:
            logger.warning(
                "PairingBatch REFUSED at admission: action={} items={}", action, len(items),
            )
            self._feedback_label.setText(text.CLUSTER_PAIRING_BATCH_BUSY)
            return
        logger.info(
            "PairingBatch admitted: action={} items={}", action, len(items),
        )
        self._batch_person_suffix = (
            f" → {person_name}"
            if action == text.CLUSTER_PAIRING_CONFIRM_BUTTON and person_name
            else ""
        )
        # 防呆：reserve 成功即同步置忙并显示进度（不等 started 事件——那之间
        # 按钮仍可点，二次点击会撞出「已有批量终审在执行」提示）。
        self._show_batch_running_state()
        runnable = self._task_executor.submit(
            PairingBatchFinalizeTask(self._workbench_service, items, action),  # type: ignore[arg-type]  # WorkerTask[PairingBatchOutcome] vs [object] generics variance
        )
        self._task_coordinator.bind(runnable, self._connect_batch_route)

    def _connect_batch_route(
        self,
        runnable: QtWorkerRunnable,
        started,
        progress,
        completed,
        failed,
        cancelled=None,
    ) -> None:
        """Wire worker events to the coordinator route only.

        对话框 UX 一律经协调器信号（构造期连接、事件带 task_name 过滤）——
        对话框关闭重开也能重新附着在跑批次；不走 runnable 直连。
        """
        runnable.signals.started.connect(started)
        runnable.signals.progress.connect(progress)
        runnable.signals.completed.connect(completed)
        runnable.signals.failed.connect(failed)
        if cancelled is not None:
            runnable.signals.cancelled.connect(cancelled)

    def _execute_batch_now(
        self,
        action: str,
        items: tuple[PairingBatchItem, ...],
        person_name: str = "",
    ) -> None:
        """Synchronous fallback（未注入协调器）：同一任务对象在调用线程执行。"""
        self._batch_person_suffix = (
            f" → {person_name}"
            if action == text.CLUSTER_PAIRING_CONFIRM_BUTTON and person_name
            else ""
        )
        outcome = PairingBatchFinalizeTask(
            self._workbench_service, items, action,
        ).execute()
        self._apply_batch_outcome(outcome)

    def _apply_batch_outcome(self, outcome: PairingBatchOutcome) -> None:
        """Render one PairingBatchOutcome into the feedback line and refresh."""
        self._feedback_label.setText(
            text.CLUSTER_PAIRING_BATCH_DONE.format(
                succeeded=outcome.succeeded,
                skipped=outcome.skipped,
                failed=outcome.failed,
            )
            + self._batch_person_suffix
            + ("；" + "；".join(outcome.outcomes) if outcome.outcomes else "")
        )
        self.refresh()

    def set_busy(self, busy: bool) -> None:
        """批量终审在飞时禁用决策面（与窗口级任务准入一致）。"""
        self._busy = busy
        for widget in (
            self._confirm_button, self._reject_button,
            self._batch_pass_button, self._generate_button,
            self._person_combo, self._generation_combo,
        ):
            widget.setEnabled(not busy)
        if not busy:
            self._render_batch_pass_state()

    def _is_pairing_batch_event(
        self,
        event: TaskStarted | TaskProgress | TaskCompleted | TaskFailed | TaskCancelled,
    ) -> bool:
        """协调器承载全部窗口任务——UX 只消费批量终审事件。"""
        return event.task_name == "pairing_batch"

    def _show_batch_running_state(self) -> None:
        """忙碌态 + 脉冲进度条 + 进行中文案（分发期/重附着共用）。"""
        self.set_busy(True)
        self._feedback_label.setText(text.CLUSTER_PAIRING_BATCH_RUNNING)
        # 首个进度事件前总数未知＝脉冲未知态（min=max=0 的 busy bar）。
        self._batch_progress.setRange(0, 0)
        self._batch_progress.setVisible(True)

    def _reattach_running_batch(self) -> None:
        """构造期检测：协调器正被批量终审占用（前一个对话框会话派发）→
        立即附着忙碌态；后续进度/终态经协调器信号继续驱动本对话框。"""
        coordinator = self._task_coordinator
        if coordinator is None:
            return
        if coordinator.is_busy and coordinator.label in (
            text.CLUSTER_PAIRING_CONFIRM_BUTTON,
            text.CLUSTER_PAIRING_BATCH_PASS_BUTTON,
        ):
            self._show_batch_running_state()

    def _on_batch_started(self, event: TaskStarted) -> None:
        if not self._is_pairing_batch_event(event):
            return
        self._show_batch_running_state()

    def _on_batch_progress(self, event: TaskProgress) -> None:
        if not self._is_pairing_batch_event(event):
            return
        if event.current is None or event.total is None:
            return
        self._feedback_label.setText(
            text.CLUSTER_PAIRING_BATCH_PROGRESS.format(
                current=event.current, total=event.total, message=event.message,
            )
        )
        self._batch_progress.setRange(0, event.total)
        self._batch_progress.setValue(event.current)

    def _on_batch_terminal(
        self, event: TaskCompleted | TaskFailed | TaskCancelled,
    ) -> None:
        if not self._is_pairing_batch_event(event):
            return
        self.set_busy(False)
        self._batch_progress.setVisible(False)
        if isinstance(event, TaskCompleted):
            # result 为 PairingBatchOutcome（任务层契约）。
            self._apply_batch_outcome(event.result)
        elif isinstance(event, TaskFailed):
            self._feedback_label.setText(
                f"{text.CLUSTER_PAIRING_BATCH_FAILED}：{event.error}"
            )
            # 部分项可能已提交——刷新到真实状态。
            self.refresh()
        else:
            self._feedback_label.setText(text.CLUSTER_PAIRING_BATCH_CANCELLED)
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

    # ── 详图内忽略/恢复（Owner 2026-10-31）───────────────────────────────

    def current_cluster_detail(self):
        """当前选中簇的明细（无选中/无快照＝None；控制器查询态用）。"""
        current = self._cluster_list.currentItem()
        cluster_id = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        if self._current is None or cluster_id is None:
            return None
        return next(
            (d for d in self._current.clusters if d.cluster_id == cluster_id), None,
        )

    def is_photo_ignored(self, photo_id) -> bool:
        """详图查询：当前簇内该照片是否已忽略（_DetailIgnoreController 用）。"""
        detail = self.current_cluster_detail()
        return detail is not None and photo_id in set(detail.ignored_photo_ids)

    def toggle_detail_ignore(self, photo_id, ignore: bool) -> str | None:
        """详图内忽略/恢复单张照片：服务调用＋原位重渲染，不关详图。

        P6 快照失效仅限 refresh/切代际——本路径重载**同一代际**快照并恢复
        当前簇选中，``_detail_photos`` 集合不变，详图可继续导航。返回反馈
        文本（成功/跳过/失败；无代际或无服务＝None）。
        """
        cluster_run_id = self._generation_combo.currentData()
        if cluster_run_id is None or self._ignore_service is None:
            return None
        if ignore:
            result = self._ignore_service.ignore_photos(
                IgnorePhotosCommand(cluster_run_id=cluster_run_id, photo_ids=(photo_id,)),
            )
            verb = "忽略"
        else:
            result = self._ignore_service.restore_photos(
                RestorePhotosCommand(cluster_run_id=cluster_run_id, photo_ids=(photo_id,)),
            )
            verb = "恢复"
        current_detail = self.current_cluster_detail()
        selected_cluster_id = (
            current_detail.cluster_id if current_detail is not None else None
        )
        self._current = self._results_service.results(cluster_run_id)
        self._render_run_status(cluster_run_id)
        self._render_clusters()
        # _render_clusters 会重置到第 0 行——恢复到原选中簇（重触发渲染）。
        if selected_cluster_id is not None:
            for row in range(self._cluster_list.count()):
                item = self._cluster_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == selected_cluster_id:
                    self._cluster_list.setCurrentRow(row)
                    break
        outcome = result.outcomes[0] if result.outcomes else None
        if outcome is None:
            return None
        if outcome.outcome == "skipped":
            return text.CLUSTER_DETAIL_IGNORE_SKIPPED.format(reason=outcome.reason)
        if outcome.outcome == "failed":
            return text.CLUSTER_DETAIL_IGNORE_FAILED.format(reason=outcome.reason)
        return text.CLUSTER_DETAIL_IGNORE_DONE.format(verb=verb)

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
                navigator=self,
                ignore_controller=self._detail_ignore,
            )
            # P6：详图生命周期绑定导航可用性——任何关闭路径（accept/
            # reject/标题栏/close）经 finished 信号统一回收。
            self._detail_dialog.finished.connect(self._on_detail_dialog_finished)
            self._detail_dialog.navigation_requested.connect(self._on_detail_prev_next)
        else:
            # replace_photo 自动重启受控解码（导航模式契约）；缩略图已知时
            # 先占位再解码（P12：导航不再白屏等待高清）。
            self._detail_dialog.replace_photo(
                photo, thumbnail_path=self._thumbnail_paths.get(photo_id),
            )
        self._detail_dialog.set_navigation_position(text.CLUSTER_DETAIL_NAV_POSITION.format(
            index=self._detail_index + 1, total=len(self._detail_photos),
        ))
        self._detail_dialog.show()
        self._detail_dialog.raise_()

    def _show_detail_photo_missing(self) -> None:
        """P6：详图目标已不在当前结果快照中——可见反馈，绝不静默。"""
        self._feedback_label.setText(text.CLUSTER_DETAIL_PHOTO_MISSING)

    def _close_detail(self) -> None:
        """P6：快照失效路径（refresh/切代际）关闭已打开的详图。

        关闭经 QDialog.close() → finished 信号统一走
        :meth:`_on_detail_dialog_finished`，导航随对话框销毁。
        """
        if self._detail_dialog is not None:
            self._detail_dialog.close()

    def _on_detail_dialog_finished(self, _result: int) -> None:
        """P6：详图任何结束路径——释放对话框引用（导航随对话框销毁）。"""
        dialog = self._detail_dialog
        self._detail_dialog = None
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
        # id 必须携带真实 photo_id（Owner 2026-10-31 详图内忽略/恢复依赖它；
        # 缺省自动生成的 UUID 会让服务按「无本代际成员资格」跳过）。
        return Photo(
            id=photo_id, path=path, original_name=name,
            captured_at=member.captured_at,
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
