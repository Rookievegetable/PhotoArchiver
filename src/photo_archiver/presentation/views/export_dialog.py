"""Export dialog for Step 14 Export.

Provides scope selection (all / current batch / filtered), output path,
and format (XLSX / CSV) controls. Follows the ``ArchivePreviewDialog``
precedent for UI layout and user interaction patterns.
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

_SCOPE_LABELS = {
    ExportScope.ALL: "All data (people, photos, matches, archive history)",
    ExportScope.CURRENT_BATCH: "Current batch (most recently processed)",
    ExportScope.FILTERED: "Filtered results (current selection)",
}

_FORMAT_CHOICES = ("Excel (.xlsx)", "CSV (.csv)", "HTML (.html)")


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
    ) -> None:
        """Initialize the dialog with an optional default output root.

        Args:
            default_output_root: Default directory for the output file picker.
                Falls back to the current working directory when ``None``.
        """
        super().__init__(parent)
        self.setWindowTitle("Export Data")
        self.setMinimumWidth(520)
        self._default_output_root = default_output_root or Path.cwd()
        self._output_path: Path | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """Lay out the scope radio group, format combo, path picker, and buttons."""
        main_layout = QVBoxLayout(self)

        # --- Scope ------------------------------------------------------------
        main_layout.addWidget(QLabel("Export scope:"))
        self._scope_group = QVBoxLayout()
        self._scope_radios: dict[ExportScope, QRadioButton] = {}
        for scope, label in _SCOPE_LABELS.items():
            radio = QRadioButton(label, self)
            if scope is ExportScope.ALL:
                radio.setChecked(True)
            self._scope_radios[scope] = radio
            self._scope_group.addWidget(radio)
        main_layout.addLayout(self._scope_group)

        # --- Format -----------------------------------------------------------
        fmt_layout = QFormLayout()
        self._format_combo = QComboBox(self)
        for choice in _FORMAT_CHOICES:
            self._format_combo.addItem(choice)
        fmt_layout.addRow("Format:", self._format_combo)
        main_layout.addLayout(fmt_layout)

        # --- Output path ------------------------------------------------------
        path_layout = QHBoxLayout()
        self._path_edit = QLineEdit(self)
        self._path_edit.setPlaceholderText("Select export file destination …")
        path_layout.addWidget(QLabel("Output:"))
        path_layout.addWidget(self._path_edit)
        browse_btn = QPushButton("Browse…", self)
        browse_btn.clicked.connect(self._on_browse)
        path_layout.addWidget(browse_btn)
        main_layout.addLayout(path_layout)

        # --- Buttons ----------------------------------------------------------
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok, self)  # type: ignore[attr-defined]
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    # ── Properties (read by the caller after accept) ─────────────────────────

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
            filter_str = "Excel files (*.xlsx)"
        elif selected_format == "csv":
            filter_str = "CSV files (*.csv)"
        else:
            filter_str = "HTML files (*.html)"
        default_name = f"export.{selected_format}"

        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save Export As",
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

            QMessageBox.warning(self, "No output path", "Please select an export file destination.")
            return
        self._output_path = Path(raw)
        self.accept()
