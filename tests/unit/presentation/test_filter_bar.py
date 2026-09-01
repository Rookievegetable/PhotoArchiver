"""FilterBar unit tests — date-range axis enablement (Phase 9, FEAT-P9-1).

Covers the gated date-range semantics: an unchecked "From"/"To" checkbox is
the explicit "unset" representation (QDateTimeEdit always holds a value), a
checked box contributes its edit's datetime to the emitted
``PhotoSearchCriteria``, ``from > to`` is passed through verbatim (the
repository range semantics simply match nothing), combinations with the
status axis keep AND semantics, and ``clear()`` returns every axis to unset.

Pure widget-level tests over the real ``FilterBar``; no repository is
involved (criteria emission is the contract under test).
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from datetime import datetime

from PySide6.QtCore import QDateTime

from photo_archiver.domain import MatchStatus
from photo_archiver.presentation.views.filter_bar import FilterBar


class _CriteriaRecorder:
    """Collect criteria_changed emissions for assertions."""

    def __init__(self, bar: FilterBar) -> None:
        self.emissions: list[object] = []
        bar.criteria_changed.connect(self.emissions.append)

    @property
    def last(self):
        assert self.emissions, "expected at least one criteria emission"
        return self.emissions[-1]


def _set(edit, year: int, month: int, day: int) -> None:
    edit.setDateTime(QDateTime(year, month, day, 12, 0, 0))


def test_unchecked_date_gates_mean_no_date_constraint(qtbot) -> None:
    """Default (unchecked) state emits None — no hidden date constraint."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    bar._from_check.setChecked(True)  # constrain ...
    assert recorder.last.captured_from is not None
    bar._from_check.setChecked(False)  # ... then unset again
    assert recorder.last is None  # back to "no criteria at all"


def test_from_only_emits_captured_from_only(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    _set(bar._from_edit, 2023, 5, 1)
    bar._from_check.setChecked(True)

    criteria = recorder.last
    assert criteria is not None
    assert criteria.captured_from == datetime(2023, 5, 1, 12, 0, 0)
    assert criteria.captured_to is None
    assert criteria.person_id is None and criteria.match_status is None


def test_to_only_emits_captured_to_only(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    _set(bar._to_edit, 2024, 6, 30)
    bar._to_check.setChecked(True)

    criteria = recorder.last
    assert criteria is not None
    assert criteria.captured_to == datetime(2024, 6, 30, 12, 0, 0)
    assert criteria.captured_from is None


def test_from_and_to_emit_both_bounds(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    bar._from_check.setChecked(True)
    bar._to_check.setChecked(True)
    _set(bar._from_edit, 2023, 1, 1)
    _set(bar._to_edit, 2023, 12, 31)

    criteria = recorder.last
    assert criteria.captured_from == datetime(2023, 1, 1, 12, 0, 0)
    assert criteria.captured_to == datetime(2023, 12, 31, 12, 0, 0)


def test_from_after_to_is_passed_through_verbatim(qtbot) -> None:
    """from > to is NOT clamped or rejected — it emits as-is and the range
    semantics of the repository match nothing (honest empty result)."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    bar._from_check.setChecked(True)
    bar._to_check.setChecked(True)
    _set(bar._from_edit, 2024, 6, 30)
    _set(bar._to_edit, 2023, 1, 1)

    criteria = recorder.last
    assert criteria.captured_from == datetime(2024, 6, 30, 12, 0, 0)
    assert criteria.captured_to == datetime(2023, 1, 1, 12, 0, 0)
    assert criteria.captured_from > criteria.captured_to


def test_date_axis_combines_with_status_axis(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    bar._status_combo.setCurrentIndex(1)  # Pending
    bar._from_check.setChecked(True)
    _set(bar._from_edit, 2023, 5, 1)

    criteria = recorder.last
    assert criteria.match_status is MatchStatus.PENDING
    assert criteria.captured_from == datetime(2023, 5, 1, 12, 0, 0)
    assert criteria.captured_to is None


def test_date_edits_disabled_until_gated(qtbot) -> None:
    """The edit widgets stay disabled while their gate is unchecked."""
    bar = FilterBar()
    qtbot.addWidget(bar)

    assert not bar._from_edit.isEnabled()
    assert not bar._to_edit.isEnabled()
    bar._from_check.setChecked(True)
    assert bar._from_edit.isEnabled()
    assert not bar._to_edit.isEnabled()


def test_clear_resets_every_axis_to_unset(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    bar._status_combo.setCurrentIndex(1)
    bar._from_check.setChecked(True)
    bar._to_check.setChecked(True)
    _set(bar._from_edit, 2023, 1, 1)
    bar.clear()

    assert recorder.last is None
    assert bar._status_combo.currentIndex() == 0
    assert not bar._from_check.isChecked() and not bar._to_check.isChecked()
    assert not bar._from_edit.isEnabled() and not bar._to_edit.isEnabled()


def test_changing_date_value_while_gated_reemits(qtbot) -> None:
    """Editing a gated-in date re-emits with the updated value (live filter)."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    bar._from_check.setChecked(True)
    _set(bar._from_edit, 2023, 5, 1)
    _set(bar._from_edit, 2023, 6, 1)

    assert recorder.last.captured_from == datetime(2023, 6, 1, 12, 0, 0)
