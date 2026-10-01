"""Combo search helper tests (2026-10-01 审核中心身份下拉搜索).

NameSearchComboBinder reuses the FilterBar person-axis pattern: editable
combo + smart-ranked completion via person_name_ranker. Items are read
back from the combo itself; picking a completion locates the first item
with that name.
"""

from uuid import uuid4

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QComboBox

from photo_archiver.presentation.combo_search import NameSearchComboBinder


def _make_combo(qtbot) -> tuple[QComboBox, NameSearchComboBinder]:
    combo = QComboBox()
    combo.addItem("未指定", None)
    alice = uuid4()
    bob = uuid4()
    combo.addItem("Alice", alice)
    combo.addItem("Bob", bob)
    combo.addItem("阿明", uuid4())
    binder = NameSearchComboBinder(combo, parent=combo)
    qtbot.addWidget(combo)
    return combo, binder


def test_attach_makes_combo_editable_without_insert(qtbot) -> None:
    combo, binder = _make_combo(qtbot)
    assert combo.isEditable()
    assert combo.insertPolicy() == QComboBox.InsertPolicy.NoInsert
    assert combo.completer() is not None


def test_typing_ranks_completion_list(qtbot) -> None:
    combo, binder = _make_combo(qtbot)
    combo.lineEdit().setText("ali")
    ranked = binder._completer_model.stringList()
    assert ranked == ["Alice"]  # 前缀命中
    combo.lineEdit().setText("b")
    ranked = binder._completer_model.stringList()
    assert "Bob" in ranked and "Alice" not in ranked


def test_empty_query_defers_to_combo_dropdown(qtbot) -> None:
    """空查询 = ranker 文档化契约（匹配为空，caller 呈现完整列表）——点击
    展开按钮仍显示全部项，补全列表仅在输入时参与排名。"""
    combo, binder = _make_combo(qtbot)
    combo.lineEdit().setText("  ")
    assert binder._completer_model.stringList() == []


def test_completion_activation_locates_matching_item(qtbot) -> None:
    combo, binder = _make_combo(qtbot)
    binder._completer.activated.emit("Bob")
    assert combo.currentText() == "Bob"
    assert combo.currentData() is not None  # Bob 的 UUID


def test_duplicate_names_resolve_to_first_item(qtbot) -> None:
    combo = QComboBox()
    first, second = uuid4(), uuid4()
    combo.addItem("同名", first)
    combo.addItem("同名", second)
    binder = NameSearchComboBinder(combo, parent=combo)
    binder._completer.activated.emit("同名")
    assert combo.currentData() == first  # 与 FilterBar 行为一致：首个匹配项
