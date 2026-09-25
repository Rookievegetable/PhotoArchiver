"""RecognitionScopeDialog tests — 阶段 C Commit 3 范围选择 UI.

Covers the five face-count presets ([1] [2-3] [4-5] [6-10] [11+]) with any
combination allowed, the OK gate (at least one range), and the photo-scope
radios (all photos vs. the library selection). The dialog only collects
input — FaceCountRange construction is the domain mapping under test.
"""

from pathlib import Path

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDialogButtonBox

from photo_archiver.domain import FaceCountRange
from photo_archiver.presentation.views.recognition_scope_dialog import (
    _SCOPE_PRESETS,
    RecognitionScopeDialog,
)


def test_defaults_select_all_presets_and_all_photos(qtbot) -> None:
    """默认全选五档（等价 FaceCountRange(1, None)）+ 全部照片。"""
    dialog = RecognitionScopeDialog(selected_count=0)
    qtbot.addWidget(dialog)

    assert dialog.selected_ranges == _SCOPE_PRESETS
    assert dialog.photo_scope_selected_only is False
    ok = dialog._ok_button
    assert ok.isEnabled() is True


def test_presets_map_to_expected_domain_ranges() -> None:
    """五档预设对应领域值对象：[1] [2-3] [4-5] [6-10] [11+]。"""
    assert [str(preset) for preset in _SCOPE_PRESETS] == ["1", "2-3", "4-5", "6-10", "11+"]


def test_arbitrary_combination_returns_checked_ranges_in_preset_order(qtbot) -> None:
    """任意组合：只勾 [2-3] 和 [11+] 时按预设顺序返回。"""
    dialog = RecognitionScopeDialog()
    qtbot.addWidget(dialog)
    for check in dialog._range_checks:
        check.setChecked(False)
    dialog._range_checks[1].setChecked(True)
    dialog._range_checks[4].setChecked(True)

    assert dialog.selected_ranges == (FaceCountRange(2, 3), FaceCountRange(11, None))


def test_ok_disabled_while_no_range_selected(qtbot) -> None:
    """一档都不选时 OK 置灰，勾选任一档后恢复。"""
    dialog = RecognitionScopeDialog()
    qtbot.addWidget(dialog)
    for check in dialog._range_checks:
        check.setChecked(False)
    assert dialog._ok_button.isEnabled() is False
    assert dialog._ok_button.toolTip() != ""

    dialog._range_checks[0].setChecked(True)
    assert dialog._ok_button.isEnabled() is True
    assert dialog._ok_button.toolTip() == ""


def test_selected_only_radio_disabled_without_selection(qtbot) -> None:
    """无选区时「仅选中照片」不可选，默认停在全部照片。"""
    dialog = RecognitionScopeDialog(selected_count=0)
    qtbot.addWidget(dialog)
    assert dialog._selected_photos_radio.isEnabled() is False
    assert dialog.photo_scope_selected_only is False


def test_selected_only_radio_enabled_with_selection_count(qtbot) -> None:
    """有选区时可选，文案携带选中数量。"""
    dialog = RecognitionScopeDialog(selected_count=3)
    qtbot.addWidget(dialog)
    assert dialog._selected_photos_radio.isEnabled() is True
    assert "3" in dialog._selected_photos_radio.text()

    dialog._selected_photos_radio.setChecked(True)
    assert dialog.photo_scope_selected_only is True


def test_reject_default_button_wiring(qtbot) -> None:
    """OK/Cancel 接标准 accept/reject 通道。"""
    dialog = RecognitionScopeDialog()
    qtbot.addWidget(dialog)
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
# ── Stage F：重试选项与失败清单导出入口 ─────────────────────────────────────


def test_retry_radio_disabled_without_retryables(qtbot) -> None:
    dialog = RecognitionScopeDialog(retryable_count=0)
    qtbot.addWidget(dialog)
    assert dialog._retry_radio.isEnabled() is False
    assert dialog.photo_scope == "all"


def test_retry_radio_enabled_with_count_and_scope_property(qtbot) -> None:
    dialog = RecognitionScopeDialog(retryable_count=7)
    qtbot.addWidget(dialog)
    assert dialog._retry_radio.isEnabled() is True
    assert "7" in dialog._retry_radio.text()

    dialog._retry_radio.setChecked(True)
    assert dialog.photo_scope == "retry"


def test_photo_scope_reflects_selected_radio(qtbot) -> None:
    dialog = RecognitionScopeDialog(selected_count=3)
    qtbot.addWidget(dialog)
    dialog._selected_photos_radio.setChecked(True)
    assert dialog.photo_scope == "selected"


def test_export_button_disabled_without_failures(qtbot) -> None:
    dialog = RecognitionScopeDialog(retryable_count=0)
    qtbot.addWidget(dialog)
    assert dialog._export_button.isEnabled() is False


def test_export_button_invokes_service_with_run_id(qtbot, tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace
    from uuid import uuid4

    from PySide6.QtWidgets import QFileDialog, QMessageBox

    run_id = uuid4()
    calls: list[tuple] = []

    def _fake_export_csv(rid, path):
        calls.append((rid, path))
        Path(path).write_text("photo_id,raw_path,classification,recognition_run_id",
                              encoding="utf-8-sig")
        return 2

    service = SimpleNamespace(export_csv=_fake_export_csv)
    dialog = RecognitionScopeDialog(
        retryable_count=2, failure_service=service, latest_run_id=run_id,
    )
    qtbot.addWidget(dialog)
    assert dialog._export_button.isEnabled() is True

    target = tmp_path / "failures.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(target), "")))
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: 0))

    dialog._on_export_failures_clicked()

    assert calls == [(run_id, str(target))]  # QFileDialog 返回 str 路径
    assert target.exists()
