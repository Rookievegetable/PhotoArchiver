"""Import preview and confirmation dialog (people-import redesign stage A).

Owner plan §4.2: the dialog shows every draft row as
原始内容 / 解析结果 / 告警 / 处理动作 and lets the user split multi-name
cells, switch actions, edit fields, and re-parse with different options
(header, sheet, field mapping) before anything touches the formal registry.

The dialog never writes people itself — it persists draft edits through
``ParseImportDraftService`` and, on accept, hands the batch back to the
window, which runs ``ConfirmImportService`` synchronously (≤500 rows) or
submits ``ConfirmImportTask`` for larger rosters. Cancel keeps the draft.
"""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from photo_archiver.application.commands.import_draft import (
    ReparseImportDraftCommand,
)
from photo_archiver.application.dtos.import_draft import ImportDraft
from photo_archiver.domain.entities import (
    DRAFT_ACTION_CREATE,
    DRAFT_ACTION_MERGE_EXISTING,
    DRAFT_ACTION_SKIP,
)
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import ROLE_PRIMARY, assign_role

CONFIRM_SYNC_LIMIT = 500

_ACTION_LABELS = (
    (DRAFT_ACTION_CREATE, text.IMPORT_PREVIEW_ACTION_CREATE),
    (DRAFT_ACTION_MERGE_EXISTING, text.IMPORT_PREVIEW_ACTION_MERGE),
    (DRAFT_ACTION_SKIP, text.IMPORT_PREVIEW_ACTION_SKIP),
)
_FIELDS = ("name", "identity", "department", "note", "group")


class ImportPreviewDialog(QDialog):
    """Edit a parsed import draft; accept = ready for the window to confirm."""

    def __init__(self, draft: ImportDraft, services, source_path, parent=None) -> None:  # noqa: ANN001
        """Build the four-zone preview over the persisted draft batch.

        Args:
            draft: The parsed draft from ``ParseImportDraftService``.
            services: Application service container (parse/confirm services).
            source_path: Absolute roster file path (reparse/sheet listing).
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self.setWindowTitle(text.IMPORT_PREVIEW_TITLE)
        self.resize(960, 560)
        self._services = services
        self._draft = draft
        self._source_file = source_path
        self._has_header = draft.batch.has_header
        self._sheet_name = draft.batch.sheet_name
        self._build_ui()
        self._repopulate()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Lay out options row, draft table, counts row and buttons."""
        layout = QVBoxLayout(self)

        options_row = QHBoxLayout()
        options_row.addWidget(QLabel(
            text.IMPORT_PREVIEW_FILE_LABEL + str(self._draft.batch.file_name), self,
        ))
        options_row.addWidget(QLabel(
            text.IMPORT_PREVIEW_ENCODING_LABEL + str(self._draft.batch.encoding or "—"), self,
        ))
        options_row.addWidget(QLabel(
            text.IMPORT_PREVIEW_DELIMITER_LABEL + str(self._draft.batch.delimiter or "—"), self,
        ))
        self._header_check = QCheckBox(text.IMPORT_PREVIEW_HEADER_LABEL, self)
        self._header_check.setChecked(self._has_header)
        self._header_check.toggled.connect(self._on_options_changed)
        options_row.addWidget(self._header_check)
        self._sheet_combo: QComboBox | None = None
        if self._draft.batch.source_type in ("xlsx", "xlsm", "xls"):
            sheet_names = self._services.parse_import_draft.list_sheets(self._source_file)
            if sheet_names:
                options_row.addWidget(QLabel(text.IMPORT_PREVIEW_SHEET_LABEL, self))
                self._sheet_combo = QComboBox(self)
                self._sheet_combo.addItems(sheet_names)
                if self._sheet_name:
                    index = self._sheet_combo.findText(self._sheet_name)
                    if index >= 0:
                        self._sheet_combo.setCurrentIndex(index)
                self._sheet_combo.currentIndexChanged.connect(self._on_options_changed)
                options_row.addWidget(self._sheet_combo)
        reparse = QPushButton(text.IMPORT_PREVIEW_REPARSE_BUTTON, self)
        reparse.clicked.connect(self._on_options_changed)
        options_row.addWidget(reparse)
        options_row.addStretch()
        layout.addLayout(options_row)

        self._table = QTableWidget(0, 8, self)
        self._table.setHorizontalHeaderLabels([
            text.IMPORT_PREVIEW_COL_RAW,
            text.IMPORT_PREVIEW_COL_NAME,
            text.IMPORT_PREVIEW_COL_IDENTITY,
            text.IMPORT_PREVIEW_COL_DEPARTMENT,
            text.IMPORT_PREVIEW_COL_NOTE,
            text.IMPORT_PREVIEW_COL_WARNINGS,
            text.IMPORT_PREVIEW_COL_ACTION,
            "",
        ])
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed,
        )
        self._table.verticalHeader().setVisible(False)
        self._table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._table, 1)

        counts_row = QHBoxLayout()
        self._counts_label = QLabel(self)
        self._counts_label.setWordWrap(True)
        counts_row.addWidget(self._counts_label)
        counts_row.addStretch()
        layout.addLayout(counts_row)
        # P9：逐次动作反馈（如拆分 no-op 的可见提示），不随重绘清除。
        self._feedback_label = QLabel(self)
        self._feedback_label.setWordWrap(True)
        layout.addWidget(self._feedback_label)
        if len(self._draft.rows) > CONFIRM_SYNC_LIMIT:
            notice = QLabel(
                text.IMPORT_PREVIEW_CONFIRM_LARGE.format(limit=CONFIRM_SYNC_LIMIT), self,
            )
            notice.setWordWrap(True)
            layout.addWidget(notice)

        buttons = QHBoxLayout()
        cancel = QPushButton(text.IMPORT_PREVIEW_CANCEL_BUTTON, self)
        cancel.setDefault(True)
        cancel.clicked.connect(self.reject)
        confirm = QPushButton(text.IMPORT_PREVIEW_CONFIRM_BUTTON, self)
        assign_role(confirm, ROLE_PRIMARY)
        confirm.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

    # ── Data plumbing ────────────────────────────────────────────────────

    @property
    def batch_id(self) -> UUID:
        """The confirmed draft batch id (valid after :meth:`exec` accepts)."""
        return self._draft.batch.id  # type: ignore[return-value]

    @property
    def row_count(self) -> int:
        """Draft row count at accept time (drives sync vs worker confirm)."""
        return len(self._draft.rows)

    def set_source_file(self, path) -> None:  # noqa: ANN001
        """Record the absolute source path (needed for sheet listing/reparse)."""
        self._source_file = path

    def _on_options_changed(self) -> None:
        """Re-parse the file with the current header/sheet options."""
        self._has_header = self._header_check.isChecked()
        if self._sheet_combo is not None:
            self._sheet_name = self._sheet_combo.currentText() or None
        mapping = {field: index for field, index in self._draft.field_mapping.items()}
        self._draft = self._services.parse_import_draft.reparse(
            ReparseImportDraftCommand(
                batch_id=self._draft.batch.id,  # type: ignore[arg-type]
                source_path=self._source_file,
                has_header=self._has_header,
                sheet_name=self._sheet_name,
                field_mapping=mapping,
            ),
        )
        self._repopulate()

    def _repopulate(self) -> None:
        """Rebuild the table from the current draft rows."""
        rows = self._draft.rows
        self._table.blockSignals(True)
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self._table.setItem(row_index, 0, self._readonly_cell("　".join(row.raw_values)))
            name_item = QTableWidgetItem(row.parsed_name)
            self._table.setItem(row_index, 1, name_item)
            self._table.setItem(row_index, 2, self._editable_cell(row.parsed_identity))
            self._table.setItem(row_index, 3, self._editable_cell(row.parsed_department))
            self._table.setItem(row_index, 4, self._editable_cell(row.parsed_note))
            self._table.setItem(row_index, 5, self._readonly_cell(self._warnings_text(row)))
            action = QComboBox(self)
            for value, label in _ACTION_LABELS:
                action.addItem(label, value)
            current = _ACTION_LABELS_INDEX.get(row.action, 0)
            action.setCurrentIndex(current)
            action.currentIndexChanged.connect(
                lambda index, r=row: self._on_action_changed(r, index),
            )
            self._table.setCellWidget(row_index, 6, action)
            if any(w[0] == "multi_name" for w in row.warnings):
                split = QPushButton(text.IMPORT_PREVIEW_SPLIT_BUTTON, self)
                split.clicked.connect(lambda _=False, r=row: self._on_split(r))
                self._table.setCellWidget(row_index, 7, split)
        self._table.blockSignals(False)
        self._refresh_counts()

    @staticmethod
    def _readonly_cell(value: str) -> QTableWidgetItem:
        """Non-editable cell with full text in the tooltip."""
        item = QTableWidgetItem(value)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setToolTip(value)
        return item

    @staticmethod
    def _editable_cell(value: str | None) -> QTableWidgetItem:
        """Editable cell (empty string for None)."""
        return QTableWidgetItem(value or "")

    def _warnings_text(self, row) -> str:  # noqa: ANN001
        """Format the row's structured warnings into one user-readable line."""
        formatted = []
        for code, detail in row.warnings:
            template = text.IMPORT_WARNING_TEXTS.get(code, text.IMPORT_PREVIEW_DEFAULT_WARNING)
            formatted.append(template.format(code=code, detail=detail))
        return "；".join(formatted)

    def _row_for(self, table_row: int):
        """Return the draft row backing a table row (order_index == table order)."""
        return self._draft.rows[table_row]

    _EDITABLE_COLUMNS = {1: "parsed_name", 2: "parsed_identity", 3: "parsed_department", 4: "parsed_note"}

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Persist a committed cell edit back into the draft row."""
        field_name = self._EDITABLE_COLUMNS.get(item.column())
        if field_name is None or item.row() >= len(self._draft.rows):
            return
        row = self._draft.rows[item.row()]
        value = item.text().strip()
        if field_name == "parsed_name":
            row.parsed_name = value  # 姓名保持空串语义（实体校验负责拒绝真空名）
        else:
            setattr(row, field_name, value or None)
        self._draft = self._services.parse_import_draft.save_draft_rows(
            self._draft.batch.id, self._draft.rows,
        )
        self._refresh_counts()

    def _on_action_changed(self, row, index: int) -> None:  # noqa: ANN001
        """Persist an action switch from the per-row combo."""
        row.action = _ACTION_LABELS[index][0]
        self._draft = self._services.parse_import_draft.save_draft_rows(
            self._draft.batch.id, self._draft.rows,
        )
        self._refresh_counts()

    def _on_split(self, row) -> None:  # noqa: ANN001
        """Split one multi-name draft row into one row per name.

        P9：无可拆内容时给出可见反馈（此前为静默 no-op）。
        """
        self._draft, changed = self._services.parse_import_draft.split_draft_row_with_status(
            self._draft.batch.id, row.id,
        )
        if not changed:
            self._feedback_label.setText(text.IMPORT_PREVIEW_SPLIT_NOOP)
        else:
            self._feedback_label.clear()
        self._repopulate()

    def _refresh_counts(self) -> None:
        """Refresh the will-create/merge/skip/warnings counters."""
        warning_rows = sum(1 for row in self._draft.rows if row.warnings)
        self._counts_label.setText(text.IMPORT_PREVIEW_COUNTS.format(
            create=self._draft.create_count,
            merge=self._draft.merge_count,
            skip=self._draft.skip_count,
            warnings=warning_rows,
        ))


_ACTION_LABELS_INDEX = {value: index for index, (value, _) in enumerate(_ACTION_LABELS)}
