"""Filter bar widget for B2 搜索/筛选.

落 B2 裁决：筛选栏归 Presentation 层，发 ``criteria_changed`` 信号（持
PhotoSearchCriteria 或 None）由 PhotoListController 接收调 SearchPhotosService。
控件含人员下拉 + 状态下拉 + 日期区间（from/to）+ 清除按钮。

状态下拉走 MatchStatus 三值 + "全部"占位。日期区间用 QDateTimeEdit 双控件，
各自由 "From"/"To" 复选框门控（Phase 9 FEAT-P9-1）：未勾选 = 该轴不设约束
（QDateTimeEdit 恒有值，必须显式表达"未设置"），勾选后取控件当前值。人员轴
经 ``set_persons`` 供给（FEAT-P9-2，数据来自 Application 层 ListPersonsService）。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from PySide6.QtCore import QDateTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from photo_archiver.domain import MatchStatus, Person, PhotoSearchCriteria


class FilterBar(QWidget):
    """Horizontal filter bar emitting criteria changes for the photo list.

    The bar is passive — it only emits ``criteria_changed``; the controller
    decides whether to call ``SearchPhotosService`` synchronously (fast repo
    query per B2-a decision) or debounce. Empty criteria (all axes unset) is
    emitted as ``None`` so the controller falls back to ``list_all``.

    Date axes are gated by their "From"/"To" checkboxes: an unchecked box
    means the axis carries no constraint, regardless of the edit's value
    (QDateTimeEdit always holds a datetime, so the gate is the explicit
    "unset" representation). ``from > to`` is passed through verbatim — the
    repository range semantics simply match nothing (an honest empty result).
    """

    criteria_changed = Signal(object)  # PhotoSearchCriteria | None

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the filter bar with person/status combos + gated date range."""
        super().__init__(parent)
        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        """Lay out the filter controls horizontally."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        # Person axis — populated via set_persons(); "All persons" (userData
        # None) is the no-constraint entry.
        layout.addWidget(QLabel("Person:"))
        self._person_combo = QComboBox(self)
        self._person_combo.addItem("All persons", None)
        self._person_combo.setToolTip("Filter photos by matched person.")
        layout.addWidget(self._person_combo)

        # Status axis — MatchStatus three values + "All" placeholder.
        layout.addWidget(QLabel("Status:"))
        self._status_combo = QComboBox(self)
        self._status_combo.addItem("All", None)  # userData None → no constraint
        self._status_combo.addItem("Pending", "pending")
        self._status_combo.addItem("Approved", "approved")
        self._status_combo.addItem("Rejected", "rejected")
        layout.addWidget(self._status_combo)

        # Date range axis — each edit gated by a checkbox (FEAT-P9-1): an
        # unchecked box = axis unset (no constraint), checked = use the edit's
        # current value. ``from > to`` is allowed and matches nothing.
        self._from_check = QCheckBox("From", self)
        layout.addWidget(self._from_check)
        self._from_edit = QDateTimeEdit(self)
        self._from_edit.setCalendarPopup(True)
        self._from_edit.setEnabled(False)
        self._from_edit.setToolTip("Match photos captured on or after this date.")
        self._from_edit.setDateTime(QDateTime.currentDateTime().addYears(-1))
        layout.addWidget(self._from_edit)

        self._to_check = QCheckBox("To", self)
        layout.addWidget(self._to_check)
        self._to_edit = QDateTimeEdit(self)
        self._to_edit.setCalendarPopup(True)
        self._to_edit.setEnabled(False)
        self._to_edit.setToolTip("Match photos captured on or before this date.")
        self._to_edit.setDateTime(QDateTime.currentDateTime())
        layout.addStretch(1)

        self._clear_button = QPushButton("Clear", self)
        layout.addWidget(self._clear_button)

    def _wire_signals(self) -> None:
        """Connect control changes to emit criteria_changed."""
        self._person_combo.currentIndexChanged.connect(self._emit_criteria)
        self._status_combo.currentIndexChanged.connect(self._emit_criteria)
        self._from_check.toggled.connect(self._on_from_gate_toggled)
        self._to_check.toggled.connect(self._on_to_gate_toggled)
        self._from_edit.dateTimeChanged.connect(self._emit_criteria)
        self._to_edit.dateTimeChanged.connect(self._emit_criteria)
        self._clear_button.clicked.connect(self.clear)

    def _on_from_gate_toggled(self, checked: bool) -> None:
        """Gate the From edit on its checkbox and re-emit criteria."""
        self._from_edit.setEnabled(checked)
        self._emit_criteria()

    def _on_to_gate_toggled(self, checked: bool) -> None:
        """Gate the To edit on its checkbox and re-emit criteria."""
        self._to_edit.setEnabled(checked)
        self._emit_criteria()

    def set_persons(self, persons: Sequence[Person]) -> None:
        """Populate the person combo from the Application layer (FEAT-P9-2).

        Repopulation blocks the combo's signals so loading never emits
        spurious criteria; a single ``_emit_criteria`` runs afterwards. The
        previously selected person is preserved when still present, otherwise
        the selection resets to "All persons".

        The combo's userData carries the person id in **string** form:
        QVariant compares wrapped Python objects by identity, so findData /
        currentData round-trips would silently miss equal-valued but distinct
        UUID instances. ``_emit_criteria`` converts back to UUID.
        """
        selected_id = self._person_combo.currentData()
        self._person_combo.blockSignals(True)
        try:
            self._person_combo.clear()
            self._person_combo.addItem("All persons", None)
            for person in persons:
                if person.id is not None:
                    self._person_combo.addItem(person.name, str(person.id))
        finally:
            self._person_combo.blockSignals(False)
        restore_index = self._person_combo.findData(selected_id)
        self._person_combo.setCurrentIndex(restore_index if restore_index >= 0 else 0)
        self._emit_criteria()

    def _emit_criteria(self) -> None:
        """Build PhotoSearchCriteria from current control state and emit.

        Empty criteria (all axes unset / "All" placeholders) is emitted as
        ``None`` so the controller falls back to ``list_all`` rather than
        forcing a trivially-true search.
        """
        # Person ids travel the combo as strings (see set_persons); convert
        # back to the UUID the criteria VO expects.
        person_data = self._person_combo.currentData()
        person_id = UUID(person_data) if person_data else None
        status_value = self._status_combo.currentData()
        # A gated-off date edit carries no constraint even though QDateTimeEdit
        # always holds a value (the checkbox is the explicit "unset" state).
        captured_from: datetime | None = (
            self._from_edit.dateTime().toPython()  # type: ignore[assignment]  # Qt opaquely returns object
            if self._from_check.isChecked()
            else None
        )
        captured_to: datetime | None = (
            self._to_edit.dateTime().toPython()  # type: ignore[assignment]  # Qt opaquely returns object
            if self._to_check.isChecked()
            else None
        )
        if (
            person_id is None
            and status_value is None
            and captured_from is None
            and captured_to is None
        ):
            self.criteria_changed.emit(None)
            return
        match_status = None
        if status_value is not None:
            match_status = MatchStatus(status_value)
        criteria = PhotoSearchCriteria(
            person_id=person_id,
            match_status=match_status,
            captured_from=captured_from,
            captured_to=captured_to,
        )
        self.criteria_changed.emit(criteria)

    def clear(self) -> None:
        """Reset all axes to unset and emit criteria via the single _emit_criteria path.

        与 _emit_criteria 逻辑单源：未勾选的日期轴在 _emit_criteria 判 None 分支
        返 None，故 clear() 复位控件后调 _emit_criteria() 即可——避免 emit None
        与 _emit_criteria 的判 None 逻辑二处维护。
        """
        self._person_combo.setCurrentIndex(0)
        self._status_combo.setCurrentIndex(0)
        self._from_check.setChecked(False)
        self._to_check.setChecked(False)
        self._from_edit.setDateTime(QDateTime.currentDateTime().addYears(-1))
        self._to_edit.setDateTime(QDateTime.currentDateTime())
        self._emit_criteria()
