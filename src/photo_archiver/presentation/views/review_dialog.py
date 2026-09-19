"""ReviewDialog — Step 13 fix + Batch 5: a review board, not a blind batch.

Modal ``QDialog`` listing pending recognition results with inline
approve/reject controls. The dialog holds NO business logic:

- load on construction via the injected ``ReviewController``;
- approve/reject forward to the controller synchronously (<10ms SQLite per
  Step 12 裁决 A);
- after each transition the list re-fetches ``list_pending`` so the user sees
  the remaining queue shrink. An empty queue no longer auto-closes the dialog:
  Batch 2 keeps it open with an explicit empty state so the entry point is
  inspectable instead of appearing to "flash and vanish".

Batch 5 (可审阅而非盲批):

- queue header moved to the TOP of the dialog and always states the pending
  total;
- each row is two lines: human-readable photo/person labels plus an explicit
  textual confidence reading (band + exact value kept for audit) and the
  record status — never a bare decimal, never color-only semantics;
- optional ``thumbnail_source`` (the main window's PhotoListController) feeds
  row thumbnails through the existing async loader — the dialog itself never
  touches disk;
- approve/reject buttons carry the exact selected count; "approve all"
  requires an explicit confirmation stating the count and that there is no
  in-app bulk undo.

Layout:
    [待审核 N 条。…]
    QListWidget rows: "照片={file}　人员={name}" / "置信度：较高（0.87）· 状态：待审核"
    [通过所选（n）] [拒绝所选（n）] [全部通过（N）] [Close]
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.domain import RecognitionResult
from photo_archiver.presentation.controllers.review_controller import ReviewController
from photo_archiver.presentation.ui_text import (
    REVIEW_APPROVE_ALL,
    REVIEW_APPROVE_ALL_CONFIRM,
    REVIEW_APPROVE_ALL_CONFIRM_TITLE,
    REVIEW_APPROVE_ALL_COUNTED,
    REVIEW_APPROVE_SELECTED,
    REVIEW_APPROVE_SELECTED_COUNTED,
    REVIEW_CONFIDENCE_FORMAT,
    REVIEW_CONFIDENCE_HIGH,
    REVIEW_CONFIDENCE_LOW,
    REVIEW_CONFIDENCE_MEDIUM,
    REVIEW_CONFIDENCE_VERY_HIGH,
    REVIEW_DIALOG_TITLE,
    REVIEW_EMPTY,
    REVIEW_REJECT_SELECTED,
    REVIEW_REJECT_SELECTED_COUNTED,
    REVIEW_ROW_DETAIL_FORMAT,
    REVIEW_ROW_FORMAT,
    REVIEW_STATUS_LINE,
    STATUS_BADGE_PENDING,
)

if TYPE_CHECKING:
    from photo_archiver.presentation.controllers.photo_list_controller import (
        PhotoListController,
    )

# Confidence bands for the textual reading (exact value stays on the row for
# audit — these thresholds only pick the wording, never gate any decision).
_CONFIDENCE_VERY_HIGH_FLOOR = 0.90
_CONFIDENCE_HIGH_FLOOR = 0.75
_CONFIDENCE_MEDIUM_FLOOR = 0.60


def confidence_band(confidence: float) -> str:
    """Return the textual band for a match confidence (Batch 5 wording only)."""
    if confidence >= _CONFIDENCE_VERY_HIGH_FLOOR:
        return REVIEW_CONFIDENCE_VERY_HIGH
    if confidence >= _CONFIDENCE_HIGH_FLOOR:
        return REVIEW_CONFIDENCE_HIGH
    if confidence >= _CONFIDENCE_MEDIUM_FLOOR:
        return REVIEW_CONFIDENCE_MEDIUM
    return REVIEW_CONFIDENCE_LOW


class ReviewDialog(QDialog):
    """Modal dialog for reviewing pending recognition results."""

    def __init__(
        self,
        controller: ReviewController,
        parent: QWidget | None = None,
        thumbnail_source: PhotoListController | None = None,
    ) -> None:
        """Initialize the dialog and load the pending queue.

        Args:
            controller: Bridge to the Application-layer ReviewRecognitionService.
            parent: Optional Qt parent for ownership / cleanup.
            thumbnail_source: Optional PhotoListController-like object providing
                ``load_thumbnail(photo_id, source_path)`` and a
                ``thumbnail_loaded(object, object)`` signal — the existing
                async, off-UI-thread thumbnail channel. The dialog only
                renders what arrives; it never reads the disk itself.
        """
        super().__init__(parent)
        self.setWindowTitle(REVIEW_DIALOG_TITLE)
        self._controller = controller
        self._thumbnail_source = thumbnail_source
        self._items_by_photo_id: dict[UUID, list[QListWidgetItem]] = {}
        self._build_ui()
        if thumbnail_source is not None:
            # Connect once — _request_row_thumbnail may register many rows and
            # a per-row connect would multiply every arriving signal.
            thumbnail_source.thumbnail_loaded.connect(self._attach_thumbnail)
        self._refresh_list()

    def _build_ui(self) -> None:
        """Lay out the header, list and action buttons (Batch 5 order)."""
        self._status = QLabel(self)
        self._status.setWordWrap(True)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.setWordWrap(True)

        self._approve_selected = QPushButton(REVIEW_APPROVE_SELECTED, self)
        self._approve_selected.clicked.connect(self._on_approve_selected)
        self._reject_selected = QPushButton(REVIEW_REJECT_SELECTED, self)
        self._reject_selected.clicked.connect(self._on_reject_selected)
        self._approve_all = QPushButton(REVIEW_APPROVE_ALL, self)
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

        layout = QVBoxLayout(self)
        layout.addWidget(self._status)  # 待审核总数常驻列表顶部（Batch 5）
        layout.addWidget(self._list, 1)
        layout.addLayout(button_row)
        layout.addWidget(close_buttons)

        # Wire selection changes → per-button enablement + counted texts (done
        # after the first refresh so construction-time selection changes are
        # inert). Keyboard multi-select works via ExtendedSelection defaults.
        self._list.itemSelectionChanged.connect(self._update_action_buttons)

    def _refresh_list(self) -> None:
        """Reload pending results; keep the dialog open with an empty state."""
        pending = self._controller.list_pending()
        self._list.clear()
        self._items_by_photo_id = {}
        for result in pending:
            self._list.addItem(self._make_row(result))
        # Batch 2: an emptied queue stays open and inspectable instead of
        # auto-closing; the entry must never appear to "flash and vanish".
        has_pending = bool(pending)
        self._list.setVisible(has_pending)
        self._status.setText(
            REVIEW_STATUS_LINE.format(count=len(pending)) if has_pending else REVIEW_EMPTY
        )
        self._update_action_buttons()
        if has_pending:
            self._list.setFocus()

    def _update_action_buttons(self) -> None:
        """Enable queue actions and state the exact object counts (Batch 5)."""
        has_rows = self._list.count() > 0
        selection = self._list.selectedItems()
        self._approve_all.setEnabled(has_rows)
        self._approve_all.setText(
            REVIEW_APPROVE_ALL_COUNTED.format(count=self._list.count())
            if has_rows
            else REVIEW_APPROVE_ALL
        )
        self._approve_selected.setEnabled(has_rows and bool(selection))
        self._reject_selected.setEnabled(has_rows and bool(selection))
        if selection:
            counted = REVIEW_APPROVE_SELECTED_COUNTED.format(count=len(selection))
            rejected = REVIEW_REJECT_SELECTED_COUNTED.format(count=len(selection))
        else:
            counted = REVIEW_APPROVE_SELECTED
            rejected = REVIEW_REJECT_SELECTED
        self._approve_selected.setText(counted)
        self._reject_selected.setText(rejected)

    def _make_row(self, result: RecognitionResult) -> QListWidgetItem:
        """Build a two-line review row carrying the result id for actions.

        ADR-036: rows show human-readable photo file name and person name
        (resolved through the controller's read-side lookups) instead of bare
        UUIDs; unknown entities fall back to the UUID / 未知人员. Batch 5:
        the confidence is a textual band with the exact value kept in
        parentheses for audit, and the row states its status explicitly.
        """
        photo_label, person_label = self._controller.resolve_row_labels(result)
        confidence_text = REVIEW_CONFIDENCE_FORMAT.format(
            band=confidence_band(result.confidence), value=result.confidence,
        )
        item = QListWidgetItem("\n".join((
            REVIEW_ROW_FORMAT.format(
                photo_label=photo_label, person_label=person_label,
            ),
            REVIEW_ROW_DETAIL_FORMAT.format(
                confidence_text=confidence_text, status=STATUS_BADGE_PENDING,
            ),
        )))
        item.setData(Qt.ItemDataRole.UserRole, result.id)
        self._request_row_thumbnail(item, result)
        return item

    def _request_row_thumbnail(self, item: QListWidgetItem, result: RecognitionResult) -> None:
        """Route one row's thumbnail through the shared async loader, if given.

        The photo entity comes from the controller's read-side lookup; a
        missing entity simply leaves the row without an icon. Items register
        under their photo id so the loader's signal can attach the image.
        """
        if self._thumbnail_source is None:
            return
        photo = self._controller.photo_for(result)
        if photo is None or photo.id is None:
            return
        self._items_by_photo_id.setdefault(photo.id, []).append(item)
        self._thumbnail_source.load_thumbnail(photo.id, photo.path.raw_path)

    def _attach_thumbnail(self, photo_id: object, thumbnail: object) -> None:
        """Attach an arrived thumbnail to every row of that photo (no-op on miss)."""
        if not isinstance(photo_id, UUID) or thumbnail is None:
            return
        items = self._items_by_photo_id.get(photo_id)
        if not items:
            return
        icon = QIcon(str(thumbnail))
        for item in items:
            item.setIcon(icon)

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
        """Approve every pending result — behind an explicit count confirmation.

        Batch 5: a full-queue approval is the one blind-batch hazard, so it
        must be confirmed with the exact count and an honest statement that
        the app offers no bulk undo. Cancel (the default) changes nothing.
        """
        all_ids = tuple(
            item.data(Qt.ItemDataRole.UserRole)
            for item in [self._list.item(i) for i in range(self._list.count())]
        )
        if not all_ids:
            return
        answer = QMessageBox.question(
            self,
            REVIEW_APPROVE_ALL_CONFIRM_TITLE,
            REVIEW_APPROVE_ALL_CONFIRM.format(count=len(all_ids)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._controller.bulk_approve(all_ids)
        self._refresh_list()
