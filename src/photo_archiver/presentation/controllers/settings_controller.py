"""Controller coordinating the settings workflow with the UI.

Step 13 settings dialog controller: bridges the SettingsController surface
between the SettingsDialog (QDialog UI) and the Application-layer
SettingsService. The controller holds NO business logic — it forwards
load/save calls to the use case and translates raised InvalidPreferencesError
into user-facing message strings so the dialog can keep them on-screen.

Cancellation behavior: ``cancel`` is a UI-only operation and therefore lives
here (controller) not on the use case. The dialog's edited field values are
discarded by the dialog itself when it returns QDialog.Rejected; the
controller does not need to call the service on cancel.
"""

from PySide6.QtCore import QObject

from photo_archiver.application import InvalidPreferencesError, SettingsUseCase, UserPreferences


class SettingsController(QObject):
    """Bridge settings use case calls to synchronous UI refresh."""

    def __init__(
        self,
        use_case: SettingsUseCase,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with its settings use case.

        Args:
            use_case: load/save user preferences use case boundary.
            parent: Optional Qt parent for ownership / cleanup.
        """
        super().__init__(parent)
        self._use_case = use_case

    def load(self) -> UserPreferences:
        """Return the currently persisted user preferences."""
        return self._use_case.load()

    def save(self, preferences: UserPreferences) -> None:
        """Validate and persist the candidate preferences.

        Args:
            preferences: Candidate preferences value object.

        Raises:
            InvalidPreferencesError: When any field violates its bound. The
                controller does NOT catch this — the dialog surfaces the
                message string so the user can fix all fields in one pass
                rather than losing their edits on a partial-validation popup.
        """
        self._use_case.save(preferences)

    @staticmethod
    def format_validation_error(error: InvalidPreferencesError) -> str:
        """Translate a multi-field validation error into a user-facing message.

        ``InvalidPreferencesError`` already carries a combined ``; ``-joined
        message from ``validate_preferences``; this helper keeps the
        formatting policy in one place so future i18n can swap it without
        touching the dialog.
        """
        return str(error)
