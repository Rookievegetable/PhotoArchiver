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


# ── P8：告警分级渲染（强冲突 / 弱冲突 / 提示；未知 code 默认样式） ────────────


def test_warning_severity_classification_matches_semantics() -> None:
    """7 种已知 code 按文案语义归类：强/弱/提示三级。"""
    from photo_archiver.presentation import ui_text as text
    from photo_archiver.presentation.views.import_preview_dialog import (
        classify_import_warning,
    )

    assert classify_import_warning("identity_duplicate_in_file") == (
        text.IMPORT_WARNING_SEVERITY_STRONG
    )
    assert classify_import_warning("identity_duplicate_db") == (
        text.IMPORT_WARNING_SEVERITY_STRONG
    )
    assert classify_import_warning("name_department_duplicate_in_file") == (
        text.IMPORT_WARNING_SEVERITY_WEAK
    )
    assert classify_import_warning("name_department_duplicate_db") == (
        text.IMPORT_WARNING_SEVERITY_WEAK
    )
    for info_code in ("empty_name", "multi_name", "group_title"):
        assert classify_import_warning(info_code) == text.IMPORT_WARNING_SEVERITY_INFO
    assert classify_import_warning("mystery_code") == (
        text.IMPORT_WARNING_SEVERITY_DEFAULT
    )
    assert set(text.IMPORT_WARNING_SEVERITIES) == set(text.IMPORT_WARNING_TEXTS)


def test_warning_severity_styles_are_pairwise_distinct() -> None:
    """三级的（符号, 前景, 背景）两两可区分；未知样式不与三级混淆。"""
    from photo_archiver.presentation import ui_text as text
    from photo_archiver.presentation.views.import_preview_dialog import (
        _IMPORT_WARNING_DEFAULT_STYLE,
        _IMPORT_WARNING_STYLES,
    )

    styles = [
        _IMPORT_WARNING_STYLES[sev] for sev in (
            text.IMPORT_WARNING_SEVERITY_STRONG,
            text.IMPORT_WARNING_SEVERITY_WEAK,
            text.IMPORT_WARNING_SEVERITY_INFO,
        )
    ]
    assert len(set(styles)) == 3
    assert all(fg is not None and bg is not None for _sym, fg, bg in styles)
    assert _IMPORT_WARNING_DEFAULT_STYLE[1] is None  # 默认样式无配色


def test_build_warning_label_renders_each_severity_distinctly() -> None:
    """每类 code 的图标 + 配色可区分；文本保留完整文案。"""
    from photo_archiver.presentation import ui_text as text
    from photo_archiver.presentation.views.import_preview_dialog import (
        _IMPORT_WARNING_STYLES,
        build_warning_label,
        classify_import_warning,
    )

    for code in text.IMPORT_WARNING_SEVERITIES:
        symbol, fg, bg = _IMPORT_WARNING_STYLES[classify_import_warning(code)]
        label = build_warning_label([(code, "明细")])
        assert symbol in label.text()
        assert fg in label.text() and bg in label.text()  # 前景/背景配色上墙
        assert "background-color" in label.text()
        assert text.IMPORT_WARNING_TEXTS[code].split("（")[0].split("{")[0] in label.text()


def test_build_warning_label_unknown_code_falls_back_without_crash() -> None:
    """未知 code：默认样式（无配色 span、兜底模板），不崩溃。"""
    from photo_archiver.presentation.views.import_preview_dialog import (
        build_warning_label,
    )

    label = build_warning_label([("mystery_code", "x")])
    assert "mystery_code" in label.text()
    assert "background-color" not in label.text()  # 无配色 = 默认样式
    assert label.text().startswith("• ")  # 兜底前缀符号


def test_build_warning_label_escapes_html_and_joins_lines() -> None:
    """多条告警逐行渲染；detail 中的 HTML 元字符被转义（防注入）。"""
    from photo_archiver.presentation.views.import_preview_dialog import (
        build_warning_label,
    )

    label = build_warning_label([
        ("multi_name", "3"),
        ("group_title", "<名单>"),
    ])
    assert "<br>" in label.text()
    assert "&" + "lt;" + "名单" + "&" + "gt;" in label.text()  # HTML 元字符已转义
    assert "<名单>" not in label.text()  # 原始标记不出现（防注入）


def test_dialog_renders_graded_warning_cells(tmp_path: Path, qtbot) -> None:
    """对话框告警列：分级 QLabel 单元格（强/弱/提示三码同屏可区分）。"""
    from photo_archiver.presentation.views.import_preview_dialog import (
        _IMPORT_WARNING_STYLES,
        classify_import_warning,
    )

    from photo_archiver.domain import Person

    parse, confirm, people = _services(tmp_path / "graded.db")
    people.add(Person(name="李四", department="市场部"))  # 造库内姓名+部门重复
    path = _write_csv(tmp_path / "graded.csv", (
        "姓名,工号,部门\n"
        "1甲、1乙,,\n"  # multi_name（提示）
        "张三,E001,工程部\n"
        "张三,E001,工程部\n"  # identity_duplicate_in_file（强冲突）
        "李四,E002,市场部\n"  # name_department_duplicate_db（弱冲突）
    ))
    draft = parse.execute(ParseImportDraftCommand(path))
    dialog = ImportPreviewDialog(draft, SimpleNamespaceService(parse, confirm), path)
    qtbot.addWidget(dialog)
    dialog.show()

    expected_codes = {
        "multi_name", "identity_duplicate_in_file", "name_department_duplicate_db",
    }
    seen = set()
    for row_index, row in enumerate(dialog._draft.rows):
        for code in row.warnings and [w[0] for w in row.warnings] or []:
            if code not in expected_codes:
                continue
            seen.add(code)
            widget = dialog._table.cellWidget(row_index, 5)
            assert isinstance(widget, QLabel)
            symbol, fg, _bg = _IMPORT_WARNING_STYLES[classify_import_warning(code)]
            assert symbol in widget.text()
            assert fg in widget.text()
    assert seen == expected_codes


# ── P10：草稿取消文案不再暗示可回看 ──────────────────────────────────────────


def test_status_import_draft_parsed_has_no_revisit_hint() -> None:
    """P10/D6-A：取消文案为裁决文本，不含任何「回看」暗示。"""
    from photo_archiver.presentation import ui_text as text

    assert text.STATUS_IMPORT_DRAFT_PARSED == (
        "取消将丢弃本次草稿；如需导入请重新选择文件"
    )
    assert "回看" not in text.STATUS_IMPORT_DRAFT_PARSED
    assert "丢弃" in text.STATUS_IMPORT_DRAFT_PARSED
    assert "重新选择文件" in text.STATUS_IMPORT_DRAFT_PARSED
    assert "{rows}" not in text.STATUS_IMPORT_DRAFT_PARSED  # 不再需要行数占位
