"""FilterBar 人员搜索接线测试（人员下拉智能搜索，2026-09-05 UI 轮）.

验证补全链路的数据流：输入 → 补全列表按智能排名刷新；补全激活 → 落到
对应人员并发出 criteria；输入过程本身不改变 criteria；清除复位占位态。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from photo_archiver.domain import Person
from photo_archiver.presentation.views.filter_bar import FilterBar


def _make_person(name: str) -> Person:
    return Person(name=name)


def _make_bar(qtbot) -> tuple[FilterBar, list]:
    bar = FilterBar()
    qtbot.addWidget(bar)
    emissions: list[object] = []
    bar.criteria_changed.connect(emissions.append)
    return bar, emissions


def test_completer_lists_all_persons_and_ranks_on_input(qtbot) -> None:
    bar, _ = _make_bar(qtbot)
    bar.set_persons([_make_person("陈1号"), _make_person("陈10号"), _make_person("王五")])

    bar._person_combo.lineEdit().setText("10")

    assert list(bar._person_completer_model.stringList()) == ["陈10号"]

    bar._person_combo.lineEdit().setText("陈")
    # 陈1号/陈10号同层（连续包含、首现位置相同）→ 层内按名称字典序；王五不含"陈"被排除。
    assert list(bar._person_completer_model.stringList()) == ["陈10号", "陈1号"]


def test_typing_alone_does_not_change_criteria(qtbot) -> None:
    bar, emissions = _make_bar(qtbot)
    bar.set_persons([_make_person("Alice"), _make_person("Bob")])
    emissions.clear()

    bar._person_combo.lineEdit().setText("Ali")

    assert bar._person_combo.currentIndex() == -1  # 未选中 = 占位态
    assert all(e is None for e in emissions)  # 只有无约束的复位发过 None


def test_completion_activation_selects_person_and_emits_criteria(qtbot) -> None:
    bar, emissions = _make_bar(qtbot)
    alice = _make_person("Alice")
    bar.set_persons([alice, _make_person("Bob")])
    emissions.clear()

    bar._on_person_completion_activated("Alice")

    assert bar._person_combo.currentData() == str(alice.id)
    assert emissions[-1] is not None and emissions[-1].person_id == alice.id


def test_clear_resets_search_text_and_selection(qtbot) -> None:
    bar, emissions = _make_bar(qtbot)
    bar.set_persons([_make_person("Alice"), _make_person("Bob")])
    bar._person_combo.lineEdit().setText("Ali")
    bar._person_combo.setCurrentIndex(0)
    emissions.clear()

    bar.clear()

    assert bar._person_combo.lineEdit().text() == ""
    assert bar._person_combo.currentIndex() == -1
    assert bar._person_combo.placeholderText() == "全部人员"
    assert emissions[-1] is None


def test_set_persons_refreshes_search_source(qtbot) -> None:
    bar, _ = _make_bar(qtbot)
    bar.set_persons([_make_person("陈1号")])

    bar._person_combo.lineEdit().setText("陈2")

    assert list(bar._person_completer_model.stringList()) == []
    bar.set_persons([_make_person("陈2号")])
    bar._person_combo.lineEdit().setText("陈2")
    assert list(bar._person_completer_model.stringList()) == ["陈2号"]
