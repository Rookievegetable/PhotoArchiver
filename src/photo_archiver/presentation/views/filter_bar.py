"""Filter panel widget for B2 搜索/筛选（照片库右侧筛选条件面板）.

落 B2 裁决：筛选栏归 Presentation 层，发 ``criteria_changed`` 信号（持
``tuple[PhotoSearchCriteria, ...]`` 或 ``None``）由 PhotoListController 接收调
SearchPhotosService。控件含人员下拉 + 状态**复选框组（多选＋计数）** +
时间模式 + 清除按钮。

状态轴 2026-10-30 参考图基线裁决（Owner：DEC-06=A 按图推翻）：照片库右侧
筛选面板的状态轴改为**复选框多选**，每项带实时计数（``set_status_counts``
由窗口回填）。多选语义 = 各选中状态查询结果的并集——本面板发
``tuple[PhotoSearchCriteria, ...]``（每个选中状态一条 criteria，人员/时间轴
逐条 AND 组合）；未选中任何状态但人员/时间轴有约束时发单条 1-tuple；
全空发 ``None``（窗口回退 ``list_all``）。单选时窗口兼容既有
``_current_criteria`` 单条语义（导出范围/刷新复用）。

人员轴经 ``set_persons`` 供给（FEAT-P9-2）。两轴均为占位语义：下拉列表只
含真实选项，未选中（currentIndex == -1）时闭合框内灰色占位（"全部人员"）
= 该轴不设约束。

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
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateTimeEdit,
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
from photo_archiver.presentation.person_name_ranker import rank_person_names
from photo_archiver.presentation.ui_text import (
    FILTER_ALL_PERSONS,
    FILTER_CLEAR_BUTTON,
    FILTER_DATE_FORMAT,
    FILTER_DATE_RANGE_INVALID,
    FILTER_FROM_TOOLTIP,
    FILTER_PANEL_STATUS_TITLE,
    FILTER_PANEL_TIME_TITLE,
    FILTER_PANEL_TITLE,
    FILTER_PERSON_LABEL,
    FILTER_PERSON_TOOLTIP,
    FILTER_RESULT_COUNT,
    FILTER_STATUS_APPROVED,
    FILTER_STATUS_COUNT_FORMAT,
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
    FILTER_TO_TOOLTIP,
)
from photo_archiver.presentation.visual_style import style_section_title

# 状态复选框顺序（即并集查询顺序；key = criteria 状态值契约值）。
_STATUS_OPTIONS: tuple[tuple[str, str], ...] = (
    ("pending", FILTER_STATUS_PENDING),
    ("approved", FILTER_STATUS_APPROVED),
    ("rejected", FILTER_STATUS_REJECTED),
    ("unmatched", FILTER_STATUS_UNMATCHED),
)


class FilterBar(QWidget):
    """Right-hand filter panel emitting criteria tuples for the photo list.

    The panel is passive — it only emits ``criteria_changed``; the controller
    decides whether to call ``SearchPhotosService`` synchronously (fast repo
    query per B2-a decision) or debounce. Empty criteria (all axes unset) is
    emitted as ``None`` so the controller falls back to ``list_all``. 多选状
    态轴按选中项发 1..N 条 criteria 的元组（每条 = 共享人员/时间轴 × 单一
    状态），窗口做并集合并。

    Date semantics (Batch 4): the time-mode combo defaults to "全部时间"
    (no constraint, edits hidden). Picking "自定义时间" reveals both edits
    and contributes their values. ``from > to`` blocks the emission — the
    previous valid criteria stays in force and an inline hint explains the
    fix, so an invalid range never silently renders an empty result.
    """

    criteria_changed = Signal(object)  # tuple[PhotoSearchCriteria, ...] | None

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the filter panel: person combo, status checkboxes, time axis."""
        super().__init__(parent)
        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        """Lay out the vertical filter panel: title, axes, summary rows."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 2)
        outer.setSpacing(6)

        # 参考图 M8：面板标题「筛选条件」（参考图语义；SectionTitle 挂点）。
        self._panel_title = QLabel(FILTER_PANEL_TITLE, self)
        style_section_title(self._panel_title)
        outer.addWidget(self._panel_title)

        # Person axis — populated via set_persons(). 占位语义：下拉列表只含
        # 真实人员；未选中（currentIndex == -1）时闭合框内显示灰色占位
        # "全部人员"= 该轴不设约束。可编辑 + 智能搜索补全（2026-09-05）。
        outer.addWidget(QLabel(FILTER_PERSON_LABEL, self))
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
        outer.addWidget(self._person_combo)
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

        # Status axis（DEC-06 按图推翻）：复选框多选＋实时计数。未勾选任何
        # 状态 = 该轴不设约束（不筛状态）；勾选 N 项 = N 条 criteria 并集。
        outer.addWidget(QLabel(FILTER_PANEL_STATUS_TITLE, self))
        self._status_checks: dict[str, QCheckBox] = {}
        self._status_labels: dict[str, str] = {}
        self._status_counts: dict[str, int] = {}
        for key, label in _STATUS_OPTIONS:
            check = QCheckBox(label, self)
            check.setToolTip(FILTER_STATUS_PLACEHOLDER_TOOLTIP)
            check.setChecked(True)  # 参考图口径：默认全选（= 不筛状态）
            outer.addWidget(check)
            self._status_checks[key] = check
            self._status_labels[key] = label

        # Time mode axis (Batch 4): "全部时间" is the default — the from/to
        # edits only appear (and only constrain) after picking "自定义时间".
        outer.addWidget(QLabel(FILTER_PANEL_TIME_TITLE, self))
        self._time_mode_combo = QComboBox(self)
        self._time_mode_combo.addItem(FILTER_TIME_ALL)
        self._time_mode_combo.addItem(FILTER_TIME_CUSTOM)
        outer.addWidget(self._time_mode_combo)

        self._from_edit = QDateTimeEdit(self)
        self._from_edit.setCalendarPopup(True)
        self._from_edit.setToolTip(FILTER_FROM_TOOLTIP)
        self._from_edit.setDateTime(QDateTime.currentDateTime().addYears(-1))
        self._from_edit.setVisible(False)
        outer.addWidget(self._from_edit)

        self._to_edit = QDateTimeEdit(self)
        self._to_edit.setCalendarPopup(True)
        self._to_edit.setToolTip(FILTER_TO_TOOLTIP)
        self._to_edit.setDateTime(QDateTime.currentDateTime())
        self._to_edit.setVisible(False)
        # P0-3 heritage: both edits MUST join the layout (unmanaged children
        # overlapped the Person axis in the Phase 9 gap — never regress).
        outer.addWidget(self._to_edit)

        outer.addStretch(1)

        self._clear_button = QPushButton(FILTER_CLEAR_BUTTON, self)
        outer.addWidget(self._clear_button, 0, Qt.AlignmentFlag.AlignLeft)

        # Summary row (Batch 4): effective conditions + live result count.
        self._summary_label = QLabel(FILTER_SUMMARY_NONE, self)
        self._summary_label.setWordWrap(True)
        outer.addWidget(self._summary_label)
        self._count_label = QLabel("", self)
        outer.addWidget(self._count_label)
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
        for check in self._status_checks.values():
            check.toggled.connect(self._emit_criteria)
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

        The panel cannot know result sizes (it only emits criteria); the window
        calls this after each query so the count never lies about the list.
        """
        self._last_result_count = count
        self._count_label.setText(FILTER_RESULT_COUNT.format(count=count))

    def set_status_counts(self, counts: dict[str, int] | None) -> None:
        """Backfill per-status counts beside each checkbox（参考图 M8 口径）.

        ``counts`` 以契约值（pending/approved/rejected/unmatched）为键；缺键
        状态保持现文案。``None`` = 清除计数显示（仅状态文案）。
        """
        self._status_counts = dict(counts) if counts is not None else {}
        for key, check in self._status_checks.items():
            count = self._status_counts.get(key)
            label = self._status_labels[key]
            check.setText(
                FILTER_STATUS_COUNT_FORMAT.format(label=label, count=count)
                if count is not None else label
            )

    @property
    def result_count(self) -> int:
        """Return the last backfilled query size (``0`` before any query)."""
        return self._last_result_count

    @property
    def summary_text(self) -> str:
        """Return the effective-conditions summary (for scope-honest exports)."""
        return self._summary_label.text()

    def _checked_statuses(self) -> list[str]:
        """Return the checked status keys in the fixed option order."""
        return [key for key, _label in _STATUS_OPTIONS if self._status_checks[key].isChecked()]

    def _emit_criteria(self) -> None:
        """Build criteria tuples from current control state and emit.

        多选语义（DEC-06 按图推翻）：每个勾选状态发一条 criteria（共享人员/
        时间轴）；全空发 ``None``（窗口回退 list_all）。``from > to`` 阻止发
        射——保持上一有效筛选并显示内联提示，绝不静默渲染空结果。
        """
        # Person ids travel the combo as strings (see set_persons); convert
        # back to the UUID the criteria VO expects.
        person_data = self._person_combo.currentData()
        person_id = UUID(person_data) if person_data else None
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
        statuses = self._checked_statuses()
        if len(statuses) == len(_STATUS_OPTIONS):
            # 全选 = 状态轴不设约束（参考图默认勾选全部状态；等价 list_all，
            # 避免四次同义查询）。
            statuses = []
        if person_id is None and not statuses and captured_from is None and captured_to is None:
            self.criteria_changed.emit(None)
            self._update_summary(None, (), captured_from, captured_to)
            return
        criteria_list: list[PhotoSearchCriteria] = []
        if statuses:
            for key in statuses:
                # "unmatched" 是哨兵（完全无识别结果），不是 MatchStatus 枚举值。
                match_status = UNMATCHED if key == "unmatched" else MatchStatus(key)
                criteria_list.append(PhotoSearchCriteria(
                    person_id=person_id,
                    match_status=match_status,  # type: ignore[arg-type]
                    captured_from=captured_from,
                    captured_to=captured_to,
                ))
        else:
            criteria_list.append(PhotoSearchCriteria(
                person_id=person_id,
                match_status=None,
                captured_from=captured_from,
                captured_to=captured_to,
            ))
        person_name = (
            self._person_combo.currentText()
            if self._person_combo.currentIndex() >= 0
            else None
        )
        self.criteria_changed.emit(tuple(criteria_list))
        self._update_summary(person_name, tuple(statuses), captured_from, captured_to)

    def _update_summary(
        self,
        person_name: str | None,
        statuses: tuple[str, ...],
        captured_from: datetime | None,
        captured_to: datetime | None,
    ) -> None:
        """Render the effective-conditions text under the control row."""
        parts: list[str] = []
        if person_name:
            parts.append(FILTER_SUMMARY_PERSON.format(name=person_name))
        if statuses:
            status_names = "、".join(self._status_labels[key] for key in statuses)
            parts.append(FILTER_SUMMARY_STATUS.format(name=status_names))
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
        for check in self._status_checks.values():
            check.setChecked(False)
        self._time_mode_combo.setCurrentIndex(0)  # 回"全部时间"（隐藏起止编辑）
        self._from_edit.setDateTime(QDateTime.currentDateTime().addYears(-1))
        self._to_edit.setDateTime(QDateTime.currentDateTime())
        self._emit_criteria()
