"""Filter bar widget for B2 搜索/筛选.

落 B2 裁决：筛选栏归 Presentation 层，发 ``criteria_changed`` 信号（持
PhotoSearchCriteria 或 None）由 PhotoListController 接收调 SearchPhotosService。
控件含人员下拉 + 状态下拉 + 日期区间（from/to）+ 清除按钮。

人员下拉首版留空（无 Application 端"list persons"用例暴露给 Presentation——
B5 PluginContext 落地后或新裁决再补；当前人员维度靠 CLI/后续轮补）。状态下拉
走 MatchStatus 三值 + "全部"占位。日期区间用 QDateTimeEdit 双控件。
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from photo_archiver.domain import MatchStatus, PhotoSearchCriteria


class FilterBar(QWidget):
    """Horizontal filter bar emitting criteria changes for the photo list.

    The bar is passive — it only emits ``criteria_changed``; the controller
    decides whether to call ``SearchPhotosService`` synchronously (fast repo
    query per B2-a decision) or debounce. Empty criteria (all axes unset) is
    emitted as ``None`` so the controller falls back to ``list_all``.
    """

    criteria_changed = Signal(object)  # PhotoSearchCriteria | None

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the filter bar with status combo + date range + clear button.

        Person combo is created but left empty in this version — populating it
        requires an Application "list persons" use case not yet exposed to
        Presentation. A follow-up round (post-B5 PluginContext or new裁决)
        will wire it; until then it stays disabled to avoid misleading users.
        """
        super().__init__(parent)
        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        """Lay out the filter controls horizontally."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        # Person axis — disabled placeholder (see __init__ docstring).
        layout.addWidget(QLabel("Person:"))
        self._person_combo = QComboBox(self)
        self._person_combo.setEnabled(False)
        self._person_combo.setToolTip(
            "Person filter is reserved for a follow-up round; disabled in this version.",
        )
        layout.addWidget(self._person_combo)

        # Status axis — MatchStatus three values + "All" placeholder.
        layout.addWidget(QLabel("Status:"))
        self._status_combo = QComboBox(self)
        self._status_combo.addItem("All", None)  # userData None → no constraint
        self._status_combo.addItem("Pending", "pending")
        self._status_combo.addItem("Approved", "approved")
        self._status_combo.addItem("Rejected", "rejected")
        layout.addWidget(self._status_combo)

        # Date range axis — disabled placeholder (首版仅 status 轴生效，
        # 见 __init__ docstring � erbar 项裁决；启用需可勾选开关 + 默认值语义，留后续轮)。
        layout.addWidget(QLabel("From:"))
        self._from_edit = QDateTimeEdit(self)
        self._from_edit.setCalendarPopup(True)
        self._from_edit.setEnabled(False)
        self._from_edit.setToolTip(
            "Date range filter is reserved for a follow-up round; disabled in this version.",
        )
        self._from_edit.setDateTime(QDateTime.currentDateTime().addYears(-1))
        layout.addWidget(self._from_edit)

        layout.addWidget(QLabel("To:"))
        self._to_edit = QDateTimeEdit(self)
        self._to_edit.setCalendarPopup(True)
        self._to_edit.setEnabled(False)
        self._to_edit.setToolTip(
            "Date range filter is reserved for a follow-up round; disabled in this version.",
        )
        self._to_edit.setDateTime(QDateTime.currentDateTime())
        layout.addStretch(1)

        self._clear_button = QPushButton("Clear", self)
        layout.addWidget(self._clear_button)

    def _wire_signals(self) -> None:
        """Connect control changes to emit criteria_changed."""
        self._status_combo.currentIndexChanged.connect(self._emit_criteria)
        self._from_edit.dateTimeChanged.connect(self._emit_criteria)
        self._to_edit.dateTimeChanged.connect(self._emit_criteria)
        self._clear_button.clicked.connect(self.clear)

    def _emit_criteria(self) -> None:
        """Build PhotoSearchCriteria from current control state and emit.

        Empty criteria (all axes unset / "All" status) is emitted as ``None``
        so the controller falls back to ``list_all`` rather than forcing a
        trivially-true search.
        """
        status_value = self._status_combo.currentData()
        # Person combo disabled → always None; captured here for future wiring.
        person_id = None
        # toPython() returns object; cast to datetime | None for PhotoSearchCriteria typing.
        captured_from: datetime | None = (
            self._from_edit.dateTime().toPython()  # type: ignore[assignment]  # Qt opaquely returns object
            if self._from_edit.isEnabled()
            else None
        )
        captured_to: datetime | None = (
            self._to_edit.dateTime().toPython()  # type: ignore[assignment]  # Qt opaquely returns object
            if self._to_edit.isEnabled()
            else None
        )
        if status_value is None and person_id is None and captured_from is None and captured_to is None:
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

        与 _emit_criteria 逻辑单源：禁用态下 _emit_criteria 的 isEnabled() 判会
        返 None 分支，故 clear() 调 _emit_criteria() 即可——避免 emit None 与
        _emit_criteria 的判 None 逻辑二处维护。
        """
        self._status_combo.setCurrentIndex(0)
        self._from_edit.setDateTime(QDateTime.currentDateTime().addYears(-1))
        self._to_edit.setDateTime(QDateTime.currentDateTime())
        self._emit_criteria()
