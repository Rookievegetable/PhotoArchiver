"""Pairing workbench dialog — Stage E 身份指派与人工确认.

在 D-4 聚类结果之上叠加身份指派层：为选定聚类代际的每个簇展示当前
指派状态（待确认/已确认/已拒绝/未指派，自动建议与人工决策可区分），
支持生成建议、确认、拒绝、人工指派（改派）、解除映射、标记陌生人、
忽略组。操作为快速 SQLite 调用（Review 同步语义），无 Worker；每次
操作后重读持久化数据重渲染——Cluster 原始成员/排序永不在 UI 修改。
"""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.commands.pairing import (
    AssignClusterPersonCommand,
    ConfirmAssignmentCommand,
    RejectAssignmentCommand,
    SetClusterStateCommand,
    StartSuggestPairingsCommand,
    UnassignClusterCommand,
)
from photo_archiver.application.services import (
    ClusterResultsService,
    ListPersonsService,
    PairingWorkbenchService,
    SuggestPairingsService,
)
from photo_archiver.domain import ClusterPersonAssignment
from photo_archiver.presentation import ui_text as text


def _format_moment(moment) -> str:
    return moment.strftime("%Y-%m-%d %H:%M") if moment is not None else "—"


class PairingWorkbenchDialog(QDialog):
    """Identity-assignment workbench over one recognition run's generations."""

    def __init__(
        self,
        suggest_service: SuggestPairingsService,
        workbench_service: PairingWorkbenchService,
        results_service: ClusterResultsService,
        list_persons: ListPersonsService,
        recognition_run_id: UUID,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(text.PAIRING_WORKBENCH_TITLE)
        self.setMinimumSize(760, 520)
        self._suggest_service = suggest_service
        self._workbench_service = workbench_service
        self._results_service = results_service
        self._list_persons = list_persons
        self._recognition_run_id = recognition_run_id
        self._persons = list_persons.execute()
        self._assignments_by_cluster: dict[UUID, ClusterPersonAssignment] = {}
        self._selected_cluster_id: UUID | None = None
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        """Lay out the generation row, cluster list and the action pane."""
        layout = QVBoxLayout(self)

        hint = QLabel(text.PAIRING_WORKBENCH_HINT, self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        generation_row = QHBoxLayout()
        generation_row.addWidget(QLabel(text.PAIRING_WORKBENCH_GENERATION_LABEL, self))
        self._generation_combo = QComboBox(self)
        self._generation_combo.setMinimumWidth(320)
        self._generation_combo.currentIndexChanged.connect(self._on_generation_selected)
        generation_row.addWidget(self._generation_combo)
        self._generate_button = QPushButton(text.PAIRING_WORKBENCH_GENERATE_BUTTON, self)
        self._generate_button.clicked.connect(self._on_generate_clicked)
        generation_row.addWidget(self._generate_button)
        generation_row.addStretch()
        layout.addLayout(generation_row)

        self._status_label = QLabel(self)
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        body = QHBoxLayout()
        self._cluster_list = QListWidget(self)
        self._cluster_list.setMinimumWidth(300)
        self._cluster_list.currentItemChanged.connect(self._on_cluster_selected)
        body.addWidget(self._cluster_list, 2)

        action_pane = QWidget(self)
        action_layout = QVBoxLayout(action_pane)
        action_layout.addWidget(QLabel(text.PAIRING_WORKBENCH_MEMBER_LABEL, action_pane))
        self._person_combo = QComboBox(action_pane)
        self._person_combo.setMinimumWidth(220)
        action_layout.addWidget(self._person_combo)
        self._confirm_button = QPushButton(text.PAIRING_WORKBENCH_CONFIRM_BUTTON, action_pane)
        self._confirm_button.clicked.connect(self._on_confirm_clicked)
        self._reject_button = QPushButton(text.PAIRING_WORKBENCH_REJECT_BUTTON, action_pane)
        self._reject_button.clicked.connect(self._on_reject_clicked)
        self._assign_button = QPushButton(text.PAIRING_WORKBENCH_ASSIGN_BUTTON, action_pane)
        self._assign_button.clicked.connect(self._on_assign_clicked)
        self._unassign_button = QPushButton(text.PAIRING_WORKBENCH_UNASSIGN_BUTTON, action_pane)
        self._unassign_button.clicked.connect(self._on_unassign_clicked)
        for button in (self._confirm_button, self._reject_button,
                       self._assign_button, self._unassign_button):
            action_layout.addWidget(button)
        state_row = QHBoxLayout()
        self._unknown_button = QPushButton(text.PAIRING_WORKBENCH_UNKNOWN_BUTTON, action_pane)
        self._unknown_button.clicked.connect(lambda: self._on_state_clicked("unknown"))
        self._ignore_button = QPushButton(text.PAIRING_WORKBENCH_IGNORE_BUTTON, action_pane)
        self._ignore_button.clicked.connect(lambda: self._on_state_clicked("ignored"))
        state_row.addWidget(self._unknown_button)
        state_row.addWidget(self._ignore_button)
        action_layout.addLayout(state_row)
        action_layout.addStretch()
        body.addWidget(action_pane, 1)
        layout.addLayout(body, 1)

    # ── 数据 + 渲染 ─────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload generations, assignments and roster; keep the selection."""
        self._persons = self._list_persons.execute()
        selected = self._generation_combo.currentData()
        runs = self._results_service.list_cluster_runs(self._recognition_run_id)
        self._generation_combo.blockSignals(True)
        self._generation_combo.clear()
        for run in runs:
            self._generation_combo.addItem(
                text.PAIRING_WORKBENCH_GENERATION_ENTRY.format(
                    created_at=_format_moment(run.created_at),
                    status=text.cluster_run_status_label(run.status),
                    clusters=run.cluster_count,
                ),
                run.id,
            )
        if selected is not None:
            for index in range(self._generation_combo.count()):
                if self._generation_combo.itemData(index) == selected:
                    self._generation_combo.setCurrentIndex(index)
                    break
        if self._generation_combo.currentIndex() < 0 and self._generation_combo.count():
            self._generation_combo.setCurrentIndex(0)
        self._generation_combo.blockSignals(False)
        if not runs:
            self._cluster_list.clear()
            self._status_label.setText(text.CLUSTER_RESULTS_EMPTY)
            self._set_actions_enabled(False)
            return
        self._reload_assignments()
        self._render_clusters()
        self._render_person_combo()

    def _reload_assignments(self) -> None:
        """当前有效指派（suggested/confirmed）按 cluster 索引。"""
        cluster_run_id = self._generation_combo.currentData()
        self._assignments_by_cluster = {}
        if cluster_run_id is None:
            return
        for assignment in self._results_service.assignments_active(cluster_run_id):
            self._assignments_by_cluster[assignment.cluster_id] = assignment

    def _render_clusters(self) -> None:
        """簇列表：组号/成员数/当前指派状态（自动建议与人工决策可区分）。"""
        cluster_run_id = self._generation_combo.currentData()
        self._cluster_list.blockSignals(True)
        self._cluster_list.clear()
        if cluster_run_id is None:
            self._cluster_list.blockSignals(False)
            self._set_actions_enabled(False)
            return
        results = self._results_service.results(cluster_run_id)
        if results is None or not results.clusters:
            self._cluster_list.blockSignals(False)
            self._status_label.setText(text.PAIRING_WORKBENCH_NO_CLUSTERS)
            self._set_actions_enabled(False)
            return
        for detail in results.clusters:
            assignment = self._assignments_by_cluster.get(detail.cluster_id)
            item = QListWidgetItem(text.PAIRING_WORKBENCH_CLUSTER_ENTRY.format(
                ordinal=detail.ordinal + 1,
                count=detail.member_count,
                assignment=self._assignment_text(assignment),
            ))
            item.setData(Qt.ItemDataRole.UserRole, detail.cluster_id)
            self._cluster_list.addItem(item)
        self._cluster_list.blockSignals(False)
        keep = self._selected_cluster_id
        target_row = 0
        for row in range(self._cluster_list.count()):
            if self._cluster_list.item(row).data(Qt.ItemDataRole.UserRole) == keep:
                target_row = row
                break
        self._cluster_list.setCurrentRow(target_row)

    def _assignment_text(self, assignment: ClusterPersonAssignment | None) -> str:
        """Render one assignment's state; suggestions carry source + score."""
        if assignment is None:
            return text.PAIRING_WORKBENCH_NO_ASSIGNMENT_HINT
        if assignment.status in ("suggested", "confirmed", "rejected"):
            person = self._person_name(assignment.person_id)
            if assignment.status == "suggested":
                source = text.PAIRING_WORKBENCH_SOURCE_LABELS.get(
                    assignment.source, assignment.source,
                )
                score = f"{assignment.score:.2f}" if assignment.score is not None else "—"
                return text.PAIRING_WORKBENCH_ASSIGNMENT_LABEL["suggested"].format(
                    source=source, score=score,
                )
            label = text.PAIRING_WORKBENCH_ASSIGNMENT_LABEL.get(
                assignment.status, assignment.status,
            )
            return label.format(person=person)
        return text.PAIRING_WORKBENCH_ASSIGNMENT_LABEL["unassigned"]

    def _person_name(self, person_id: UUID | None) -> str:
        if person_id is None:
            return "—"
        for person in self._persons:
            if person.id == person_id:
                return person.name
        return "—"

    def _render_person_combo(self) -> None:
        """人员下拉（roster 顺序）；空名单给出明确提示并禁用指派。"""
        self._person_combo.blockSignals(True)
        self._person_combo.clear()
        for person in self._persons:
            if person.id is not None:
                self._person_combo.addItem(person.name, person.id)
        self._person_combo.blockSignals(False)
        self._person_combo.setEnabled(bool(self._persons))

    def _set_actions_enabled(self, enabled: bool) -> None:
        for button in (self._confirm_button, self._reject_button,
                       self._assign_button, self._unassign_button,
                       self._unknown_button, self._ignore_button):
            button.setEnabled(enabled)

    # ── 选择联动 ────────────────────────────────────────────────────────

    def _on_generation_selected(self, _index: int) -> None:
        self._selected_cluster_id = None
        self._reload_assignments()
        self._render_clusters()

    def _on_cluster_selected(self, current, _previous) -> None:
        cluster_id = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self._selected_cluster_id = cluster_id if isinstance(cluster_id, UUID) else None
        self._set_actions_enabled(self._selected_cluster_id is not None)
        assignment = (
            self._assignments_by_cluster.get(self._selected_cluster_id)
            if self._selected_cluster_id is not None else None
        )
        if assignment is not None and assignment.status == "suggested":
            if assignment.person_id is not None:
                index = self._person_combo.findData(assignment.person_id)
                if index >= 0:
                    self._person_combo.setCurrentIndex(index)

    # ── 操作（同步、快 SQLite；操作后重读重渲染） ────────────────────────

    def _selected_assignment_id(self) -> UUID | None:
        cluster_id = self._selected_cluster_id
        if cluster_id is None:
            return None
        assignment = self._assignments_by_cluster.get(cluster_id)
        if assignment is None or assignment.id is None:
            return None
        return assignment.id

    def _on_generate_clicked(self) -> None:
        cluster_run_id = self._generation_combo.currentData()
        if cluster_run_id is None:
            return
        summary = self._suggest_service.execute(
            StartSuggestPairingsCommand(cluster_run_id),
        )
        self._status_label.setText(
            text.PAIRING_WORKBENCH_SUGGESTED_DONE.format(
                suggestions=summary.suggestions,
                sample_matched=summary.sample_matched,
                ordered=summary.ordered,
            )
        )
        self.refresh()

    def _on_confirm_clicked(self) -> None:
        assignment_id = self._selected_assignment_id()
        if assignment_id is None:
            return
        try:
            result = self._workbench_service.confirm(
                ConfirmAssignmentCommand(assignment_id),
            )
        except Exception as exc:  # noqa: BLE001 - UI boundary
            self._warn(str(exc))
            return
        self._status_label.setText(
            text.PAIRING_WORKBENCH_CONFIRMED.format(
                person=self._person_name(self._person_id_of(result.assignment_id)),
            )
        )
        self.refresh()

    def _on_reject_clicked(self) -> None:
        assignment_id = self._selected_assignment_id()
        if assignment_id is None:
            return
        try:
            self._workbench_service.reject(RejectAssignmentCommand(assignment_id))
        except Exception as exc:  # noqa: BLE001 - UI boundary
            self._warn(str(exc))
            return
        self._status_label.setText(text.PAIRING_WORKBENCH_REJECTED)
        self.refresh()

    def _on_assign_clicked(self) -> None:
        cluster_id = self._selected_cluster_id
        person_id = self._person_combo.currentData()
        if cluster_id is None or person_id is None:
            return
        try:
            result = self._workbench_service.assign_person(
                AssignClusterPersonCommand(cluster_id=cluster_id, person_id=person_id),
            )
        except Exception as exc:  # noqa: BLE001 - UI boundary
            self._warn(str(exc))
            return
        self._status_label.setText(
            text.PAIRING_WORKBENCH_ASSIGNED.format(
                person=self._person_name(self._person_id_of(result.assignment_id)),
            )
        )
        self.refresh()

    def _on_unassign_clicked(self) -> None:
        cluster_id = self._selected_cluster_id
        if cluster_id is None:
            return
        try:
            self._workbench_service.unassign(UnassignClusterCommand(cluster_id))
        except Exception as exc:  # noqa: BLE001 - UI boundary
            self._warn(str(exc))
            return
        self._status_label.setText(text.PAIRING_WORKBENCH_UNASSIGNED)
        self.refresh()

    def _on_state_clicked(self, state: str) -> None:
        cluster_id = self._selected_cluster_id
        if cluster_id is None:
            return
        try:
            self._workbench_service.set_cluster_state(
                SetClusterStateCommand(cluster_id=cluster_id, state=state),
            )
        except Exception as exc:  # noqa: BLE001 - UI boundary
            self._warn(str(exc))
            return
        self._status_label.setText(
            text.PAIRING_WORKBENCH_STATE_SET.format(state=state),
        )
        self.refresh()

    # ── 助手 ────────────────────────────────────────────────────────────

    def _person_id_of(self, assignment_id: UUID | None) -> UUID | None:
        if assignment_id is None:
            return None
        assignment = self._workbench_service.get_assignment(assignment_id)
        return assignment.person_id if assignment is not None else None

    def _warn(self, message: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(
            self, text.PAIRING_WORKBENCH_OP_FAILED_TITLE, message,
        )
