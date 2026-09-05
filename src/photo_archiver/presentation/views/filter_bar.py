"""Filter bar widget for B2 搜索/筛选.

落 B2 裁决：筛选栏归 Presentation 层，发 ``criteria_changed`` 信号（持
PhotoSearchCriteria 或 None）由 PhotoListController 接收调 SearchPhotosService。
控件含人员下拉 + 状态下拉 + 日期区间（from/to）+ 清除按钮。

状态下拉走 MatchStatus 三值，人员轴经 ``set_persons`` 供给（FEAT-P9-2）。
两轴均为占位语义：下拉列表只含真实选项，未选中（currentIndex == -1）时
闭合框内灰色占位（"全部" / "全部人员"）= 该轴不设约束。日期区间用
QDateTimeEdit 双控件，各自由 "从"/"至" 复选框门控（Phase 9 FEAT-P9-1）：
未勾选 = 该轴不设约束（QDateTimeEdit 恒有值，必须显式表达"未设置"），
勾选后取控件当前值。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from PySide6.QtCore import QDateTime, Qt, Signal, QStringListModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from photo_archiver.domain import MatchStatus, Person, PhotoSearchCriteria
from photo_archiver.presentation.person_matcher import rank_person_names
from photo_archiver.presentation.ui_text import (
    FILTER_ALL_PERSONS,
    FILTER_CLEAR_BUTTON,
    FILTER_FROM_CHECK,
    FILTER_FROM_TOOLTIP,
    FILTER_PERSON_LABEL,
    FILTER_PERSON_TOOLTIP,
    FILTER_STATUS_ALL,
    FILTER_STATUS_APPROVED,
    FILTER_STATUS_LABEL,
    FILTER_STATUS_PENDING,
    FILTER_STATUS_PLACEHOLDER_TOOLTIP,
    FILTER_STATUS_REJECTED,
    FILTER_TO_CHECK,
    FILTER_TO_TOOLTIP,
)


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

        # Person axis — populated via set_persons(). 占位语义：下拉列表只含
        # 真实人员；未选中（currentIndex == -1）时闭合框内显示灰色占位
        # "全部人员"= 该轴不设约束。可编辑 + 智能搜索补全（2026-09-05）：
        # 输入即按 person_matcher 排名过滤（全等 → 前缀 → 连续包含 → 子序列），
        # 从补全中选中才落到筛选值——纯输入不改变 criteria。
        layout.addWidget(QLabel(FILTER_PERSON_LABEL))
        self._person_combo = QComboBox(self)
        self._person_combo.setEditable(True)
        self._person_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._person_combo.setPlaceholderText(FILTER_ALL_PERSONS)
        self._person_combo.setToolTip(FILTER_PERSON_TOOLTIP)
        self._person_combo.setCurrentIndex(-1)
        layout.addWidget(self._person_combo)
        self._person_names: list[str] = []
        self._person_ids_by_name: dict[str, str] = {}
        self._person_completer = QCompleter(self._person_combo)
        self._person_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._person_completer.setCompletionMode(
            QCompleter.CompletionMode.UnfilteredPopupCompletion
        )
        self._person_completer_model = QStringListModel(self._person_completer)
        self._person_completer.setModel(self._person_completer_model)
        self._person_combo.setCompleter(self._person_completer)
        self._person_completer.activated.connect(self._on_person_completion_activated)
        self._person_combo.editTextChanged.connect(self._on_person_search_text_changed)

        # Status axis — MatchStatus 三值为仅有的可选项；未选中（-1）=
        # 不设约束，闭合框内灰色占位"全部"。
        layout.addWidget(QLabel(FILTER_STATUS_LABEL))
        self._status_combo = QComboBox(self)
        self._status_combo.setPlaceholderText(FILTER_STATUS_ALL)
        self._status_combo.setToolTip(FILTER_STATUS_PLACEHOLDER_TOOLTIP)
        self._status_combo.addItem(FILTER_STATUS_PENDING, "pending")
        self._status_combo.addItem(FILTER_STATUS_APPROVED, "approved")
        self._status_combo.addItem(FILTER_STATUS_REJECTED, "rejected")
        self._status_combo.setCurrentIndex(-1)
        layout.addWidget(self._status_combo)

        # Date range axis — each edit gated by a checkbox (FEAT-P9-1): an
        # unchecked box = axis unset (no constraint), checked = use the edit's
        # current value. ``from > to`` is allowed and matches nothing.
        self._from_check = QCheckBox(FILTER_FROM_CHECK, self)
        layout.addWidget(self._from_check)
        self._from_edit = QDateTimeEdit(self)
        self._from_edit.setCalendarPopup(True)
        self._from_edit.setEnabled(False)
        self._from_edit.setToolTip(FILTER_FROM_TOOLTIP)
        self._from_edit.setDateTime(QDateTime.currentDateTime().addYears(-1))
        layout.addWidget(self._from_edit)

        self._to_check = QCheckBox(FILTER_TO_CHECK, self)
        layout.addWidget(self._to_check)
        self._to_edit = QDateTimeEdit(self)
        self._to_edit.setCalendarPopup(True)
        self._to_edit.setEnabled(False)
        self._to_edit.setToolTip(FILTER_TO_TOOLTIP)
        self._to_edit.setDateTime(QDateTime.currentDateTime())
        # P0-3: the To edit MUST join the layout — without addWidget it sat as
        # an unmanaged child at (0,0,100,30), overlapping and blocking the
        # Person axis (found via manual desktop smoke; Phase 9 FEAT-P9-1 gap).
        layout.addWidget(self._to_edit)

        layout.addStretch(1)

        self._clear_button = QPushButton(FILTER_CLEAR_BUTTON, self)
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

    def _on_person_search_text_changed(self, text: str) -> None:
        """Rebuild the completion list with smart-ranked matches for ``text``.

        输入过程只影响补全列表——criteria 仍仅由"选中某个人员"（下拉选择或
        补全激活，二者都会落到 currentIndex）驱动，见 _emit_criteria。
        """
        self._person_completer_model.setStringList(
            rank_person_names(text, self._person_names)
        )

    def _on_person_completion_activated(self, name: str) -> None:
        """Map a picked completion back to the person entry and select it.

        同名人员（不同部门）在补全中以名称呈现——激活时落到该名称的首个
        id，与下拉直接点选的既有限制一致。
        """
        person_id = self._person_ids_by_name.get(name)
        if person_id is None:
            return
        index = self._person_combo.findData(person_id)
        if index >= 0:
            self._person_combo.setCurrentIndex(index)

    def set_persons(self, persons: Sequence[Person]) -> None:
        """Populate the person combo from the Application layer (FEAT-P9-2).

        Repopulation blocks the combo's signals so loading never emits
        spurious criteria; a single ``_emit_criteria`` runs afterwards. The
        previously selected person is preserved when still present, otherwise
        the selection resets to the unselected placeholder state (index -1,
        displaying the "全部人员" hint).

        The combo's userData carries the person id in **string** form:
        QVariant compares wrapped Python objects by identity, so findData /
        currentData round-trips would silently miss equal-valued but distinct
        UUID instances. ``_emit_criteria`` converts back to UUID.
        """
        selected_id = self._person_combo.currentData()
        self._person_combo.blockSignals(True)
        try:
            self._person_combo.clear()
            for person in persons:
                if person.id is not None:
                    self._person_combo.addItem(person.name, str(person.id))
        finally:
            self._person_combo.blockSignals(False)
        # 搜索补全的数据源与名称→id 映射同步重建（同名人员取首个 id，
        # 与补全激活的既有限制一致）。
        self._person_names = [p.name for p in persons if p.id is not None]
        self._person_ids_by_name = {}
        for person in persons:
            if person.id is not None:
                self._person_ids_by_name.setdefault(person.name, str(person.id))
        self._person_completer_model.setStringList(self._person_names)
        restore_index = self._person_combo.findData(selected_id)
        # 找不回原选择（含此前本就未选中）→ 回落未选中占位态（-1）。
        self._person_combo.setCurrentIndex(restore_index)
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
        self._person_combo.setCurrentIndex(-1)
        # combo 已 setEditable(True)，lineEdit() 运行时恒非空——守卫仅满足可空注解。
        line_edit = self._person_combo.lineEdit()
        if line_edit is not None:
            line_edit.clear()
        self._status_combo.setCurrentIndex(-1)
        self._from_check.setChecked(False)
        self._to_check.setChecked(False)
        self._from_edit.setDateTime(QDateTime.currentDateTime().addYears(-1))
        self._to_edit.setDateTime(QDateTime.currentDateTime())
        self._emit_criteria()
