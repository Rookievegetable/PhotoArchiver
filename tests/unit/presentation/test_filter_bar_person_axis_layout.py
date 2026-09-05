"""P0-3 regression: FilterBar person axis must stay usable after repopulation.

Manual desktop smoke feedback (Phase A P0-3): after a real Excel import, the
"人员：" label was seen painting over the person combo and the combo stopped
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
        "全部人员",
        "Alice",
        "Bob",
    ]
    assert combo.currentIndex() == 0  # reset to the no-constraint entry


def test_to_date_edit_is_managed_by_the_layout(qtbot) -> None:
    """P0-3: the To edit must sit in the row, right of its checkbox.

    Regression for the Phase 9 gap: ``_to_edit`` was never added to the
    layout, so it floated as an unmanaged child at (0, 0, 100, 30) — painting
    its frame and date text over the Person axis and swallowing that area's
    clicks on the real desktop.
    """
    bar = FilterBar()
    qtbot.addWidget(bar)
    bar.resize(1200, 40)
    bar.show()

    person_combo = bar._person_combo
    to_check = bar._to_check
    to_edit = bar._to_edit

    # Managed by the row: right of its own checkbox, no overlap anywhere.
    assert to_edit.geometry().left() >= to_check.geometry().right()
    assert not to_edit.geometry().intersects(person_combo.geometry()), (
        f"to_edit {to_edit.geometry()} overlaps person combo {person_combo.geometry()}"
    )
    assert not to_edit.geometry().intersects(bar.findChild(QLabel).geometry()), (
        "to_edit overlaps the Person label"
    )
    # The From edit sits symmetrically right of its own checkbox.
    assert bar._from_edit.geometry().left() >= bar._from_check.geometry().right()
