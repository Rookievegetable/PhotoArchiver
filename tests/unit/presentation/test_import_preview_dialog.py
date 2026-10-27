"""Stage A UI tests: ImportPreviewDialog editing, counts, split and cancel.

The dialog is exercised over a real parsed draft (real reader + real SQLite);
exec() is never called — edits and actions are driven directly.
"""

from pathlib import Path

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QLabel

from photo_archiver.application.commands.import_draft import ParseImportDraftCommand
from photo_archiver.presentation.views.import_preview_dialog import (
    CONFIRM_SYNC_LIMIT,
    ImportPreviewDialog,
)
from tests.integration.test_import_draft_flow import _services  # noqa: F401  (reuse wiring)


def _write_csv(path: Path, content: str) -> Path:
    path.write_bytes(content.encode("utf-8"))
    return path


@pytest.fixture
def parsed(tmp_path: Path):
    """Real parse over a mixed-content roster; returns (draft, services, people)."""
    path = _write_csv(tmp_path / "roster.csv", (
        "姓名,工号,部门\n"
        "1曹徽文、2曹紫夏、3贾偌涵,\n"
        "2组\n"
        "张三,E001,工程部\n"
        "李四,E002,\n"
    ))
    parse, confirm, people = _services(tmp_path / "a.db")
    draft = parse.execute(ParseImportDraftCommand(path))
    return draft, parse, confirm, people, tmp_path


def _make_dialog(parsed, qtbot):
    draft, parse, confirm, people, tmp_path = parsed
    services = SimpleNamespaceService(parse, confirm)
    dialog = ImportPreviewDialog(draft, services, tmp_path / "roster.csv")
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog, people


class SimpleNamespaceService:
    """Minimal service container mirroring context.services attribute access."""

    def __init__(self, parse, confirm) -> None:
        self.parse_import_draft = parse
        self.confirm_import = confirm


def test_dialog_populates_rows_counts_and_warnings(parsed, qtbot) -> None:
    dialog, people = _make_dialog(parsed, qtbot)

    assert dialog._table.rowCount() == 4  # 6 数据行：拆分前 4 行（组标题/多名/张三/李四）…
    counts = next(w for w in dialog.findChildren(QLabel) if "将新建" in w.text())
    assert "跳过 1" in counts.text()  # “2组”默认跳过
    assert "告警 2" in counts.text()  # 组标题 + 多名
    assert "合并 0" in counts.text()


def test_split_button_splits_row_and_updates_counts(parsed, qtbot) -> None:
    dialog, people = _make_dialog(parsed, qtbot)
    multi = next(row for row in dialog._draft.rows if any(w[0] == "multi_name" for w in row.warnings))
    dialog._on_split(multi)

    names = [row.parsed_name for row in dialog._draft.rows]
    assert "1曹徽文" in names and "2曹紫夏" in names and "3贾偌涵" in names
    counts = next(w for w in dialog.findChildren(QLabel) if "将新建" in w.text())
    assert "将新建 5" in counts.text()  # 3 拆分行 + 张三 + 李四；组标题跳过


def test_split_noop_shows_visible_feedback(parsed, qtbot) -> None:
    """P9：拆分无可拆内容时界面给出可见反馈（此前为静默 no-op）。"""
    dialog, _people = _make_dialog(parsed, qtbot)
    single = next(row for row in dialog._draft.rows if row.parsed_name == "张三")

    dialog._on_split(single)

    from photo_archiver.presentation import ui_text as text
    assert dialog._feedback_label.text() == text.IMPORT_PREVIEW_SPLIT_NOOP


def test_split_success_clears_feedback(parsed, qtbot) -> None:
    """P9：成功拆分不残留 no-op 提示。"""
    dialog, _people = _make_dialog(parsed, qtbot)
    multi = next(row for row in dialog._draft.rows if any(w[0] == "multi_name" for w in row.warnings))

    dialog._on_split(multi)

    assert dialog._feedback_label.text() == ""


def test_action_switch_to_skip_persists(parsed, qtbot) -> None:
    dialog, people = _make_dialog(parsed, qtbot)
    target = next(row for row in dialog._draft.rows if row.parsed_name == "张三")
    combo = dialog._table.cellWidget(dialog._draft.rows.index(target), 6)
    combo.setCurrentIndex(2)  # 跳过
    assert target.action == "skip"


def test_confirm_via_window_writes_people(parsed, qtbot, monkeypatch) -> None:
    """对话框 accept 后窗口同步确认：人员写入、roster 顺序生效。"""
    draft, parse, confirm, people, tmp_path = parsed
    services = SimpleNamespaceService(parse, confirm)
    dialog = ImportPreviewDialog(draft, services, tmp_path / "roster.csv")
    qtbot.addWidget(dialog)
    multi = next(row for row in dialog._draft.rows if any(w[0] == "multi_name" for w in row.warnings))
    dialog._on_split(multi)

    dialog.accept()  # 窗口随后用 dialog.batch_id / row_count 执行确认
    result = confirm.execute(
        __import__("photo_archiver.application.commands.import_draft", fromlist=["ConfirmImportCommand"])
        .ConfirmImportCommand(dialog.batch_id),
    )
    assert result.imported_count == 5  # 3 拆分 + 张三 + 李四；“2组”跳过
    names = [p.name for p in people.list_all()]
    assert names[:3] == ["1曹徽文", "2曹紫夏", "3贾偌涵"]  # roster 顺序 = 拆分后顺序


def test_cancel_keeps_draft(parsed, qtbot) -> None:
    dialog, people = _make_dialog(parsed, qtbot)
    dialog.reject()
    assert people.list_all() == []  # 未确认不写正式人员


def test_unknown_warning_code_falls_back(parsed, qtbot) -> None:
    """未知告警 code 走兜底模板，不在预览中崩溃。"""
    dialog, _ = _make_dialog(parsed, qtbot)
    row = dialog._draft.rows[0]
    row.warnings = (("mystery_code", "x"),)
    line = dialog._warnings_text(row)
    assert "mystery_code" in line


def test_large_roster_notice_only_over_sync_limit(parsed, qtbot) -> None:
    """>CONFIRM_SYNC_LIMIT 行显示后台确认提示；小名单不显示（非模态告知）。"""
    draft, parse, confirm, people, tmp_path = parsed
    small = ImportPreviewDialog(draft, SimpleNamespaceService(parse, confirm), tmp_path / "roster.csv")
    qtbot.addWidget(small)
    assert not any("超过" in w.text() for w in small.findChildren(QLabel))

    path = tmp_path / "large.csv"
    lines = ["姓名,工号"] + [
        f"人员{index:04d},ID{index:04d}" for index in range(1, CONFIRM_SYNC_LIMIT + 2)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    large_draft = parse.execute(ParseImportDraftCommand(path))
    large = ImportPreviewDialog(
        large_draft, SimpleNamespaceService(parse, confirm), path,
    )
    qtbot.addWidget(large)
    notices = [w.text() for w in large.findChildren(QLabel) if "超过" in w.text()]
    assert len(notices) == 1
    assert str(CONFIRM_SYNC_LIMIT) in notices[0]
