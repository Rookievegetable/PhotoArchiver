"""People & grouping page — stage B of the people-import redesign (D5).

The roster is the ordered registry the photo library filters by, so this page
makes it editable: add, edit, delete (through the existing danger-confirm
dialog) and drag-reorder. ``来源批次`` shows which import brought a person in,
and the batch selector offers a read-only review of one batch at a time.

Layer note: the page talks to Application services only (DEP-010); it owns no
repository, no SQL and no business rule — validation errors come back from
``ManagePeopleService`` and are shown verbatim.
"""

from __future__ import annotations

from uuid import UUID

from loguru import logger
from PySide6.QtCore import Qt, QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.commands import (
    AddPersonCommand,
    DeletePersonCommand,
    EditPersonCommand,
    ReorderPeopleCommand,
)
from photo_archiver.application.dtos import ImportBatchSummary, PersonDeletionResult
from photo_archiver.application.services import (
    ClusterResultsService,
    ListPersonsService,
    ListRecognitionRunsService,
    ManagePeopleService,
)
from photo_archiver.domain import Person
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import ROLE_DANGER, ROLE_PRIMARY, assign_role
from photo_archiver.presentation.views.batch_person_deletion_dialog import (
    BatchPersonDeletionDialog,
    ClearAllPeopleDialog,
)
from photo_archiver.presentation.views.person_deletion_dialog import PersonDeletionDialog
from photo_archiver.presentation.views.person_edit_dialog import PersonEditDialog

# 界面优化 §4.1：取消行内操作列——编辑移至工具栏（选中行生效），
# 减少操作栏占用；身份/排序/批次归属/删除能力全部保留。
_COLUMNS = (
    text.PEOPLE_PAGE_COL_ORDER,
    text.PEOPLE_PAGE_COL_NAME,
    text.PEOPLE_PAGE_COL_IDENTITY,
    text.PEOPLE_PAGE_COL_DEPARTMENT,
    text.PEOPLE_PAGE_COL_NOTE,
    text.PEOPLE_PAGE_COL_BATCH,
)


_ROW_MIME_TYPE = "application/x-qabstractitemmodeldatalist"


class _ReorderableTable(QTableWidget):
    """Table whose rows can be dragged to re-ask the page for a new order.

    A drag is a *positional request*, never a model edit: the page re-renders
    from the domain roster after the drop, so the table model stays the single
    source of truth. Two Qt details make that work (both verified against the
    shipped PySide6 build — stage-B review fix #2):

    - ``setDragDropMode(DragOnly)`` turns ``acceptDrops`` back off, so drops
      arrive only when the view *and* its viewport re-enable it after the mode
      call;
    - accepting a drop with its proposed ``MoveAction`` makes
      ``QAbstractItemView::startDrag`` run its internal ``clearOrRemove()``
      afterwards, removing the source row from the model *after* the page had
      re-rendered — exactly the blank row of the stage-B review. The drop is
      accepted as ``CopyAction`` instead (a table drag offers ``Copy|Move``, so
      the downgrade always applies), and the stale selection is cleared as a
      second guard for a drag that could not be downgraded.
    """

    rows_dropped = Signal(int, int)  # (source_row, target_row)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Configure the table for single-row selection with row dragging."""
        super().__init__(parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._drag_source_row: int | None = None
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        # Order matters: the mode call above turns both drop flags back off.
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(False)

    def startDrag(self, supported_actions) -> None:  # noqa: ANN001  # Qt signature
        """Remember which row the drag started from, then run Qt's drag loop."""
        self._drag_source_row = self.currentRow()
        super().startDrag(supported_actions)

    def dragEnterEvent(self, event) -> None:  # noqa: ANN001  # Qt signature
        """Accept this table's own row payload; ignore every foreign drag."""
        if self._is_row_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: ANN001  # Qt signature
        """Keep one of our own row drags alive while it is over the viewport."""
        if self._is_row_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: ANN001  # Qt signature
        """Translate a row drop into a reorder request instead of a copy."""
        source_row = self._drag_source_row
        self._drag_source_row = None
        if source_row is None:
            source_row = self.currentRow()
        target_row = self.indexAt(event.position().toPoint()).row()
        if target_row < 0:  # dropped in the empty area below the last row
            target_row = self.rowCount() - 1
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        if source_row < 0 or target_row < 0 or source_row == target_row:
            return
        self.rows_dropped.emit(source_row, target_row)
        if event.dropAction() != Qt.DropAction.CopyAction:
            # Qt could not downgrade this drop, so its internal clearOrRemove()
            # is about to delete the selected row from the model: no row (and
            # in particular not the freshly re-selected moved one) may stay
            # selected.
            self.clearSelection()

    def _is_row_drag(self, event) -> bool:  # noqa: ANN001  # Qt signature
        """Return True while one of our own draggable rows is over the table."""
        if not self.dragEnabled() or not event.mimeData().hasFormat(_ROW_MIME_TYPE):
            return False
        source = event.source()
        return source is None or source is self or source is self.viewport()


class PeopleAdminPage(QWidget):
    """Ordered roster table with add/edit/delete and drag reordering."""

    # structure_changed=False marks a pure reorder: the roster contents are
    # unchanged, so the window leaves the filter axis and the readiness
    # snapshot alone (the page has already re-rendered itself by then).
    people_changed = Signal(bool)
    # D-4 聚类入口：页面只发请求信号，运行/对话框由主窗口按既有任务管线处理。
    cluster_run_requested = Signal()
    cluster_results_requested = Signal()

    def __init__(
        self,
        manage_people: ManagePeopleService,
        list_persons: ListPersonsService,
        delete_person,
        list_recognition_runs: ListRecognitionRunsService,
        cluster_results: ClusterResultsService,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the page with its Application services.

        Args:
            manage_people: Roster administration use case (add/edit/reorder).
            list_persons: Read-only catalog used to reload after deletions
                (the deletion use case is not on ``ManagePeopleService``).
            delete_person: The existing deletion use case (preview + execute),
                reused so cascade semantics stay in one place.
            list_recognition_runs: Read-only recognition runs for the D-4
                clustering entry's run selector.
            cluster_results: Read-only cluster generations/results for the
                clustering section's availability and results dialog.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._manage_people = manage_people
        self._list_persons = list_persons
        self._delete_person = delete_person
        self._list_recognition_runs = list_recognition_runs
        self._cluster_results = cluster_results
        self._rows: list[Person] = []
        self._batches: tuple[ImportBatchSummary, ...] = ()
        self._batch_filter: UUID | None = None
        self._build_ui()
        self.refresh()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Lay out the hint, batch review row, toolbar row and the table."""
        layout = QVBoxLayout(self)

        hint = QLabel(text.PEOPLE_PAGE_HINT, self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        review_row = QHBoxLayout()
        review_row.addWidget(QLabel(text.PEOPLE_PAGE_BATCH_FILTER_LABEL, self))
        self._batch_combo = QComboBox(self)
        self._batch_combo.setMinimumWidth(260)
        self._batch_combo.currentIndexChanged.connect(self._on_batch_selected)
        review_row.addWidget(self._batch_combo)
        self._batch_hint = QLabel(text.PEOPLE_PAGE_BATCH_FILTER_HINT, self)
        review_row.addWidget(self._batch_hint)
        review_row.addStretch()
        layout.addLayout(review_row)

        toolbar_row = QHBoxLayout()
        self._add_button = QPushButton(text.PEOPLE_PAGE_ADD_BUTTON, self)
        self._add_button.clicked.connect(self._on_add_clicked)
        assign_role(self._add_button, ROLE_PRIMARY)
        self._edit_button = QPushButton(text.PEOPLE_PAGE_EDIT_BUTTON, self)
        self._edit_button.clicked.connect(self._on_edit_selected_clicked)
        self._move_up_button = QPushButton(text.PEOPLE_PAGE_MOVE_UP, self)
        self._move_up_button.clicked.connect(lambda: self.move_selected(-1))
        self._move_down_button = QPushButton(text.PEOPLE_PAGE_MOVE_DOWN, self)
        self._move_down_button.clicked.connect(lambda: self.move_selected(1))
        self._delete_button = QPushButton(text.PEOPLE_PAGE_DELETE_BUTTON, self)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        assign_role(self._delete_button, ROLE_DANGER)
        self._delete_batch_button = QPushButton(text.PEOPLE_PAGE_DELETE_BATCH_BUTTON, self)
        self._delete_batch_button.clicked.connect(self._on_delete_batch_clicked)
        assign_role(self._delete_batch_button, ROLE_DANGER)
        self._clear_all_button = QPushButton(text.PEOPLE_PAGE_CLEAR_ALL_BUTTON, self)
        self._clear_all_button.clicked.connect(self._on_clear_all_clicked)
        assign_role(self._clear_all_button, ROLE_DANGER)
        for widget in (
            self._add_button, self._edit_button, self._move_up_button,
            self._move_down_button, self._delete_button, self._delete_batch_button,
            self._clear_all_button,
        ):
            toolbar_row.addWidget(widget)
        toolbar_row.addStretch()
        layout.addLayout(toolbar_row)

        self._table = _ReorderableTable(self)
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.rows_dropped.connect(self._on_rows_dropped)
        self._table.itemSelectionChanged.connect(self._render_action_state)
        layout.addWidget(self._table, 1)

        self._empty_label = QLabel(self)
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        self._build_clustering_ui(layout)

    # ── Data + rendering ────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload the roster from Application and re-render everything.

        The selection is anchored to the selected *person*, not to a row index:
        every re-render (import, deletion, reorder, the window's own refresh)
        keeps that person selected wherever the roster now puts them. Stage-B
        review follow-up: the highlight used to stay on the old row index,
        which after 「上移/下移」 is somebody else — so the next click moved the
        wrong person.
        """
        selected_id = self._selected_person_id()
        roster = self._manage_people.roster()
        self._rows = list(roster.people)
        self._batches = roster.batches
        self._render_batch_combo()
        self._render_rows()
        self._restore_selection(selected_id)
        self.refresh_clustering()

    def visible_people(self) -> list[Person]:
        """Return the rows the table currently shows (batch filter applied)."""
        if self._batch_filter is None:
            return list(self._rows)
        return [person for person in self._rows if person.source_batch_id == self._batch_filter]

    def _selected_person_id(self) -> UUID | None:
        """Return the id of the person behind the selected row, or ``None``."""
        person = self._selected_person()
        return person.id if person is not None else None

    def _restore_selection(self, person_id: UUID | None) -> None:
        """Re-select ``person_id`` when it is still part of the visible roster."""
        if person_id is None:
            return
        for index, person in enumerate(self.visible_people()):
            if person.id == person_id:
                self._focus_row(index)
                return

    def _focus_row(self, index: int) -> None:
        """Select row ``index``, make it the current row and reveal it.

        Focus is only taken when the table already owned it — a move started
        from the 「上移/下移」 buttons must leave those buttons keyboard-usable.
        """
        if not (0 <= index < self._table.rowCount()):
            return
        item = self._table.item(index, 1)
        if item is None:
            return
        self._table.setCurrentCell(index, 1)
        self._table.selectRow(index)
        self._table.scrollToItem(item)
        if self._table.hasFocus() or self._table.viewport().hasFocus():
            self._table.setFocus(Qt.FocusReason.OtherFocusReason)

    def _render_batch_combo(self) -> None:
        """Refill the batch selector, preserving the active filter."""
        self._batch_combo.blockSignals(True)
        self._batch_combo.clear()
        self._batch_combo.addItem(text.PEOPLE_PAGE_BATCH_ALL, None)
        for summary in self._batches:
            label = text.PEOPLE_PAGE_BATCH_ENTRY.format(
                file_name=summary.batch.file_name, person_count=summary.person_count,
            )
            self._batch_combo.addItem(label, summary.batch.id)
        index = self._batch_combo.findData(self._batch_filter)
        self._batch_combo.setCurrentIndex(index if index >= 0 else 0)
        self._batch_filter = self._batch_combo.currentData()
        self._batch_combo.blockSignals(False)

    def _render_rows(self) -> None:
        """Render the (filtered) roster into the table.

        The rebuild runs with updates frozen and table signals blocked:
        per-row ``setItem``/``setCellWidget`` would otherwise repaint and fire
        selection signals row by row (probe ④ dominated every click at 300+
        rows). Row positions come from an id→position map instead of
        ``list.index`` — an equality scan per row made the loop O(N²).
        """
        batch_names = {summary.batch.id: summary.batch.file_name for summary in self._batches}
        people = self.visible_people()
        positions = {person.id: index + 1 for index, person in enumerate(self._rows)}
        self._table.setUpdatesEnabled(False)
        try:
            with QSignalBlocker(self._table):
                self._table.setRowCount(len(people))
                for row_index, person in enumerate(people):
                    values = (
                        str(positions[person.id]),
                        person.name,
                        person.identity.value if person.identity else "",
                        person.department or "",
                        person.note or "",
                        batch_names.get(person.source_batch_id, text.PEOPLE_PAGE_MANUAL_SOURCE)
                        if person.source_batch_id is not None else text.PEOPLE_PAGE_MANUAL_SOURCE,
                    )
                    for column, value in enumerate(values):
                        item = QTableWidgetItem(value)
                        item.setToolTip(value)
                        self._table.setItem(row_index, column, item)
                if people:
                    self._empty_label.clear()
                else:
                    self._empty_label.setText(
                        text.PEOPLE_PAGE_EMPTY if not self._rows else text.PEOPLE_PAGE_EMPTY_FILTERED
                    )
                self._table.setDragEnabled(self._batch_filter is None)
                self._batch_hint.setVisible(self._batch_filter is not None)
        finally:
            self._table.setUpdatesEnabled(True)
        self._render_action_state()

    def _render_action_state(self) -> None:
        """Reordering needs a full-roster view and a selected, movable row.

        The move buttons grey out at the roster edges instead of silently doing
        nothing when the selected person is already first/last.
        """
        index = self._selected_row_index()
        reorderable = self._batch_filter is None and index >= 0
        last_index = self._table.rowCount() - 1
        self._move_up_button.setEnabled(reorderable and index > 0)
        self._move_down_button.setEnabled(reorderable and 0 <= index < last_index)
        self._edit_button.setEnabled(self._selected_person() is not None)
        self._delete_button.setEnabled(self._selected_person() is not None)

    def _selected_row_index(self) -> int:
        """Return the selected table row, or -1 when nothing is selected."""
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        return rows[0].row() if rows else -1

    def _selected_person(self) -> Person | None:
        """Return the person behind the selected row, or None."""
        index = self._selected_row_index()
        people = self.visible_people()
        return people[index] if 0 <= index < len(people) else None

    # ── Batch review ────────────────────────────────────────────────────

    def _on_batch_selected(self, _index: int) -> None:
        """Switch the read-only batch view and re-render."""
        self._batch_filter = self._batch_combo.currentData()
        self._render_rows()

    # ── Add / edit / delete ─────────────────────────────────────────────

    def _on_add_clicked(self) -> None:
        """Collect a new person and append them to the roster."""
        dialog = PersonEditDialog(parent=self)
        if not dialog.exec():
            return
        values = dialog.values()
        try:
            person = self._manage_people.add_person(AddPersonCommand(**values))
        except ValidationError as exc:
            self._warn(text.PEOPLE_PAGE_SAVE_FAILED.format(detail=exc))
            return
        logger.info("People page added person {}", person.id)
        self._after_mutation(text.PEOPLE_PAGE_ADDED.format(name=person.name))

    def _on_edit_selected_clicked(self) -> None:
        """编辑选中行的人员资料（工具栏入口；§4.1 去行内操作列）。"""
        person = self._selected_person()
        if person is not None:
            self._on_edit_clicked(person)

    def _on_edit_clicked(self, person: Person) -> None:
        """Edit one person's fields through the form dialog."""
        dialog = PersonEditDialog(person=person, parent=self)
        if not dialog.exec():
            return
        values = dialog.values()
        try:
            updated = self._manage_people.edit_person(
                EditPersonCommand(person_id=person.id, **values),  # type: ignore[arg-type]
            )
        except ValidationError as exc:
            self._warn(text.PEOPLE_PAGE_SAVE_FAILED.format(detail=exc))
            return
        logger.info("People page edited person {}", updated.id)
        self._after_mutation(text.PEOPLE_PAGE_EDITED.format(name=updated.name))

    def _on_delete_clicked(self) -> None:
        """Delete the selected person through the existing danger-confirm dialog."""
        person = self._selected_person()
        if person is None:
            return
        dialog = PersonDeletionDialog(
            self._list_persons, self._delete_person, parent=self, preselect_id=person.id,
        )
        if not dialog.exec():
            return
        person_id = dialog.selected_person_id()
        person_name = dialog.selected_person_name()
        if person_id is None:
            return
        try:
            result: PersonDeletionResult = self._delete_person.execute(
                DeletePersonCommand(person_ids=(person_id,)),
            )
        except Exception as exc:  # noqa: BLE001  # UI boundary: show, log the detail
            logger.exception("People page deletion failed")
            self._warn(
                text.PEOPLE_PAGE_DELETE_FAILED.format(detail=exc),
                text.PEOPLE_PAGE_DELETE_FAILED_TITLE,
            )
            return
        logger.info(
            "People page deleted person {} (embedded={} orphaned={})",
            person_id, result.embedding_cascade, result.recognition_orphaned,
        )
        self._after_mutation(text.PEOPLE_PAGE_DELETED.format(name=person_name))

    def _on_delete_batch_clicked(self) -> None:
        """按导入批次删除人员（界面优化 §4.3；预览+二次确认+可选清理）。"""
        if not self._batches:
            self._warn(text.PEOPLE_PAGE_EMPTY)
            return
        dialog = BatchPersonDeletionDialog(
            self._manage_people, self._delete_person, parent=self,
        )
        if not dialog.exec():
            return
        logger.info("People page deleted one import batch's people")
        self._after_mutation(dialog.last_message())

    def _on_clear_all_clicked(self) -> None:
        """清空所有人员（界面优化 §4.3；显式知悉勾选 + 单事务执行）。"""
        dialog = ClearAllPeopleDialog(
            self._manage_people, self._delete_person, parent=self,
        )
        if not dialog.exec():
            return
        logger.info("People page cleared all people")
        self._after_mutation(dialog.last_message())

    # ── Reordering ──────────────────────────────────────────────────────

    def move_selected(self, offset: int) -> None:
        """Move the selected row by ``offset`` places and persist the roster.

        The person stays selected at their new position (``refresh`` re-anchors
        the selection to the person), so pressing 「上移/下移」 again keeps moving
        the same person instead of whoever the old row index now holds.
        """
        index = self._selected_row_index()
        if index < 0 or self._batch_filter is not None:
            return
        self.move_row(index, index + offset)

    def move_row(self, source_index: int, target_index: int) -> None:
        """Reorder the roster rows, persist the sequence and keep the row selected."""
        people = self.visible_people()
        if not (0 <= source_index < len(people)) or not (0 <= target_index < len(people)):
            return
        if source_index == target_index:
            return
        person = people.pop(source_index)
        people.insert(target_index, person)
        self._persist_order(people)

    def _on_rows_dropped(self, source_row: int, target_row: int) -> None:
        """Handle a table drag: same semantics as the move buttons."""
        self.move_row(source_row, target_row)

    def _persist_order(self, ordered_people: list[Person]) -> None:
        """Write the full roster order and refresh dependent views."""
        try:
            updated = self._manage_people.reorder_people(
                ReorderPeopleCommand(ordered_ids=tuple(
                    person.id for person in ordered_people  # type: ignore[misc]
                )),
            )
        except ValidationError as exc:
            self._warn(text.PEOPLE_PAGE_SAVE_FAILED.format(detail=exc))
            self.refresh()
            return
        logger.info("People page reordered {} people", updated)
        self._after_mutation(
            text.PEOPLE_PAGE_REORDERED.format(count=updated)
            + " " + text.PEOPLE_PAGE_REORDER_HINT,
            structure_changed=False,
        )

    # ── D-4 聚类入口 ───────────────────────────────────────────────────

    def _build_clustering_ui(self, layout: QVBoxLayout) -> None:
        """Build the clustering group: run selector, run + results buttons.

        页面只发请求信号——运行走主窗口的 TaskCoordinator 管线（互斥/取消/
        状态栏），结果对话框由主窗口打开（父窗口与缩略图通道注入）。
        """
        group = QGroupBox(text.CLUSTER_PAGE_GROUP, self)
        group_layout = QVBoxLayout(group)
        row = QHBoxLayout()
        row.addWidget(QLabel(text.CLUSTER_PAGE_RUN_LABEL, group))
        self._cluster_run_combo = QComboBox(group)
        self._cluster_run_combo.setMinimumWidth(280)
        row.addWidget(self._cluster_run_combo)
        self._cluster_run_button = QPushButton(text.CLUSTER_PAGE_RUN_BUTTON, group)
        self._cluster_run_button.clicked.connect(self.cluster_run_requested.emit)
        assign_role(self._cluster_run_button, ROLE_PRIMARY)
        row.addWidget(self._cluster_run_button)
        self._cluster_results_button = QPushButton(text.CLUSTER_PAGE_RESULTS_BUTTON, group)
        self._cluster_results_button.clicked.connect(self.cluster_results_requested.emit)
        row.addWidget(self._cluster_results_button)
        row.addStretch()
        group_layout.addLayout(row)
        hint = QLabel(text.CLUSTER_PAGE_HINT, group)
        hint.setWordWrap(True)
        group_layout.addWidget(hint)
        self._cluster_hint = QLabel("", group)
        self._cluster_hint.setWordWrap(True)
        group_layout.addWidget(self._cluster_hint)
        layout.addWidget(group)

    def refresh_clustering(self) -> None:
        """Reload the recognition-run selector and clustering availability.

        选择按 run id 锚定（刷新后保持合理当前选择）；无运行时按钮禁用并
        给出明确空态文案。
        """
        selected = self.selected_recognition_run_id()
        runs = self._list_recognition_runs.execute()
        self._cluster_run_combo.blockSignals(True)
        self._cluster_run_combo.clear()
        for run in runs:
            self._cluster_run_combo.addItem(
                text.CLUSTER_PAGE_RUN_ENTRY.format(
                    created_at=run.created_at.strftime("%Y-%m-%d %H:%M")
                    if run.created_at is not None else "—",
                    status=text.cluster_run_status_label(run.status),
                    faces=run.face_count,
                ),
                run.id,
            )
        self._cluster_run_combo.blockSignals(False)
        if selected is not None:
            # findData 对值相等但非同一实例的 UUID 不可靠（QVariant 比较），
            # 这里用值扫描保持刷新后的当前选择。
            for index in range(self._cluster_run_combo.count()):
                if self._cluster_run_combo.itemData(index) == selected:
                    self._cluster_run_combo.setCurrentIndex(index)
                    break
        self._render_cluster_availability()

    def _render_cluster_availability(self) -> None:
        """Enable the run button on a selected run; results need a generation."""
        run_id = self.selected_recognition_run_id()
        has_results = False
        if run_id is not None:
            has_results = bool(self._cluster_results.list_cluster_runs(run_id))
        self._cluster_run_button.setEnabled(run_id is not None)
        self._cluster_results_button.setEnabled(has_results)
        self._cluster_hint.setText(
            "" if run_id is not None else text.CLUSTER_PAGE_NO_RUNS
        )

    def selected_recognition_run_id(self) -> UUID | None:
        """Return the recognition run id behind the selector, or ``None``."""
        data = self._cluster_run_combo.currentData()
        return data if isinstance(data, UUID) else None

    # ── Shared helpers ──────────────────────────────────────────────────

    def _after_mutation(self, message: str, *, structure_changed: bool = True) -> None:
        """Reload the page, then let the window refresh dependent surfaces.

        ``structure_changed=False`` marks a pure reorder: the page has already
        re-rendered here, and the window skips its filter-axis / snapshot
        cascade — its extra ``refresh()`` used to double every table rebuild.
        """
        self.refresh()
        self._status_message = message
        self.people_changed.emit(structure_changed)

    def last_message(self) -> str:
        """Return the message of the last successful mutation (window status)."""
        return getattr(self, "_status_message", "")

    def _warn(self, message: str, title: str = text.PEOPLE_PAGE_SAVE_FAILED_TITLE) -> None:
        """Show a non-destructive warning for a rejected operation."""
        QMessageBox.warning(self, title, message)
