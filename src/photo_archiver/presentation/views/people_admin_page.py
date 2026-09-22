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
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from photo_archiver.application.services import ListPersonsService, ManagePeopleService
from photo_archiver.domain import Person
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import ROLE_DANGER, ROLE_PRIMARY, assign_role
from photo_archiver.presentation.views.person_deletion_dialog import PersonDeletionDialog
from photo_archiver.presentation.views.person_edit_dialog import PersonEditDialog

_COLUMNS = (
    text.PEOPLE_PAGE_COL_ORDER,
    text.PEOPLE_PAGE_COL_NAME,
    text.PEOPLE_PAGE_COL_IDENTITY,
    text.PEOPLE_PAGE_COL_DEPARTMENT,
    text.PEOPLE_PAGE_COL_NOTE,
    text.PEOPLE_PAGE_COL_BATCH,
    text.PEOPLE_PAGE_COL_ACTIONS,
)


class _ReorderableTable(QTableWidget):
    """Table whose rows can be dragged to re-ask the page for a new order."""

    rows_dropped = Signal(int, int)  # (source_row, target_row)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Configure the table for single-row selection with internal drag."""
        super().__init__(parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def dropEvent(self, event) -> None:  # noqa: ANN001  # Qt signature
        """Translate a row drop into a reorder request instead of a copy."""
        source_row = self.currentRow()
        target_row = self.indexAt(event.position().toPoint()).row()
        if target_row < 0:
            target_row = self.rowCount() - 1
        event.accept()
        if source_row < 0 or source_row == target_row:
            return
        self.rows_dropped.emit(source_row, target_row)


class PeopleAdminPage(QWidget):
    """Ordered roster table with add/edit/delete and drag reordering."""

    people_changed = Signal()

    def __init__(
        self,
        manage_people: ManagePeopleService,
        list_persons: ListPersonsService,
        delete_person,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the page with its Application services.

        Args:
            manage_people: Roster administration use case (add/edit/reorder).
            list_persons: Read-only catalog used to reload after deletions
                (the deletion use case is not on ``ManagePeopleService``).
            delete_person: The existing deletion use case (preview + execute),
                reused so cascade semantics stay in one place.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._manage_people = manage_people
        self._list_persons = list_persons
        self._delete_person = delete_person
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
        self._move_up_button = QPushButton(text.PEOPLE_PAGE_MOVE_UP, self)
        self._move_up_button.clicked.connect(lambda: self.move_selected(-1))
        self._move_down_button = QPushButton(text.PEOPLE_PAGE_MOVE_DOWN, self)
        self._move_down_button.clicked.connect(lambda: self.move_selected(1))
        self._delete_button = QPushButton(text.PEOPLE_PAGE_DELETE_BUTTON, self)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        assign_role(self._delete_button, ROLE_DANGER)
        for widget in (
            self._add_button, self._move_up_button, self._move_down_button, self._delete_button,
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

    # ── Data + rendering ────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload the roster from Application and re-render everything."""
        roster = self._manage_people.roster()
        self._rows = list(roster.people)
        self._batches = roster.batches
        self._render_batch_combo()
        self._render_rows()

    def visible_people(self) -> list[Person]:
        """Return the rows the table currently shows (batch filter applied)."""
        if self._batch_filter is None:
            return list(self._rows)
        return [person for person in self._rows if person.source_batch_id == self._batch_filter]

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
        """Render the (filtered) roster into the table."""
        batch_names = {summary.batch.id: summary.batch.file_name for summary in self._batches}
        people = self.visible_people()
        self._table.setRowCount(len(people))
        for row_index, person in enumerate(people):
            position = self._rows.index(person) + 1
            values = (
                str(position),
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
            edit_button = QPushButton(text.PEOPLE_PAGE_EDIT_BUTTON, self._table)
            edit_button.clicked.connect(
                lambda _checked=False, person=person: self._on_edit_clicked(person),
            )
            self._table.setCellWidget(row_index, len(_COLUMNS) - 1, edit_button)
        if people:
            self._empty_label.clear()
        else:
            self._empty_label.setText(
                text.PEOPLE_PAGE_EMPTY if not self._rows else text.PEOPLE_PAGE_EMPTY_FILTERED
            )
        self._table.setDragEnabled(self._batch_filter is None)
        self._batch_hint.setVisible(self._batch_filter is not None)
        self._render_action_state()

    def _render_action_state(self) -> None:
        """Reordering needs a full-roster view and a selected row."""
        reorderable = self._batch_filter is None and self._selected_row_index() >= 0
        self._move_up_button.setEnabled(reorderable)
        self._move_down_button.setEnabled(reorderable)
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
            self._warn(text.PEOPLE_PAGE_DELETE_FAILED.format(detail=exc))
            return
        logger.info(
            "People page deleted person {} (embedded={} orphaned={})",
            person_id, result.embedding_cascade, result.recognition_orphaned,
        )
        self._after_mutation(text.PEOPLE_PAGE_DELETED.format(name=person_name))

    # ── Reordering ──────────────────────────────────────────────────────

    def move_selected(self, offset: int) -> None:
        """Move the selected row by ``offset`` places and persist the roster."""
        index = self._selected_row_index()
        if index < 0 or self._batch_filter is not None:
            return
        self.move_row(index, index + offset)

    def move_row(self, source_index: int, target_index: int) -> None:
        """Reorder the roster rows and persist the new sequence in one call."""
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
        self._after_mutation(text.PEOPLE_PAGE_REORDERED.format(count=updated))

    # ── Shared helpers ──────────────────────────────────────────────────

    def _after_mutation(self, message: str) -> None:
        """Reload the page, then let the window refresh dependent surfaces."""
        self.refresh()
        self._status_message = message
        self.people_changed.emit()

    def last_message(self) -> str:
        """Return the message of the last successful mutation (window status)."""
        return getattr(self, "_status_message", "")

    def _warn(self, message: str) -> None:
        """Show a non-destructive warning for a rejected operation."""
        QMessageBox.warning(self, text.PEOPLE_PAGE_ADD_BUTTON, message)
