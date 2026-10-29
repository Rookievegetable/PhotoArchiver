"""FilterBar unit tests — date-range / person / status axes (Batch 4 + M8).

Covers the gated date-range semantics, the person axis placeholder semantics,
the status checkbox multi-select axis（DEC-06 按图推翻：右侧筛选面板状态复选
框多选＋计数；``criteria_changed`` 发 ``tuple[PhotoSearchCriteria, ...]`` 或
``None``），combinations keep AND semantics per emitted criteria, and
``clear()`` returns every axis to unset.

Pure widget-level tests over the real ``FilterBar``; no repository is
involved (criteria emission is the contract under test).
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from datetime import datetime

from PySide6.QtCore import QDateTime

from photo_archiver.domain import MatchStatus
from photo_archiver.presentation import ui_text as text
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


def _check(bar: FilterBar, key: str, checked: bool = True) -> None:
    """Toggle one status checkbox（状态轴复选框 API 的测试入口）."""
    bar._status_checks[key].setChecked(checked)


def _uncheck_all(bar: FilterBar) -> None:
    for check in bar._status_checks.values():
        check.setChecked(False)


def test_default_state_is_no_constraint(qtbot) -> None:
    """默认全选状态 = 状态轴不设约束（参考图 M8 默认勾选全部）。"""
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    assert all(check.isChecked() for check in bar._status_checks.values())
    assert recorder.emissions == []  # 构造期零发射（勾选先于信号连接）
    _check(bar, "pending", False)
    _check(bar, "pending", True)  # 恢复全选 = 不筛状态（等价 list_all）
    assert recorder.last is None


def test_single_status_emits_single_criteria(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    _uncheck_all(bar)
    _check(bar, "pending")
    criteria_tuple = recorder.last
    assert isinstance(criteria_tuple, tuple) and len(criteria_tuple) == 1
    criteria = criteria_tuple[0]
    assert criteria.match_status is MatchStatus.PENDING
    assert criteria.captured_from is None and criteria.captured_to is None


def test_custom_time_mode_emits_both_bounds(qtbot) -> None:
    """Picking 自定义时间 reveals the edits; both datetimes then constrain."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    _uncheck_all(bar)  # 仅时间轴约束
    bar._time_mode_combo.setCurrentIndex(1)
    _set(bar._from_edit, 2023, 1, 1)
    _set(bar._to_edit, 2023, 12, 31)

    criteria_tuple = recorder.last
    assert isinstance(criteria_tuple, tuple) and len(criteria_tuple) == 1
    criteria = criteria_tuple[0]
    assert criteria.captured_from == datetime(2023, 1, 1, 12, 0, 0)
    assert criteria.captured_to == datetime(2023, 12, 31, 12, 0, 0)


def test_date_edits_hidden_until_custom_time(qtbot) -> None:
    """The from/to edits only appear on screen in the custom-time mode."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    bar.show()  # isVisible() 只有在窗口实际显示后才反映布局可见性

    assert not bar._from_edit.isVisible()
    assert not bar._to_edit.isVisible()
    bar._time_mode_combo.setCurrentIndex(1)
    assert bar._from_edit.isVisible() and bar._to_edit.isVisible()
    bar._time_mode_combo.setCurrentIndex(0)
    assert not bar._from_edit.isVisible() and not bar._to_edit.isVisible()


def test_from_after_to_blocks_query_and_shows_hint(qtbot) -> None:
    """from > to never emits a criteria — the previous valid one stays in
    force and the inline hint appears until corrected (Batch 4 decision:
    never a silent empty result)."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    bar.show()  # 内联提示的 isVisible() 断言需要窗口实际显示
    _uncheck_all(bar)
    recorder = _CriteriaRecorder(bar)

    bar._time_mode_combo.setCurrentIndex(1)  # valid default range emits once
    _set(bar._from_edit, 2024, 6, 30)        # still valid against "now"
    recorder.emissions.clear()

    _set(bar._to_edit, 2023, 1, 1)  # invalid: from > to

    assert bar._date_warning_label.isVisible()
    assert recorder.emissions == []  # the invalid range was never emitted

    _set(bar._to_edit, 2024, 12, 31)  # corrected
    assert not bar._date_warning_label.isVisible()
    criteria_tuple = recorder.last
    assert isinstance(criteria_tuple, tuple)
    criteria = criteria_tuple[0]
    assert criteria.captured_from == datetime(2024, 6, 30, 12, 0, 0)
    assert criteria.captured_to == datetime(2024, 12, 31, 12, 0, 0)


def test_date_axis_combines_with_status_axis(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    _uncheck_all(bar)
    _check(bar, "pending")
    bar._time_mode_combo.setCurrentIndex(1)
    recorder.emissions.clear()
    _set(bar._from_edit, 2023, 5, 1)

    criteria_tuple = recorder.last
    assert isinstance(criteria_tuple, tuple)
    criteria = criteria_tuple[0]
    assert criteria.match_status is MatchStatus.PENDING
    assert criteria.captured_from == datetime(2023, 5, 1, 12, 0, 0)


def test_multi_status_emits_one_criteria_per_checked_state(qtbot) -> None:
    """DEC-06 按图推翻：多选状态发多条 criteria（并集语义由窗口合并）。"""
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    _uncheck_all(bar)
    _check(bar, "approved")
    _check(bar, "unmatched")

    criteria_tuple = recorder.last
    assert isinstance(criteria_tuple, tuple) and len(criteria_tuple) == 2
    assert criteria_tuple[0].match_status is MatchStatus.APPROVED
    from photo_archiver.domain import UNMATCHED

    assert criteria_tuple[1].match_status == UNMATCHED
    assert not isinstance(criteria_tuple[1].match_status, MatchStatus)


def test_clear_resets_every_axis_to_unset(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    _uncheck_all(bar)
    _check(bar, "pending")
    bar._time_mode_combo.setCurrentIndex(1)
    _set(bar._from_edit, 2023, 1, 1)
    bar.clear()

    assert recorder.last is None
    assert all(not check.isChecked() for check in bar._status_checks.values())
    assert bar._time_mode_combo.currentIndex() == 0  # back to "全部时间"
    assert not bar._from_edit.isVisible() and not bar._to_edit.isVisible()


def test_changing_date_value_while_custom_reemits(qtbot) -> None:
    """Editing a custom-time date re-emits with the updated value (live)."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)
    _uncheck_all(bar)

    bar._time_mode_combo.setCurrentIndex(1)
    recorder.emissions.clear()
    _set(bar._from_edit, 2023, 5, 1)
    _set(bar._from_edit, 2023, 6, 1)

    criteria_tuple = recorder.last
    assert isinstance(criteria_tuple, tuple)
    assert criteria_tuple[0].captured_from == datetime(2023, 6, 1, 12, 0, 0)


# ── Person axis (Phase 9, FEAT-P9-2) ─────────────────────────────────────────


def _make_person(name: str):
    from photo_archiver.domain import Person

    return Person(name=name)


def test_person_axis_starts_on_placeholder_no_constraint(qtbot) -> None:
    """未选中人员轴 = 占位态：空列表、currentIndex -1、"全部人员"灰色提示。"""
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    assert bar._person_combo.count() == 0
    assert bar._person_combo.currentIndex() == -1
    assert bar._person_combo.placeholderText() == "全部人员"
    assert bar._person_combo.currentData() is None
    # Emitting through another axis must still carry person_id=None.
    _uncheck_all(bar)
    _check(bar, "pending")
    criteria_tuple = recorder.last
    assert isinstance(criteria_tuple, tuple)
    assert criteria_tuple[0].person_id is None
    assert criteria_tuple[0].match_status is MatchStatus.PENDING


def test_set_persons_populates_combo_and_selection_filters(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)
    alice = _make_person("Alice")
    bob = _make_person("Bob")

    bar.set_persons([alice, bob])

    assert bar._person_combo.count() == 2  # real entries only — no placeholder item
    assert bar._person_combo.itemText(0) == "Alice"
    # userData carries the id in string form (QVariant identity pitfall).
    from uuid import UUID

    assert UUID(str(bar._person_combo.itemData(0))) == alice.id
    bar._person_combo.setCurrentIndex(0)
    criteria_tuple = recorder.last
    assert isinstance(criteria_tuple, tuple)
    assert criteria_tuple[0].person_id == alice.id
    assert criteria_tuple[0].match_status is None  # other axes unaffected


def test_set_persons_empty_keeps_placeholder_no_constraint(qtbot) -> None:
    """Empty person catalog is honestly represented: no entries, no filter."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    bar.set_persons([])

    assert bar._person_combo.count() == 0
    assert bar._person_combo.currentIndex() == -1
    assert recorder.last is None


def test_set_persons_emits_exactly_once(qtbot) -> None:
    """Repopulation never emits spurious per-item criteria (signals blocked)."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    bar.set_persons([_make_person("Alice"), _make_person("Bob"), _make_person("Carol")])

    assert len(recorder.emissions) == 1  # one final emit, nothing per item
    assert recorder.last is None  # selection preserved as "All persons"


def test_set_persons_preserves_current_selection(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)
    alice = _make_person("Alice")
    bob = _make_person("Bob")

    bar.set_persons([alice, bob])
    bar._person_combo.setCurrentIndex(1)  # Bob
    recorder.emissions.clear()

    bar.set_persons([_make_person("Carol"), bob])  # Bob still present

    assert bar._person_combo.currentData() == str(bob.id)
    # findData-set triggers currentIndexChanged → one re-emit, still Bob.
    criteria_tuple = recorder.last
    assert isinstance(criteria_tuple, tuple)
    assert criteria_tuple[0].person_id == bob.id


def test_set_persons_resets_selection_when_person_gone(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)
    alice = _make_person("Alice")

    bar.set_persons([alice])
    bar._person_combo.setCurrentIndex(0)
    recorder.emissions.clear()

    bar.set_persons([_make_person("Bob")])  # Alice no longer exists

    assert bar._person_combo.currentIndex() == -1  # reset to the placeholder state
    assert recorder.last is None


def test_person_axis_combines_with_status_and_date(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)
    alice = _make_person("Alice")

    bar.set_persons([alice])
    bar._person_combo.setCurrentIndex(0)
    _uncheck_all(bar)
    _check(bar, "approved")
    bar._time_mode_combo.setCurrentIndex(1)
    recorder.emissions.clear()
    _set(bar._from_edit, 2024, 1, 1)  # 默认 from=一年前，晚于 to 会触发非法区间拦截
    _set(bar._to_edit, 2024, 12, 31)

    criteria_tuple = recorder.last
    assert isinstance(criteria_tuple, tuple)
    criteria = criteria_tuple[0]
    assert criteria.person_id == alice.id
    assert criteria.match_status is MatchStatus.APPROVED
    assert criteria.captured_to == datetime(2024, 12, 31, 12, 0, 0)


def test_clear_resets_person_axis_too(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)
    alice = _make_person("Alice")

    bar.set_persons([alice])
    bar._person_combo.setCurrentIndex(0)
    _uncheck_all(bar)
    _check(bar, "pending")
    bar.clear()

    assert recorder.last is None
    assert bar._person_combo.currentIndex() == -1
    assert all(not check.isChecked() for check in bar._status_checks.values())


def test_unmatched_option_emits_sentinel_criteria(qtbot) -> None:
    """ADR-036 D6：状态轴"未匹配"项发 UNMATCHED 哨兵（非 MatchStatus 枚举）。"""
    from photo_archiver.domain import UNMATCHED

    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    assert "unmatched" in bar._status_checks  # 未匹配复选框必须在面板中
    _uncheck_all(bar)
    _check(bar, "unmatched")

    criteria_tuple = recorder.last
    assert isinstance(criteria_tuple, tuple)
    assert criteria_tuple[0].match_status == UNMATCHED
    assert not isinstance(criteria_tuple[0].match_status, MatchStatus)


def test_unmatched_combines_with_person_axis(qtbot) -> None:
    """哨兵与人员轴 AND 组合（语义上恒空，但组合本身合法透传）。"""
    from uuid import uuid4

    from photo_archiver.domain import UNMATCHED

    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    person_id = uuid4()
    bar.set_persons([])
    bar._person_combo.addItem("Alice", str(person_id))
    bar._person_combo.setCurrentIndex(0)
    _uncheck_all(bar)
    _check(bar, "unmatched")

    criteria_tuple = recorder.last
    assert isinstance(criteria_tuple, tuple)
    assert criteria_tuple[0].person_id == person_id
    assert criteria_tuple[0].match_status == UNMATCHED


def test_clear_resets_unmatched_back_to_unset(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    _uncheck_all(bar)
    _check(bar, "unmatched")
    assert recorder.last is not None
    bar.clear()
    assert recorder.last is None


# ── Status counts（参考图 M8：复选框带计数）─────────────────────────────────


def test_set_status_counts_renders_counts_beside_labels(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)

    bar.set_status_counts({"pending": 812, "approved": 226, "rejected": 5, "unmatched": 210})

    assert text.FILTER_STATUS_COUNT_FORMAT.format(label="待审核", count=812) \
        == bar._status_checks["pending"].text()
    assert "（226）" in bar._status_checks["approved"].text()
    bar.set_status_counts(None)
    assert bar._status_checks["pending"].text() == "待审核"  # 计数清除


def test_set_status_counts_partial_keys_keep_other_labels(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)

    bar.set_status_counts({"approved": 3})

    assert bar._status_checks["pending"].text() == "待审核"  # 缺键状态保持文案
    assert "（3）" in bar._status_checks["approved"].text()


# ── Summary row + result count (Batch 4) ─────────────────────────────────────


def test_summary_starts_at_no_filter(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    assert bar._summary_label.text() == text.FILTER_SUMMARY_NONE


def test_set_result_count_updates_the_count_label(qtbot) -> None:
    bar = FilterBar()
    qtbot.addWidget(bar)
    bar.set_result_count(7)
    assert bar._count_label.text() == text.FILTER_RESULT_COUNT.format(count=7)


def test_summary_lists_all_active_conditions(qtbot) -> None:
    from photo_archiver.presentation import ui_text as text

    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)
    alice = _make_person("Alice")

    bar.set_persons([alice])
    bar._person_combo.setCurrentIndex(0)
    _uncheck_all(bar)
    _check(bar, "pending")  # 待审核
    bar._time_mode_combo.setCurrentIndex(1)
    _set(bar._from_edit, 2023, 1, 1)
    _set(bar._to_edit, 2023, 12, 31)

    summary = bar._summary_label.text()
    assert text.FILTER_SUMMARY_PERSON.format(name="Alice") in summary
    assert text.FILTER_SUMMARY_STATUS.format(name="待审核") in summary
    assert text.FILTER_SUMMARY_TIME_FROM.format(date="2023-01-01") in summary
    assert text.FILTER_SUMMARY_TIME_TO.format(date="2023-12-31") in summary
    assert recorder.last is not None  # 摘要与实际发出的 criteria 同源


def test_summary_lists_multi_status_selection(qtbot) -> None:
    """多选状态时摘要列出全部勾选状态（与发射的 criteria 元组同源）。"""
    bar = FilterBar()
    qtbot.addWidget(bar)
    recorder = _CriteriaRecorder(bar)

    _uncheck_all(bar)
    _check(bar, "approved")
    _check(bar, "rejected")

    summary = bar._summary_label.text()
    assert "已通过" in summary and "已拒绝" in summary
    assert isinstance(recorder.last, tuple) and len(recorder.last) == 2


def test_invalid_range_keeps_previous_summary_and_count(qtbot) -> None:
    """A blocked range never rewrites the summary to a condition it didn't apply."""
    bar = FilterBar()
    qtbot.addWidget(bar)
    bar.show()  # 内联提示的 isVisible() 断言需要窗口实际显示
    bar.set_result_count(3)
    _uncheck_all(bar)
    _check(bar, "pending")  # 有效：待审核

    bar._time_mode_combo.setCurrentIndex(1)
    _set(bar._from_edit, 2024, 6, 30)
    # 摘要基线取自最近一次"合法"应用（含自定义模式的默认区间 emission）；
    # 拦截只应阻止非法区间的重写，不应回滚已生效条件。
    summary_before = bar._summary_label.text()
    _set(bar._to_edit, 2023, 1, 1)  # invalid

    assert bar._date_warning_label.isVisible()
    assert bar._summary_label.text() == summary_before  # 仍反映生效筛选
    assert bar._count_label.text() == text.FILTER_RESULT_COUNT.format(count=3)
