"""SettingsDialog — Step 13 user-facing preferences editor.

Modal ``QDialog`` presenting the six ``UserPreferences`` fields with inline
validation. The dialog holds NO business logic:

- load on construction via the injected ``SettingsController``;
- save on ``accept`` only after the candidate passes ``SettingsController.save``;
- validation errors surface as a non-blocking ``QMessageBox`` listing every
  offending field so the user fixes all issues in one pass.

Field layout:
    Theme          QComboBox (system / light / dark)
    Language       QComboBox (system / zh / en) — i18n placeholder
    Default import QFileDialog picker (folder)
    Default export QFileDialog picker (folder)
    Match threshold QDoubleSpinBox (0.0 - 1.0)
    Max workers     QSpinBox (1 - 32)

The dialog is owned by the caller (passes ``parent``); on ``exec()`` it
returns ``QDialog.Accepted`` after a successful save or ``QDialog.Rejected``
on cancel / validation failure that the user chose to abandon.
"""

from pathlib import Path

from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.dtos.settings import (
    InvalidPreferencesError,
    MAX_MATCH_THRESHOLD,
    MAX_MAX_WORKERS,
    MIN_MATCH_THRESHOLD,
    MIN_MAX_WORKERS,
    UserPreferences,
    VALID_LANGUAGES,
    VALID_THEMES,
)
from photo_archiver.presentation.controllers.settings_controller import SettingsController

# Threshold spin box decimal precision — match_threshold is a similarity ratio
# in [0.0, 1.0] so two decimal places is the smallest meaningful increment.
_THRESHOLD_DECIMALS = 2
# Single-step granularity for the threshold spinner (review m-10: named constant).
_THRESHOLD_SINGLE_STEP = 0.05


class SettingsDialog(QDialog):
    """Modal dialog for editing UserPreferences through a SettingsController."""

    def __init__(
        self,
        controller: SettingsController,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the dialog, load current preferences, and lay out fields.

        Args:
            controller: Bridge to the Application-layer SettingsService. The
                dialog calls ``controller.load()`` once on construction so
                the form starts from the persisted values, not the defaults.
            parent: Optional Qt parent for ownership / cleanup.
        """
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self._controller = controller
        self._preferences: UserPreferences | None = None  # lazy-loaded on first showEvent
        self._build_form()
        # Initial widget state uses dataclass defaults until showEvent loads
        # the persisted values, so the dialog is never shown with empty fields.
        self._populate_from_preferences(UserPreferences())

    def showEvent(self, event: QShowEvent) -> None:
        """Load persisted preferences on first show to keep construction cheap.

        Construction-time ``controller.load()`` would hit QSettings (registry /
        plist / conf) synchronously and may block the UI thread on cold reads
        or roaming profiles (review M-5). Deferring to first show keeps the
        constructor fast and only pays the load cost when the user actually
        opens the dialog.
        """
        if self._preferences is None:
            self._preferences = self._controller.load()
            self._populate_from_preferences(self._preferences)
        super().showEvent(event)

    def _build_form(self) -> None:
        """Lay out the six UserPreferences fields in a QFormLayout."""
        self._theme_combo = QComboBox(self)
        self._theme_combo.addItems(VALID_THEMES)

        self._language_combo = QComboBox(self)
        self._language_combo.addItems(VALID_LANGUAGES)

        self._import_path_edit = QLineEdit(self)
        self._import_path_edit.setPlaceholderText("(use system default)")
        self._import_browse = QPushButton("Browse...", self)
        self._import_browse.clicked.connect(self._on_import_browse)

        self._export_path_edit = QLineEdit(self)
        self._export_path_edit.setPlaceholderText("(use system default)")
        self._export_browse = QPushButton("Browse...", self)
        self._export_browse.clicked.connect(self._on_export_browse)

        self._threshold_spin = QDoubleSpinBox(self)
        self._threshold_spin.setRange(MIN_MATCH_THRESHOLD, MAX_MATCH_THRESHOLD)
        self._threshold_spin.setDecimals(_THRESHOLD_DECIMALS)
        self._threshold_spin.setSingleStep(_THRESHOLD_SINGLE_STEP)

        self._workers_spin = QSpinBox(self)
        self._workers_spin.setRange(MIN_MAX_WORKERS, MAX_MAX_WORKERS)

        form = QFormLayout()
        form.addRow("Theme", self._theme_combo)
        form.addRow("Language", self._language_combo)
        form.addRow("Default import path", self._import_path_layout())
        form.addRow("Default export path", self._export_path_layout())
        form.addRow("Match threshold", self._threshold_spin)
        form.addRow("Max workers", self._workers_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addStretch(1)
        layout.addWidget(QLabel("Save commits to platform preferences. Cancel discards edits."))
        layout.addWidget(buttons)

    def _import_path_layout(self) -> QWidget:
        """Wrap the import path edit + browse button in a single horizontal row."""
        wrapper = QWidget(self)
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._import_path_edit, 1)
        row.addWidget(self._import_browse, 0)
        return wrapper

    def _export_path_layout(self) -> QWidget:
        """Wrap the export path edit + browse button in a single horizontal row."""
        wrapper = QWidget(self)
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._export_path_edit, 1)
        row.addWidget(self._export_browse, 0)
        return wrapper

    def _populate_from_preferences(self, preferences: UserPreferences) -> None:
        """Set each widget value from the loaded UserPreferences."""
        self._theme_combo.setCurrentText(preferences.theme)
        self._language_combo.setCurrentText(preferences.language)
        self._import_path_edit.setText(
            str(preferences.default_import_path) if preferences.default_import_path is not None else ""
        )
        self._export_path_edit.setText(
            str(preferences.default_export_path) if preferences.default_export_path is not None else ""
        )
        self._threshold_spin.setValue(preferences.match_threshold)
        self._workers_spin.setValue(preferences.max_workers)

    def _on_import_browse(self) -> None:
        """Open a folder picker and write the selected path into the import edit."""
        folder = QFileDialog.getExistingDirectory(self, "Select Default Import Folder")
        if folder:
            self._import_path_edit.setText(folder)

    def _on_export_browse(self) -> None:
        """Open a folder picker and write the selected path into the export edit."""
        folder = QFileDialog.getExistingDirectory(self, "Select Default Export Folder")
        if folder:
            self._export_path_edit.setText(folder)

    def _collect_preferences(self) -> UserPreferences:
        """Read every widget value into a fresh UserPreferences value object."""
        import_text = self._import_path_edit.text().strip()
        export_text = self._export_path_edit.text().strip()
        return UserPreferences(
            theme=self._theme_combo.currentText(),
            language=self._language_combo.currentText(),
            default_import_path=Path(import_text) if import_text else None,
            default_export_path=Path(export_text) if export_text else None,
            match_threshold=self._threshold_spin.value(),
            max_workers=self._workers_spin.value(),
        )

    def _on_save(self) -> None:
        """Validate + persist via the controller, surfacing violations inline.

        ``InvalidPreferencesError`` carries a combined ``; ``-joined message
        from ``validate_preferences``; we display it verbatim so the user
        sees every field that needs fixing in one dialog. The SettingsDialog
        stays open on validation failure (does NOT call ``accept``) so the
        user keeps their edits.
        """
        candidate = self._collect_preferences()
        try:
            self._controller.save(candidate)
        except InvalidPreferencesError as exc:
            QMessageBox.warning(
                self,
                "Invalid settings",
                self._controller.format_validation_error(exc),
            )
            return
        self.accept()
