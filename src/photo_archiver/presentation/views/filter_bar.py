"""Filter bar widget for B2 搜索/筛选.

落 B2 裁决：筛选栏归 Presentation 层，发 ``criteria_changed`` 信号（持
PhotoSearchCriteria 或 None）由 PhotoListController 接收调 SearchPhotosService。
控件含人员下拉 + 状态下拉 + 时间模式 + 清除按钮。

状态下拉走 MatchStatus 三值，人员轴经 ``set_persons`` 供给（FEAT-P9-2）。
两轴均为占位语义：下拉列表只含真实选项，未选中（currentIndex == -1）时
闭合框内灰色占位（"全部" / "全部人员"）= 该轴不设约束。

时间轴（Batch 4）：默认"全部时间"（无约束，起止控件隐藏）；仅当选择
"自定义时间"才展开起止 QDateTimeEdit。开始时间晚于结束时间时**阻止发
criteria**（保持上一个有效筛选生效）并显示内联修正提示——绝不静默渲染
空结果。摘要行显示已生效条件与结果计数（计数经 ``set_result_count`` 由
窗口在查询后回填）。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from PySide6.QtCore import QDateTime, Qt, Signal, QStringListModel
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.domain import (
    MatchStatus,
    Person,
    PhotoSearchCriteria,
    UNMATCHED,
)
from photo_archiver.presentation.person_matcher import rank_person_names
from photo_archiver.presentation.ui_text import (
    FILTER_ALL_PERSONS,
    FILTER_CLEAR_BUTTON,
    FILTER_DATE_FORMAT,
    FILTER_DATE_RANGE_INVALID,
    FILTER_FROM_TOOLTIP,
    FILTER_PERSON_LABEL,
    FILTER_PERSON_TOOLTIP,
    FILTER_RESULT_COUNT,
    FILTER_STATUS_ALL,
    FILTER_STATUS_APPROVED,
    FILTER_STATUS_LABEL,
    FILTER_STATUS_PENDING,
    FILTER_STATUS_PLACEHOLDER_TOOLTIP,
    FILTER_STATUS_REJECTED,
    FILTER_STATUS_UNMATCHED,
    FILTER_SUMMARY_NONE,
    FILTER_SUMMARY_PERSON,
    FILTER_SUMMARY_SEPARATOR,
    FILTER_SUMMARY_STATUS,
    FILTER_SUMMARY_TIME_FROM,
    FILTER_SUMMARY_TIME_TO,
    FILTER_TIME_ALL,
    FILTER_TIME_CUSTOM,
    FILTER_TIME_LABEL,
    FILTER_TO_TOOLTIP,
)


class FilterBar(QWidget):
    """Horizontal filter bar emitting criteria changes for the photo list.

    The bar is passive — it only emits ``criteria_changed``; the controller
    decides whether to call ``SearchPhotosService`` synchronously (fast repo
    query per B2-a decision) or debounce. Empty criteria (all axes unset) is
    emitted as ``None`` so the controller falls back to ``list_all``.

    Date semantics (Batch 4): the time-mode combo defaults to "全部时间"
    (no constraint, edits hidden). Picking "自定义时间" reveals both edits
    and contributes their values. ``from > to`` blocks the emission — the
    previous valid criteria stays in force and an inline hint explains the
    fix, so an invalid range never silently renders an empty result.
    """

    criteria_changed = Signal(object)  # PhotoSearchCriteria | None

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the filter bar with person/status combos + time-mode axis."""
        super().__init__(parent)
        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        """Lay out the filter controls plus the summary and warning rows."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 2)
        outer.setSpacing(2)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(layout)

        # Person axis — populated via set_persons(). 占位语义：下拉列表只含
        # 真实人员；未选中（currentIndex == -1）时闭合框内显示灰色占位
        # "全部人员"= 该轴不设约束。可编辑 + 智能搜索补全（2026-09-05）：
        # 输入即按 person_matcher 排名过滤（全等 → 前缀 → 连续包含 → 子序列），
        # 从补全中选中才落到筛选值——纯输入不改变 criteria。
        layout.addWidget(QLabel(FILTER_PERSON_LABEL))
        self._person_combo = QComboBox(self)
        self._person_combo.setEditable(True)
        self._person_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        # 占位必须设在内部 lineEdit 上：Windows 样式下可编辑 QComboBox 不绘制
        # combo 级占位（2026-09-06 桌面实测），QLineEdit 占位渲染可靠。
        self._person_combo.setPlaceholderText(FILTER_ALL_PERSONS)
        # combo 已 setEditable(True)，lineEdit() 运行时恒非空——守卫仅满足可空注解。
        line_edit = self._person_combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(FILTER_ALL_PERSONS)
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
        # ADR-036 D6：哨兵项——反向选择"完全没有识别结果"的照片。
        self._status_combo.addItem(FILTER_STATUS_UNMATCHED, "unmatched")
        self._status_combo.setCurrentIndex(-1)
        layout.addWidget(self._status_combo)

        # Time mode axis (Batch 4): "全部时间" is the default — the from/to
        # edits only appear (and only constrain) after picking "自定义时间".
        layout.addWidget(QLabel(FILTER_TIME_LABEL, self))
        self._time_mode_combo = QComboBox(self)
        self._time_mode_combo.addItem(FILTER_TIME_ALL)
        self._time_mode_combo.addItem(FILTER_TIME_CUSTOM)
        layout.addWidget(self._time_mode_combo)

        self._from_edit = QDateTimeEdit(self)
        self._from_edit.setCalendarPopup(True)
        self._from_edit.setToolTip(FILTER_FROM_TOOLTIP)
        self._from_edit.setDateTime(QDateTime.currentDateTime().addYears(-1))
        self._from_edit.setVisible(False)
        layout.addWidget(self._from_edit)

        self._to_edit = QDateTimeEdit(self)
        self._to_edit.setCalendarPopup(True)
        self._to_edit.setToolTip(FILTER_TO_TOOLTIP)
        self._to_edit.setDateTime(QDateTime.currentDateTime())
        self._to_edit.setVisible(False)
        # P0-3 heritage: both edits MUST join the layout (unmanaged children
        # overlapped the Person axis in the Phase 9 gap — never regress).
        layout.addWidget(self._to_edit)

        layout.addStretch(1)

        self._clear_button = QPushButton(FILTER_CLEAR_BUTTON, self)
        layout.addWidget(self._clear_button)

        # Summary row (Batch 4): effective conditions + live result count.
        summary_row = QHBoxLayout()
        self._summary_label = QLabel(FILTER_SUMMARY_NONE, self)
        summary_row.addWidget(self._summary_label)
        summary_row.addStretch(1)
        self._count_label = QLabel("", self)
        summary_row.addWidget(self._count_label)
        outer.addLayout(summary_row)
        self._last_result_count = 0

        # Inline validation (Batch 4): from > to blocks the query — the hint
        # stays visible until corrected; never a silent empty result.
        self._date_warning_label = QLabel(FILTER_DATE_RANGE_INVALID, self)
        self._date_warning_label.setVisible(False)
        self._date_warning_label.setWordWrap(True)
        outer.addWidget(self._date_warning_label)

    def _wire_signals(self) -> None:
        """Connect control changes to emit criteria_changed."""
        self._person_combo.currentIndexChanged.connect(self._emit_criteria)
        self._status_combo.currentIndexChanged.connect(self._emit_criteria)
        self._time_mode_combo.currentIndexChanged.connect(self._on_time_mode_changed)
        self._from_edit.dateTimeChanged.connect(self._emit_criteria)
        self._to_edit.dateTimeChanged.connect(self._emit_criteria)
        self._clear_button.clicked.connect(self.clear)

    def _on_time_mode_changed(self, index: int) -> None:
        """Custom time reveals both edits; all-time hides and unsets them."""
        custom = index == 1
        self._from_edit.setVisible(custom)
        self._to_edit.setVisible(custom)
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

    def set_result_count(self, count: int) -> None:
        """Backfill the live result count shown beside the conditions summary.

        The bar cannot know result sizes (it only emits criteria); the window
        calls this after each query so the count never lies about the list.
        """
        self._last_result_count = count
        self._count_label.setText(FILTER_RESULT_COUNT.format(count=count))

    @property
    def result_count(self) -> int:
        """Return the last backfilled query size (``0`` before any query)."""
        return self._last_result_count

    @property
    def summary_text(self) -> str:
        """Return the effective-conditions summary (for scope-honest exports)."""
        return self._summary_label.text()

    def _emit_criteria(self) -> None:
        """Build PhotoSearchCriteria from current control state and emit.

        Empty criteria (all axes unset / "All" placeholders) is emitted as
        ``None`` so the controller falls back to ``list_all`` rather than
        forcing a trivially-true search. Batch 4: date values only constrain
        in the custom-time mode, and ``from > to`` blocks the emission (the
        previous valid criteria stays in force) with an inline hint — never
        a silent empty result.
        """
        # Person ids travel the combo as strings (see set_persons); convert
        # back to the UUID the criteria VO expects.
        person_data = self._person_combo.currentData()
        person_id = UUID(person_data) if person_data else None
        status_value = self._status_combo.currentData()
        custom_time = self._time_mode_combo.currentIndex() == 1
        captured_from: datetime | None = (
            self._from_edit.dateTime().toPython()  # type: ignore[assignment]  # Qt opaquely returns object
            if custom_time
            else None
        )
        captured_to: datetime | None = (
            self._to_edit.dateTime().toPython()  # type: ignore[assignment]  # Qt opaquely returns object
            if custom_time
            else None
        )
        if custom_time and captured_from and captured_to and captured_from > captured_to:
            # Invalid range: keep the previous criteria in force, show why.
            self._date_warning_label.setVisible(True)
            return
        self._date_warning_label.setVisible(False)
        if (
            person_id is None
            and status_value is None
            and captured_from is None
            and captured_to is None
        ):
            self.criteria_changed.emit(None)
            self._update_summary(None, None, None, None)
            return
        match_status = None
        if status_value is not None:
            # "unmatched" 是哨兵（完全无识别结果），不是 MatchStatus 枚举值。
            match_status = UNMATCHED if status_value == "unmatched" else MatchStatus(status_value)
        criteria = PhotoSearchCriteria(
            person_id=person_id,
            match_status=match_status,
            captured_from=captured_from,
            captured_to=captured_to,
        )
        person_name = (
            self._person_combo.currentText()
            if self._person_combo.currentIndex() >= 0
            else None
        )
        status_name = (
            self._status_combo.currentText()
            if self._status_combo.currentIndex() >= 0
            else None
        )
        self.criteria_changed.emit(criteria)
        self._update_summary(person_name, status_name, captured_from, captured_to)

    def _update_summary(
        self,
        person_name: str | None,
        status_name: str | None,
        captured_from: datetime | None,
        captured_to: datetime | None,
    ) -> None:
        """Render the effective-conditions text under the control row."""
        parts: list[str] = []
        if person_name:
            parts.append(FILTER_SUMMARY_PERSON.format(name=person_name))
        if status_name:
            parts.append(FILTER_SUMMARY_STATUS.format(name=status_name))
        if captured_from is not None:
            parts.append(FILTER_SUMMARY_TIME_FROM.format(
                date=captured_from.strftime(FILTER_DATE_FORMAT),
            ))
        if captured_to is not None:
            parts.append(FILTER_SUMMARY_TIME_TO.format(
                date=captured_to.strftime(FILTER_DATE_FORMAT),
            ))
        self._summary_label.setText(
            FILTER_SUMMARY_SEPARATOR.join(parts) if parts else FILTER_SUMMARY_NONE,
        )

    def clear(self) -> None:
        """Reset all axes to unset and emit criteria via the single _emit_criteria path.

        与 _emit_criteria 逻辑单源：全部时间模式下日期轴在 _emit_criteria 判
        None 分支返 None，故 clear() 复位控件后调 _emit_criteria() 即可。
        """
        self._person_combo.setCurrentIndex(-1)
        # combo 已 setEditable(True)，lineEdit() 运行时恒非空——守卫仅满足可空注解。
        line_edit = self._person_combo.lineEdit()
        if line_edit is not None:
            line_edit.clear()
        self._status_combo.setCurrentIndex(-1)
        self._time_mode_combo.setCurrentIndex(0)  # 回"全部时间"（隐藏起止编辑）
        self._from_edit.setDateTime(QDateTime.currentDateTime().addYears(-1))
        self._to_edit.setDateTime(QDateTime.currentDateTime())
        self._emit_criteria()
