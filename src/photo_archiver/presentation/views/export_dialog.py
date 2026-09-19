"""Export dialog for Step 14 Export.

Provides scope selection (all / filtered), output path, and format
(XLSX / CSV / HTML) controls. Follows the ``ArchivePreviewDialog`` precedent
for UI layout and user interaction patterns.

Batch 6: CURRENT_BATCH is removed from the end-user dialog (owner decision —
the scope is a contract placeholder without a persistence design, and an
unselectable radio would dress it up as a feature). The FILTERED scope states
the active criteria summary and the expected photo count, matching what the
photo wall would show for the same filter.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.domain import PhotoSearchCriteria
from photo_archiver.presentation.ui_text import (
    EXPORT_BROWSE_BUTTON,
    EXPORT_CSV_FILTER,
    EXPORT_DEFAULT_FILENAME,
    EXPORT_DIALOG_TITLE,
    EXPORT_FILTERED_SUMMARY,
    EXPORT_FORMAT_CSV,
    EXPORT_FORMAT_HTML,
    EXPORT_FORMAT_LABEL,
    EXPORT_FORMAT_XLSX,
    EXPORT_HTML_FILTER,
    EXPORT_NO_ACTIVE_CRITERIA_HINT,
    EXPORT_NO_PATH_MESSAGE,
    EXPORT_NO_PATH_TITLE,
    EXPORT_OUTPUT_LABEL,
    EXPORT_PATH_PLACEHOLDER,
    EXPORT_SAVE_DIALOG_TITLE,
    EXPORT_SCOPE_ALL,
    EXPORT_SCOPE_ALL_TOOLTIP,
    EXPORT_SCOPE_FILTERED,
    EXPORT_SCOPE_FILTERED_TOOLTIP,
    EXPORT_SCOPE_GROUP,
    EXPORT_XLSX_FILTER,
)

_SCOPE_LABELS = {
    ExportScope.ALL: EXPORT_SCOPE_ALL,
    ExportScope.FILTERED: EXPORT_SCOPE_FILTERED,
}

_SCOPE_TOOLTIPS = {
    ExportScope.ALL: EXPORT_SCOPE_ALL_TOOLTIP,
    ExportScope.FILTERED: EXPORT_SCOPE_FILTERED_TOOLTIP,
}

_NO_ACTIVE_CRITERIA_HINT = EXPORT_NO_ACTIVE_CRITERIA_HINT

_FORMAT_CHOICES = (EXPORT_FORMAT_XLSX, EXPORT_FORMAT_CSV, EXPORT_FORMAT_HTML)


class ExportDialog(QDialog):
    """Collect export parameters and confirm the user's intent.

    The user selects:
    - Export scope (radio buttons: all / current batch / filtered)
    - Output format (combo: XLSX / CSV)
    - Output directory + file name (path picker)
    """

    def __init__(
        self,
        default_output_root: Path | None = None,
        parent: QWidget | None = None,
        active_criteria: PhotoSearchCriteria | None = None,
        filtered_count: int | None = None,
        criteria_summary: str = "",
    ) -> None:
        """Initialize the dialog with an optional default output root.

        Args:
            default_output_root: Default directory for the output file picker.
                Falls back to the current working directory when ``None``.
            active_criteria: The window's active filter criteria, gating the
                FILTERED scope (F3: no criteria → not selectable).
            filtered_count: Photo count the active filter matched (from the
                window's last query); shown with the FILTERED scope (Batch 6).
            criteria_summary: Human-readable summary of the active criteria;
                shown with the FILTERED scope (Batch 6).
        """
        super().__init__(parent)
        self.setWindowTitle(EXPORT_DIALOG_TITLE)
        self.setMinimumWidth(520)
        self._default_output_root = default_output_root or Path.cwd()
        self._output_path: Path | None = None
        self._active_criteria = active_criteria
        self._filtered_count = filtered_count
        self._criteria_summary = criteria_summary
        self._build_ui()

    def _build_ui(self) -> None:
        """Lay out the scope radio group, format combo, path picker, and buttons."""
        main_layout = QVBoxLayout(self)

        # --- Scope ------------------------------------------------------------
        main_layout.addWidget(QLabel(EXPORT_SCOPE_GROUP))
        self._scope_group = QVBoxLayout()
        self._scope_radios: dict[ExportScope, QRadioButton] = {}
        for scope, label in _SCOPE_LABELS.items():
            radio = QRadioButton(label, self)
            radio.setToolTip(_SCOPE_TOOLTIPS[scope])
            if scope is ExportScope.ALL:
                radio.setChecked(True)
            elif scope is ExportScope.FILTERED:
                # F3: only selectable when an active filter criteria exists. A
                # criteria-less FILTERED export would silently behave as ALL —
                # the UI disables it (first UX layer); the Service errors on
                # FILTERED + None criteria (deeper invariant, Commit-2).
                if self._active_criteria is None:
                    radio.setEnabled(False)
                    radio.setToolTip(_NO_ACTIVE_CRITERIA_HINT)
            self._scope_radios[scope] = radio
            self._scope_group.addWidget(radio)
        main_layout.addLayout(self._scope_group)

        # Batch 6: the FILTERED scope states what it will export — the same
        # conditions summary and result count the photo wall shows.
        self._filtered_hint = QLabel(self)
        self._filtered_hint.setWordWrap(True)
        self._filtered_hint.setVisible(False)
        main_layout.addWidget(self._filtered_hint)
        for radio in self._scope_radios.values():
            radio.toggled.connect(self._update_scope_hint)
        self._update_scope_hint()

        # --- Format -----------------------------------------------------------
        fmt_layout = QFormLayout()
        self._format_combo = QComboBox(self)
        for choice in _FORMAT_CHOICES:
            self._format_combo.addItem(choice)
        fmt_layout.addRow(EXPORT_FORMAT_LABEL, self._format_combo)
        main_layout.addLayout(fmt_layout)

        # --- Output path ------------------------------------------------------
        path_layout = QHBoxLayout()
        self._path_edit = QLineEdit(self)
        self._path_edit.setPlaceholderText(EXPORT_PATH_PLACEHOLDER)
        path_layout.addWidget(QLabel(EXPORT_OUTPUT_LABEL))
        path_layout.addWidget(self._path_edit)
        browse_btn = QPushButton(EXPORT_BROWSE_BUTTON, self)
        browse_btn.clicked.connect(self._on_browse)
        path_layout.addWidget(browse_btn)
        main_layout.addLayout(path_layout)

        # --- Buttons ----------------------------------------------------------
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok, self)  # type: ignore[attr-defined]
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    # ── Properties (read by the caller after accept) ─────────────────────────

    def _update_scope_hint(self) -> None:
        """Show the criteria summary + expected count beside the FILTERED scope."""
        filtered_active = self._scope_radios[ExportScope.FILTERED].isChecked()
        has_criteria = self._active_criteria is not None
        self._filtered_hint.setVisible(filtered_active and has_criteria)
        if filtered_active and has_criteria:
            count_text = (
                str(self._filtered_count)
                if self._filtered_count is not None
                else "—"
            )
            self._filtered_hint.setText(EXPORT_FILTERED_SUMMARY.format(
                summary=self._criteria_summary or "—", count=count_text,
            ))

    @property
    def scope(self) -> ExportScope:
        """Return the selected export scope."""
        for scope, radio in self._scope_radios.items():
            if radio.isChecked():
                return scope
        return ExportScope.ALL

    @property
    def output_path(self) -> Path | None:
        """Return the validated output path chosen by the user.

        ``None`` if the user didn't pick one before accepting.
        """
        return self._output_path

    @property
    def format_name(self) -> str:
        """Return the canonical format name for the selected choice.

        Returns ``"xlsx"`` / ``"csv"`` / ``"html"`` for the exporter lookup.
        """
        text = self._format_combo.currentText()
        if "CSV" in text:
            return "csv"
        if "HTML" in text:
            return "html"
        return "xlsx"

    # ── Slots ────────────────────────────────────────────────────────────────

    def _on_browse(self) -> None:
        """Open a file-save dialog and populate the path edit."""
        selected_format = self.format_name
        if selected_format == "xlsx":
            filter_str = EXPORT_XLSX_FILTER
        elif selected_format == "csv":
            filter_str = EXPORT_CSV_FILTER
        else:
            filter_str = EXPORT_HTML_FILTER
        default_name = EXPORT_DEFAULT_FILENAME.format(extension=selected_format)

        path_str, _ = QFileDialog.getSaveFileName(
            self,
            EXPORT_SAVE_DIALOG_TITLE,
            str(self._default_output_root / default_name),
            filter_str,
        )
        if path_str:
            self._path_edit.setText(path_str)

    def _on_accept(self) -> None:
        """Validate the path and accept the dialog."""
        raw = self._path_edit.text().strip()
        if not raw:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, EXPORT_NO_PATH_TITLE, EXPORT_NO_PATH_MESSAGE)
            return
        self._output_path = Path(raw)
        self.accept()
