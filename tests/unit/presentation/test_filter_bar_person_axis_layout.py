"""P0-3 regression: FilterBar person axis must stay usable after repopulation.

Manual desktop smoke feedback (Phase A P0-3): after a real Excel import, the
"Person:" label was seen painting over the person combo and the combo stopped
responding to clicks. These tests pin the widget contract through the exact
production sequence — construction-time fill, then a post-import refill —
asserting geometry (no overlap), usability, and content.
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QLabel

from photo_archiver.domain import Person
from photo_archiver.presentation.views.filter_bar import FilterBar


def _persons() -> list[Person]:
    """Two real person aggregates (ids are set by Person.__post_init__)."""
    return [Person(name="Alice", identity="A001"), Person(name="Bob", identity="B002")]


def test_person_label_and_combo_do_not_overlap_after_repopulation(qtbot) -> None:
    """The exact production sequence: initial fill, then post-import refill."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    bar.resize(1200, 40)
    bar.show()

    bar.set_persons(_persons())  # construction-time fill
    bar.set_persons(_persons())  # post-import refill (_on_completed path)

    label = bar.findChild(QLabel)
    combo = bar._person_combo
    assert label is not None and combo is not None
    assert not label.geometry().intersects(combo.geometry()), (
        f"label {label.geometry()} overlaps combo {combo.geometry()}"
    )
    assert combo.geometry().left() >= label.geometry().right(), (
        f"combo {combo.geometry()} must sit right of label {label.geometry()}"
    )


def test_person_combo_stays_usable_after_repopulation(qtbot) -> None:
    """After refills the combo is enabled, correct, and reset to no-constraint."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    bar.resize(1200, 40)
    bar.show()

    bar.set_persons(_persons())
    bar.set_persons(_persons())

    combo = bar._person_combo
    assert combo.isEnabled()
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "All persons",
        "Alice",
        "Bob",
    ]
    assert combo.currentIndex() == 0  # reset to the no-constraint entry


def test_filter_bar_paints_its_own_background(qtbot) -> None:
    """The bar must fill its rect, or reflows leave ghost pixels on desktop."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    bar.show()
    assert bar.autoFillBackground() is True
