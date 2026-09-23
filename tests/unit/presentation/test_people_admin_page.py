"""Stage B people page tests: rendering, edit surface, reorder, batch review.

The page is exercised over real SQLite services (like the stage-A preview
dialog tests); no modal is opened — edits and actions are driven directly.
The stage-B desktop review fixes have their own section at the end: row drops
must reorder through the real viewport receive path without leaving a blank
row, the danger dialog must arrive with the chosen person selected, and every
rejection must read in Chinese.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands import AddPersonCommand
from photo_archiver.application.services import (
    DeletePersonService,
    ListPersonsService,
    ManagePeopleService,
)
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.people_admin_page import PeopleAdminPage
from photo_archiver.presentation.views.person_deletion_dialog import PersonDeletionDialog


def _services(tmp_path: Path):
    repositories = build_sqlite_repositories(tmp_path / "page.db")
    manage = ManagePeopleService(repositories.people, repositories.import_batches)
    return manage, ListPersonsService(repositories.people), DeletePersonService(
        repositories.people,
        repositories.photos,
        repositories.recognition,
        repositories.face_embeddings,
    ), repositories


@pytest.fixture
def populated(tmp_path: Path, qtbot):
    """Page over a three-person roster; returns (page, manage, repositories)."""
    repositories = build_sqlite_repositories(tmp_path / "page.db")
    manage = ManagePeopleService(repositories.people, repositories.import_batches)
    for name in ("张三", "李四", "王五"):
        manage.add_person(AddPersonCommand(name=name))
    page = PeopleAdminPage(
        manage,
        ListPersonsService(repositories.people),
        DeletePersonService(
            repositories.people,
            repositories.photos,
            repositories.recognition,
            repositories.face_embeddings,
        ),
    )
    qtbot.addWidget(page)
    return page, manage, repositories


def test_page_renders_roster_in_order_with_columns(populated) -> None:
    page, _, _ = populated
    table = page._table
    assert table.rowCount() == 3
    names = [table.item(row, 1).text() for row in range(table.rowCount())]
    assert names == ["张三", "李四", "王五"]
    assert [table.item(row, 0).text() for row in range(3)] == ["1", "2", "3"]


def test_move_selected_persists_and_updates_positions(populated) -> None:
    page, _, repositories = populated
    page._table.selectRow(0)
    page.move_selected(1)  # 张三下移
    names = [p.name for p in repositories.people.list_all()]
    assert names == ["李四", "张三", "王五"]
    assert [p.roster_order for p in repositories.people.list_all()] == [1, 2, 3]


def test_drop_rows_reorders(populated) -> None:
    page, _, repositories = populated
    page._on_rows_dropped(2, 0)  # 王五拖到最前
    assert [p.name for p in repositories.people.list_all()] == ["王五", "张三", "李四"]


def test_batch_review_filters_and_disables_reorder(populated, tmp_path: Path) -> None:
    page, manage, repositories = populated
    page.show()
    # 给 张三 造一个批次来源：先导入一个批次再合并
    from photo_archiver.application.commands import ConfirmImportCommand, ParseImportDraftCommand
    from photo_archiver.application.services import ConfirmImportService, ParseImportDraftService
    from photo_archiver.infrastructure.importers import FileRosterTableReader

    csv = tmp_path / "batch.csv"
    csv.write_text("姓名,工号\n张三,E001\n", encoding="utf-8")
    parse = ParseImportDraftService(
        FileRosterTableReader(), repositories.import_batches, repositories.people,
    )
    confirm = ConfirmImportService(repositories.import_batches, repositories.people)
    draft = parse.execute(ParseImportDraftCommand(csv))
    confirm.execute(ConfirmImportCommand(draft.batch.id))
    page.refresh()

    index = page._batch_combo.findText("batch.csv", flags=Qt.MatchFlag.MatchContains)
    assert index > 0  # 批次条目出现（含人数）
    page._batch_combo.setCurrentIndex(index)
    page._on_batch_selected(index)
    assert page._table.rowCount() == 1  # 该批次带入 1 人（名单里的「张三 E001」是新建，不合并无工号的同名人员）
    assert page._table.item(0, 1).text() == "张三"
    assert page._table.item(0, 5).text() == "batch.csv"  # 来源批次列可见
    assert page._batch_hint.isVisible()  # 只读提示显示
    assert not page._table.dragEnabled()  # 回看态禁止拖拽
    page._batch_combo.setCurrentIndex(0)
    page._on_batch_selected(0)
    assert page._table.rowCount() == 4


def test_add_button_opens_dialog_and_appends(populated, monkeypatch) -> None:
    page, _, repositories = populated
    dialog_stub = type("D", (), {
        "exec": lambda self: 1,
        "values": lambda self: {"name": "赵六", "identity": "", "department": "", "note": ""},
    })()
    monkeypatch.setattr(
        "photo_archiver.presentation.views.people_admin_page.PersonEditDialog",
        lambda *a, **k: dialog_stub,
    )
    page._add_button.click()
    assert any(p.name == "赵六" for p in repositories.people.list_all())
    assert page._table.rowCount() == 4


def test_validation_error_is_shown_without_write(populated, monkeypatch) -> None:
    page, _, repositories = populated
    shown = Mock(return_value=0)
    monkeypatch.setattr(QMessageBox, "warning", shown)
    dialog_stub = type("D", (), {
        "exec": lambda self: 1,
        "values": lambda self: {"name": "", "identity": "", "department": "", "note": ""},
    })()
    monkeypatch.setattr(
        "photo_archiver.presentation.views.people_admin_page.PersonEditDialog",
        lambda *a, **k: dialog_stub,
    )
    page._add_button.click()
    assert len(repositories.people.list_all()) == 3  # 未写入
    assert shown.call_count == 1  # 域校验信息原文回显，不静默
    assert "保存失败" in shown.call_args.args[2]


def test_empty_page_shows_empty_hint(tmp_path: Path, qtbot) -> None:
    manage_people, list_persons, delete_person, _ = _services(tmp_path)
    page = PeopleAdminPage(manage_people, list_persons, delete_person)
    qtbot.addWidget(page)
    labels = [w.text() for w in page.findChildren(QLabel)]
    assert any("名单为空" in t for t in labels)
    assert page._table.rowCount() == 0


# ── Stage-B desktop review fixes ──────────────────────────────────────────

_ROW_MIME_TYPE = "application/x-qabstractitemmodeldatalist"


def _row_payload() -> QMimeData:
    """Return the mime data a Qt item-view row drag carries."""
    mime = QMimeData()
    mime.setData(_ROW_MIME_TYPE, b"row-payload")
    return mime


def _row_center(table, row: int) -> QPoint:
    """Return a real viewport point inside ``row``'s cells."""
    return table.visualItemRect(table.item(row, 1)).center()


def test_table_keeps_row_drops_enabled_for_reordering(populated) -> None:
    """验收 #2：拖拽模式必须真的接收落点（``DragOnly`` 会关掉 acceptDrops）。"""
    table = populated[0]._table
    assert table.dragEnabled()
    assert table.acceptDrops()
    assert table.viewport().acceptDrops()


def test_row_drop_reorders_the_roster_without_a_blank_row(populated) -> None:
    """验收 #2：拖拽重排后目标行仍在——Qt 内部行移动曾把它删成空白行。"""
    page, _, repositories = populated
    page.resize(900, 360)
    page.show()
    table = page._table
    source_point = _row_center(table, 2)  # 王五
    target_point = _row_center(table, 0)  # 拖到最前
    assert table.indexAt(source_point).row() == 2
    assert table.indexAt(target_point).row() == 0

    mime = _row_payload()
    possible = Qt.DropAction.CopyAction | Qt.DropAction.MoveAction  # 真实拖拽给出的动作集
    enter = QDragEnterEvent(
        target_point, possible, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    move = QDragMoveEvent(
        target_point, possible, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(table.viewport(), enter)
    QApplication.sendEvent(table.viewport(), move)
    assert enter.isAccepted()
    assert move.isAccepted()  # 落点被接收，用户能看到可放置状态

    table.selectRow(2)  # 真实拖拽总是先按下源行
    table._drag_source_row = 2  # startDrag 记录的源行
    drop = QDropEvent(
        QPointF(target_point), possible, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(table.viewport(), drop)

    assert drop.isAccepted()
    assert drop.dropAction() == Qt.DropAction.CopyAction  # Qt 不得再自行改模型
    assert [p.name for p in repositories.people.list_all()] == ["王五", "张三", "李四"]
    assert [p.roster_order for p in repositories.people.list_all()] == [1, 2, 3]
    assert table.rowCount() == 3
    assert [table.item(row, 1).text() for row in range(3)] == ["王五", "张三", "李四"]
    assert all(table.cellWidget(row, 6) is not None for row in range(3))  # 操作列不空
    # 落点降级成功：Qt 不会动模型，被拖动的人在自己的新位置保持选中
    assert [index.row() for index in table.selectionModel().selectedRows()] == [0]


def test_move_only_drop_leaves_no_stale_selection(populated) -> None:
    """落点无法降级为复制时，选区必须清空（内部移动就删不到任何行）。"""
    page, _, repositories = populated
    page.resize(900, 360)
    page.show()
    table = page._table
    table.selectRow(2)
    assert table.selectionModel().selectedRows()

    target_point = _row_center(table, 0)
    assert table.indexAt(target_point).row() == 0
    mime = _row_payload()
    QApplication.sendEvent(table.viewport(), QDragEnterEvent(
        target_point, Qt.DropAction.MoveAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    ))

    table._drag_source_row = 2
    drop = QDropEvent(
        QPointF(target_point), Qt.DropAction.MoveAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(table.viewport(), drop)

    assert drop.isAccepted()
    assert [p.name for p in repositories.people.list_all()] == ["王五", "张三", "李四"]
    assert table.rowCount() == 3
    assert not table.selectionModel().selectedRows()


def test_foreign_drag_payload_never_reorders_the_roster(populated) -> None:
    """验收 #2：外部拖拽载荷（文本等）不得被当作重排请求。"""
    page, _, repositories = populated
    page.resize(900, 360)
    page.show()
    table = page._table
    mime = QMimeData()
    mime.setText("外部文本")
    enter = QDragEnterEvent(
        _row_center(table, 0), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(table.viewport(), enter)

    assert not enter.isAccepted()
    assert [p.name for p in repositories.people.list_all()] == ["张三", "李四", "王五"]


def test_batch_review_disables_row_drops(populated) -> None:
    """回看态只读：拖拽载荷在禁用拖拽时一律不接受。"""
    page, _, _ = populated
    page.resize(900, 360)
    page.show()
    table = page._table
    table.setDragEnabled(False)  # _render_rows 在批次回看态设置
    enter = QDragEnterEvent(
        _row_center(table, 1), Qt.DropAction.MoveAction, _row_payload(),
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(table.viewport(), enter)

    assert not enter.isAccepted()


def test_delete_selected_row_preselects_it_in_the_confirm_dialog(populated, monkeypatch) -> None:
    """验收 #3：确认对话框必须预选表格里选中的那位，不再要求二次选择。"""
    page, _, _ = populated
    captured: dict[str, object] = {}

    class _StubDialog:
        def __init__(self, *args, **kwargs) -> None:
            captured.update(kwargs)

        def exec(self) -> int:
            return 0  # 取消：不得删除

    monkeypatch.setattr(
        "photo_archiver.presentation.views.people_admin_page.PersonDeletionDialog",
        _StubDialog,
    )
    page._table.selectRow(1)
    page._delete_button.click()

    assert captured["preselect_id"] == page.visible_people()[1].id
    assert captured["parent"] is page


def test_deletion_dialog_selects_and_focuses_the_requested_person(tmp_path, qtbot) -> None:
    """验收 #3：对话框构造即选中并聚焦目标人员（预览同步）。"""
    manage, list_persons, delete_person, _ = _services(tmp_path)
    for name in ("张三", "李四", "王五"):
        manage.add_person(AddPersonCommand(name=name))
    third = list_persons.execute()[2]

    dialog = PersonDeletionDialog(list_persons, delete_person, preselect_id=third.id)
    qtbot.addWidget(dialog)

    assert dialog.selected_person_id() == third.id
    assert dialog.selected_person_name().startswith("王五")
    assert dialog.result_preview() is not None  # 预览已按所选人员渲染

    dialog.show()
    assert dialog.focusWidget() is dialog._combo  # 选择项开局即聚焦


def test_move_buttons_keep_the_person_selected_at_the_new_position(populated) -> None:
    """复审追问：上移/下移后高亮必须跟着人走，不能留在原行号。"""
    page, _, repositories = populated
    page._table.selectRow(1)  # 李四
    page._move_down_button.click()

    assert [p.name for p in repositories.people.list_all()] == ["张三", "王五", "李四"]
    assert page._table.item(2, 1).text() == "李四"
    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [2]
    assert page._table.currentRow() == 2
    assert not page._move_down_button.isEnabled()  # 已到末尾：置灰而非静默无效

    page._move_up_button.click()  # 李四 回退一行
    assert [p.name for p in repositories.people.list_all()] == ["张三", "李四", "王五"]
    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [1]
    assert page._move_up_button.isEnabled()

    page._move_up_button.click()  # 再退一行：李四 到开头
    assert [p.name for p in repositories.people.list_all()] == ["李四", "张三", "王五"]
    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [0]
    assert page._table.item(0, 1).text() == "李四"
    assert not page._move_up_button.isEnabled()  # 已到开头


def test_repeated_move_clicks_move_the_same_person(populated) -> None:
    """连续两次下移必须移动同一个人（旧行为第二次移动的是取而代之的那位）。"""
    page, _, repositories = populated
    page._table.selectRow(0)  # 张三
    page._move_down_button.click()
    page._move_down_button.click()

    assert [p.name for p in repositories.people.list_all()] == ["李四", "王五", "张三"]
    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [2]
    assert page._table.item(2, 1).text() == "张三"


def test_move_buttons_grey_out_at_the_roster_edges(populated) -> None:
    """边界态：首行不能上移、末行不能下移、无选区两个都禁用。"""
    page, _, _ = populated
    page._table.selectRow(0)
    assert not page._move_up_button.isEnabled()
    assert page._move_down_button.isEnabled()

    page._table.selectRow(2)
    assert page._move_up_button.isEnabled()
    assert not page._move_down_button.isEnabled()

    page._table.clearSelection()
    assert not page._move_up_button.isEnabled()
    assert not page._move_down_button.isEnabled()
    assert not page._delete_button.isEnabled()


def test_selection_follows_the_person_across_refreshes(populated) -> None:
    """任何重载（导入/删除/排序）后仍锁定同一个人，而不是同一个行号。"""
    page, manage, _ = populated
    page._table.selectRow(2)  # 王五
    manage.add_person(AddPersonCommand(name="赵六"))  # 名单变化（窗口会重载本页）
    page.refresh()

    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [2]
    assert page._table.item(2, 1).text() == "王五"

    page.move_row(2, 0)  # 王五挪到最前
    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [0]
    assert page._table.item(0, 1).text() == "王五"


def test_identity_conflict_is_reported_in_chinese(populated, monkeypatch) -> None:
    """验收 #1：工号被占用时报中文原因，且不再出现英文原文。"""
    page, manage, repositories = populated
    manage.add_person(AddPersonCommand(name="赵六", identity="E100"))
    shown = Mock(return_value=0)
    monkeypatch.setattr(QMessageBox, "warning", shown)
    dialog_stub = type("D", (), {
        "exec": lambda self: 1,
        "values": lambda self: {
            "name": "钱七", "identity": "E100", "department": "", "note": "",
        },
    })()
    monkeypatch.setattr(
        "photo_archiver.presentation.views.people_admin_page.PersonEditDialog",
        lambda *a, **k: dialog_stub,
    )

    page._add_button.click()

    assert len(repositories.people.list_all()) == 4  # 未写入
    title, message = shown.call_args.args[1], shown.call_args.args[2]
    assert title == text.PEOPLE_PAGE_SAVE_FAILED_TITLE
    assert "工号已被其他人员占用：E100" in message
    assert "identity already registered" not in message


# ── Performance regressions (P0: 拖拽/上移下移延迟优化) ─────────────────────


def test_move_renders_the_table_exactly_once(populated, monkeypatch) -> None:
    """一次移动只整表重建一次，且重排发出的是「纯顺序变化」信号（窗口不再级联重建）。"""
    page, _, _ = populated
    renders = 0
    original_render = page._render_rows

    def counting_render() -> None:
        nonlocal renders
        renders += 1
        original_render()

    monkeypatch.setattr(page, "_render_rows", counting_render)
    emissions: list[bool] = []
    page.people_changed.connect(emissions.append)

    page._table.selectRow(0)
    page.move_selected(1)

    assert renders == 1
    assert emissions == [False]


def test_structural_mutation_marks_people_changed_as_structural(populated, monkeypatch) -> None:
    """新增属于结构变化：信号 structure_changed=True，窗口据此刷新筛选轴与就绪快照。"""
    page, _, _ = populated
    emissions: list[bool] = []
    page.people_changed.connect(emissions.append)
    dialog_stub = type("D", (), {
        "exec": lambda self: 1,
        "values": lambda self: {"name": "赵六", "identity": "", "department": "", "note": ""},
    })()
    monkeypatch.setattr(
        "photo_archiver.presentation.views.people_admin_page.PersonEditDialog",
        lambda *a, **k: dialog_stub,
    )

    page._add_button.click()

    assert emissions == [True]
