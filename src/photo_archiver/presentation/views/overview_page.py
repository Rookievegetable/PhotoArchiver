"""Overview page: the five-step archive checklist and one primary CTA.

Batch 3 (UI/UX 收口) flow-driven workbench home. The widget renders an
:class:`OverviewModel` produced by :class:`OverviewPresenter` and re-emits
the chosen primary action; it performs no queries and holds no business
rules (Widget 不访问 Repository/SQLite, DEP-003/DEP-004).
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.controllers.overview_presenter import (
    OverviewModel,
)

from loguru import logger


class OverviewPage(QWidget):
    """Checklist of the archival flow with a single guided next action."""

    primary_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the static frame: title, five rows, primary CTA, privacy note."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self._title = QLabel(text.OVERVIEW_TITLE, self)
        layout.addWidget(self._title)

        self._step_labels: list[QLabel] = []
        for _ in range(5):
            label = QLabel(self)
            label.setWordWrap(True)
            self._step_labels.append(label)
            layout.addWidget(label)

        layout.addStretch()
        self._primary_button = QPushButton(self)
        self._primary_button.clicked.connect(self._emit_primary)
        layout.addWidget(self._primary_button)
        layout.addStretch()

        privacy = QLabel(text.OVERVIEW_PRIVACY_NOTE, self)
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        self._model = OverviewModel((), None, "", "")

    @Slot()
    def _emit_primary(self) -> None:
        """Re-emit the rendered primary action id for the window to dispatch."""
        if self._model.primary is not None:
            logger.debug("Overview primary action {} requested", self._model.primary)
            self.primary_clicked.emit(self._model.primary)

    def render_model(self, model: OverviewModel) -> None:
        """Replace the checklist text, CTA label and CTA enablement."""
        self._model = model
        for label, step in zip(self._step_labels, model.steps, strict=False):
            mark = text.OVERVIEW_STEP_DONE_MARK if step.done else text.OVERVIEW_STEP_TODO_MARK
            label.setText(text.OVERVIEW_STEP_FORMAT.format(
                mark=mark, label=step.label, detail=step.detail,
            ))
        has_primary = model.primary is not None
        self._primary_button.setVisible(has_primary)
        self._primary_button.setText(model.primary_label)
        self._primary_button.setToolTip(model.primary_tooltip)
        self._primary_button.setEnabled(has_primary)

    def set_busy(self, busy: bool, label: str) -> None:
        """Keep the CTA unusable while another long task owns the window."""
        if busy:
            self._primary_button.setEnabled(False)
            self._primary_button.setToolTip(
                text.OVERVIEW_PRIMARY_BUSY.format(label=label),
            )
        elif self._model.primary is not None:
            self._primary_button.setEnabled(True)
            self._primary_button.setToolTip(self._model.primary_tooltip)
