"""ReviewDialog — Step 13 fix: user-facing recognition review panel.

Modal ``QDialog`` listing pending recognition results with inline approve/reject
controls. The dialog holds NO business logic:

- load on construction via the injected ``ReviewController``;
- approve/reject forward to the controller synchronously (<10ms SQLite per
  Step 12 裁决 A);
- after each transition the list re-fetches ``list_pending`` so the user sees
  the remaining queue shrink, and the dialog closes when the queue is empty.

Layout:
    QListWidget rows: "photo={path} person={name} confidence={0.NN}"
    [Approve Selected] [Reject Selected] [Approve All] [Close]

This closes the review dead-end raised in the second-round review (no CLI
existed, no UI path could flip a result to APPROVED → archive was always
empty). Step 13 ships the UI path; a CLI review command is a follow-up.
"""

from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.domain import RecognitionResult
from photo_archiver.presentation.controllers.review_controller import ReviewController


class ReviewDialog(QDialog):
    """Modal dialog for reviewing pending recognition results."""

    def __init__(
        self,
        controller: ReviewController,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the dialog and load the pending queue.

        Args:
            controller: Bridge to the Application-layer ReviewRecognitionService.
            parent: Optional Qt parent for ownership / cleanup.
        """
        super().__init__(parent)
        self.setWindowTitle("Review Pending Recognition")
        self._controller = controller
        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        """Lay out the list + action buttons."""
        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

        self._approve_selected = QPushButton("Approve Selected", self)
        self._approve_selected.clicked.connect(self._on_approve_selected)
        self._reject_selected = QPushButton("Reject Selected", self)
        self._reject_selected.clicked.connect(self._on_reject_selected)
        self._approve_all = QPushButton("Approve All", self)
        self._approve_all.clicked.connect(self._on_approve_all)

        button_row = QHBoxLayout()
        button_row.addWidget(self._approve_selected)
        button_row.addWidget(self._reject_selected)
        button_row.addWidget(self._approve_all)

        close_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close,
            parent=self,
        )
        close_buttons.rejected.connect(self.reject)

        self._status = QLabel(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self._list, 1)
        layout.addLayout(button_row)
        layout.addWidget(self._status)
        layout.addWidget(close_buttons)

    def _refresh_list(self) -> None:
        """Reload pending results from the controller; close dialog when queue empty."""
        pending = self._controller.list_pending()
        self._list.clear()
        for result in pending:
            self._list.addItem(self._make_row(result))
        self._status.setText(
            f"{len(pending)} pending result(s). Select rows then Approve/Reject, "
            f"or Approve All to finalize the queue."
        )
        if not pending:
            self.accept()

    @staticmethod
    def _make_row(result: RecognitionResult) -> QListWidgetItem:
        """Build a list row carrying the recognition result id for retrieve on action."""
        item = QListWidgetItem(
            f"photo={result.photo_id} person={result.person_id} confidence={result.confidence:.2f}"
        )
        item.setData(Qt.ItemDataRole.UserRole, result.id)
        return item

    def _selected_ids(self) -> tuple[UUID, ...]:
        """Return the UUIDs carried by the currently selected list rows."""
        ids: list[UUID] = []
        for item in self._list.selectedItems():
            value = item.data(Qt.ItemDataRole.UserRole)
            if value is not None:
                ids.append(value)
        return tuple(ids)

    def _on_approve_selected(self) -> None:
        """Approve each selected pending result; refresh the list afterwards."""
        ids = self._selected_ids()
        if ids:
            self._controller.bulk_approve(ids)
        self._refresh_list()

    def _on_reject_selected(self) -> None:
        """Reject each selected pending result; refresh the list afterwards."""
        ids = self._selected_ids()
        if ids:
            self._controller.bulk_reject(ids)
        self._refresh_list()

    def _on_approve_all(self) -> None:
        """Approve every pending result in one batch; refresh the list afterwards."""
        all_ids = tuple(
            item.data(Qt.ItemDataRole.UserRole)
            for item in [self._list.item(i) for i in range(self._list.count())]
        )
        if all_ids:
            self._controller.bulk_approve(all_ids)
        self._refresh_list()
