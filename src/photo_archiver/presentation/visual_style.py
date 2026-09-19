"""Centralized visual system for the desktop UI (Batch 7, UI-rules §16).

Single source for the cross-widget look: button hierarchy (primary /
secondary / danger), focus ring, spacing and the empty-state card. Styles are
applied as ONE application-level stylesheet built here — individual widgets
never call ``setStyleSheet`` themselves; they opt into a hierarchy role via
:func:`assign_role` (a dynamic property) or an objectName.

Palette access uses the QSS *function* form — ``palette(Highlight)`` —
because Qt 6 does not support the ``palette.Highlight`` dot syntax: a single
invalid rule makes Qt reject the whole application stylesheet ("Could not
parse application stylesheet"), silently disabling every Batch 7 visual.
Disabled states are expressed with the ``:disabled`` pseudo-state, never as
a second palette() argument. ``test_visual_system.py`` guards both the
syntax and the real rendering (parse-warning capture + pixel probes).

Qt 6.11.1 evidence (render probes, kept here so the card scheme is not
"fixed" back into a broken form): on the plain-QWidget background painting
path every ``palette(<Role>)`` reference collapses to the window color —
only fixed/rgba colors actually paint. The card therefore uses theme-neutral
translucent rgba() tones, which render a visible tint, border and radius in
light AND dark themes; buttons paint through a different path where
``palette(Highlight)`` resolves correctly (probe-verified).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QSizePolicy, QWidget

# Dynamic-property key carrying the visual role on QAbstractButton.
ROLE_PROPERTY = "styleRole"
ROLE_PRIMARY = "primary"
ROLE_DANGER = "danger"

# objectName hooks for non-button building blocks.
EMPTY_STATE_CARD_OBJECT_NAME = "EmptyStateCard"

# The only fixed brand color: it must stay recognizable across themes
# because it marks irreversible actions.
_DANGER_COLOR = "#c62828"
_DANGER_BORDER = "#8e1f1c"

_STYLESHEET = """
QPushButton { padding: 4px 14px; }
QPushButton[styleRole="primary"] {
    background-color: palette(Highlight);
    color: palette(HighlightedText);
    border: 1px solid palette(Highlight);
    font-weight: 600;
    padding: 5px 18px;
}
QPushButton[styleRole="danger"] {
    background-color: #c62828;
    color: #ffffff;
    border: 1px solid #8e1f1c;
    font-weight: 600;
    padding: 5px 18px;
}
QPushButton[styleRole="primary"]:disabled {
    color: palette(ButtonText);
    background-color: palette(Button);
    border: 1px solid palette(Mid);
    font-weight: 400;
}
QPushButton[styleRole="danger"]:disabled {
    color: palette(ButtonText);
    background-color: palette(Button);
    border: 1px solid palette(Mid);
    font-weight: 400;
}
QPushButton:focus, QToolButton:focus {
    border: 2px solid palette(Highlight);
}
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus {
    border: 2px solid palette(Highlight);
}
QListWidget:focus, QListView:focus {
    border: 1px solid palette(Highlight);
}
QWidget#EmptyStateCard {
    background-color: rgba(127, 127, 127, 0.12);
    border: 1px solid rgba(127, 127, 127, 0.45);
    border-radius: 6px;
}
"""


def build_stylesheet() -> str:
    """Return the application-level stylesheet (single replacement point)."""
    return _STYLESHEET


def apply_visual_system(app: QApplication) -> None:
    """Install the visual system once, right after QApplication creation."""
    app.setStyleSheet(_STYLESHEET)


def assign_role(button: QPushButton, role: str) -> None:
    """Tag a button with a visual role and refresh any installed stylesheet."""
    button.setProperty(ROLE_PROPERTY, role)
    _repolish(button)


def _repolish(widget: QWidget) -> None:
    """Force the QSS engine to re-evaluate property-dependent selectors."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def style_empty_state_card(page: QWidget) -> None:
    """Give an empty-state page the shared card look via its objectName.

    ``WA_StyledBackground`` makes the stylesheet background/border/radius
    actually paint for this widget — required for any QWidget that Qt does
    not style through a plain fill (and harmless for plain instances).
    """
    page.setObjectName(EMPTY_STATE_CARD_OBJECT_NAME)
    page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


def button_role(button: QPushButton) -> str | None:
    """Return the assigned role (test/QA hook)."""
    return button.property(ROLE_PROPERTY)
