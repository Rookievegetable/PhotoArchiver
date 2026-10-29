"""Stage B people page tests: rendering, edit surface, reorder, batch review.

The page is exercised over real SQLite services (like the stage-A preview
dialog tests); no modal is opened — edits and actions are driven directly.
The stage-B desktop review fixes have their own section at the end: row drops
must reorder through the real viewport receive path without leaving a blank
row, the danger dialog must arrive with the chosen person selected, and every
rejection must read in Chinese.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QItemSelectionModel, QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QMessageBox, QWidget

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands import AddPersonCommand
from photo_archiver.application.services import (
    ClusterResultsService,
    DeletePersonService,
    ListPersonsService,
    ListRecognitionRunsService,
    ManagePeopleService,
    RosterClusterStatsService,
)
from photo_archiver.domain import (
    FaceBox,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceEmbedding,
    FaceObservation,
    Person,
    RecognitionRun,
    RunPhotoSnapshot,
)
from photo_archiver.domain.entities.cluster_assignment import (
    ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
    ASSIGNMENT_STATUS_CONFIRMED,
    ClusterPersonAssignment,
)
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import (
    CARD_OBJECT_NAME,
    ROLE_DANGER,
    ROLE_PRIMARY,
    button_role,
)
from photo_archiver.presentation.views.people_admin_page import (
    PeopleAdminPage,
    derive_group_ordinals,
    format_group_ordinal,
)
from photo_archiver.presentation.views.person_deletion_dialog import (
    MultiPersonDeletionDialog,
    PersonDeletionDialog,
)


def _services(tmp_path: Path):
    repositories = build_sqlite_repositories(tmp_path / "page.db")
    manage = ManagePeopleService(repositories.people, repositories.import_batches)
    return (
        manage,
        ListPersonsService(repositories.people),
        DeletePersonService(
            repositories.people,
            repositories.photos,
            repositories.recognition,
            repositories.face_embeddings,
        ),
        ListRecognitionRunsService(repositories.recognition_runs),
        ClusterResultsService(
            repositories.recognition_runs,
            repositories.face_observations,
            repositories.face_clusters,
        ),
        RosterClusterStatsService(
            repositories.face_clusters,
            repositories.face_observations,
            repositories.cluster_assignments,
        ),
        repositories,
    )


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
        ListRecognitionRunsService(repositories.recognition_runs),
        ClusterResultsService(
            repositories.recognition_runs,
            repositories.face_observations,
            repositories.face_clusters,
        ),
        RosterClusterStatsService(
            repositories.face_clusters,
            repositories.face_observations,
            repositories.cluster_assignments,
        ),
    )
    qtbot.addWidget(page)
    return page, manage, repositories


def _import_batch_and_select(
    page, repositories, tmp_path: Path,
    rows: list[tuple[str, str | None]], tag: str = "a",
) -> str:
    """Import one batch roster (rows of ``(name, identity|None)``) and switch
    the page to its batch view.

    identity 冲突 → 合并（既有人员批次归属被改写为新批次）——用于构造跨批
    非连续成员。返回批次文件名。
    """
    from photo_archiver.application.commands import ConfirmImportCommand, ParseImportDraftCommand
    from photo_archiver.application.services import ConfirmImportService, ParseImportDraftService
    from photo_archiver.infrastructure.importers import FileRosterTableReader

    csv = tmp_path / f"batch_{tag}.csv"
    lines = ["姓名,工号"] + [
        name if identity is None else f"{name},{identity}"
        for name, identity in rows
    ]
    csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    parse = ParseImportDraftService(
        FileRosterTableReader(), repositories.import_batches, repositories.people,
    )
    confirm = ConfirmImportService(repositories.import_batches, repositories.people)
    draft = parse.execute(ParseImportDraftCommand(csv))
    confirm.execute(ConfirmImportCommand(draft.batch.id))
    page.refresh()
    index = page._batch_combo.findText(csv.name, flags=Qt.MatchFlag.MatchContains)
    assert index > 0
    page._batch_combo.setCurrentIndex(index)
    page._on_batch_selected(index)
    return csv.name


def test_page_renders_roster_in_order_with_columns(populated) -> None:
    page, _, _ = populated
    table = page._table
    assert table.rowCount() == 3
    names = [table.item(row, 3).text() for row in range(table.rowCount())]
    assert names == ["张三", "李四", "王五"]
    assert [table.item(row, 1).text() for row in range(3)] == ["1", "2", "3"]  # 顺序列
    assert [table.item(row, 2).text() for row in range(3)] == ["—", "—", "—"]  # 组/序：单组无前缀


def test_move_selected_persists_and_updates_positions(populated, tmp_path: Path) -> None:
    """批次视图调序（Owner 2026-10-28）：批次成员按新序置换其全局名次槽位。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("批张", "EA1"), ("批李", "EA2"), ("批王", "EA3"),
    ], tag="mv")
    page._table.selectRow(0)  # 批张（批次视图首位）
    page.move_selected(1)  # 批张下移
    names = [p.name for p in repositories.people.list_all()]
    assert names == ["张三", "李四", "王五", "批李", "批张", "批王"]
    assert [p.roster_order for p in repositories.people.list_all()] == [1, 2, 3, 4, 5, 6]


def test_drop_rows_reorders(populated, tmp_path: Path) -> None:
    """批次视图拖拽：_on_rows_dropped 与按钮同语义（置换）。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("批张", "EA1"), ("批李", "EA2"), ("批王", "EA3"),
    ], tag="drop")
    page._on_rows_dropped(2, 0)  # 批王拖到批次视图最前
    names = [p.name for p in repositories.people.list_all()]
    assert names == ["张三", "李四", "王五", "批王", "批张", "批李"]


def test_batch_review_switches_hint_and_gates(tmp_path: Path, populated, qtbot) -> None:
    """Owner 裁决（2026-10-28）：批次视图可调序（拖拽启用+调序提示）、
    全部批次只读（拖拽关闭+只读提示、移动按钮禁用）。"""
    page, manage, repositories = populated
    page.show()
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
    assert index > 0
    page._batch_combo.setCurrentIndex(index)
    page._on_batch_selected(index)
    assert page._table.rowCount() == 1  # 该批次带入 1 人（名单里的「张三 E001」是新建，不合并无工号的同名人员）
    assert page._table.item(0, 3).text() == "张三"
    assert page._table.item(0, 7).text() == "batch.csv"  # 来源批次列可见（组/序插入后右移）
    assert page._batch_hint.isVisible()
    assert page._batch_hint.text() == text.PEOPLE_PAGE_BATCH_FILTER_HINT  # 调序提示
    assert page._table.dragEnabled()  # 批次视图允许拖拽调序

    page._batch_combo.setCurrentIndex(0)
    page._on_batch_selected(0)
    assert page._table.rowCount() == 4
    assert page._batch_hint.text() == text.PEOPLE_PAGE_BATCH_READONLY_HINT  # 只读提示
    assert not page._table.dragEnabled()  # 全部批次禁止拖拽
    page._table.selectRow(0)
    assert not page._move_up_button.isEnabled()  # 全部批次：移动按钮禁用
    assert not page._move_down_button.isEnabled()


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
    manage_people, list_persons, delete_person, runs, results, _stats, _ = _services(tmp_path)
    page = PeopleAdminPage(manage_people, list_persons, delete_person, runs, results, _stats)
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
    return table.visualItemRect(table.item(row, 3)).center()


def test_table_keeps_row_drops_enabled_for_reordering(populated, tmp_path: Path) -> None:
    """验收 #2：批次视图拖拽模式必须真的接收落点（``DragOnly`` 会关掉 acceptDrops）。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("批张", "EA1"), ("批李", "EA2"), ("批王", "EA3"),
    ], tag="drops")
    table = page._table
    assert table.dragEnabled()
    assert table.acceptDrops()
    assert table.viewport().acceptDrops()


def test_row_drop_reorders_the_roster_without_a_blank_row(
    populated, tmp_path: Path, qtbot,
) -> None:
    """验收 #2：批次视图拖拽重排后目标行仍在——Qt 内部行移动曾把它删成空白行。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("批张", "EA1"), ("批李", "EA2"), ("批王", "EA3"),
    ], tag="drag")
    page.resize(900, 620)  # D-4 聚类区加入后页面更高：给表格稳定几何，避免拖拽落点漂移
    page.show()
    table = page._table
    source_point = _row_center(table, 2)  # 批王
    target_point = _row_center(table, 0)  # 拖到批次视图最前
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
    # 置换语义：批次成员填回其占有的名次槽位（4..6），其余批次人员不变
    assert [p.name for p in repositories.people.list_all()] == [
        "张三", "李四", "王五", "批王", "批张", "批李",
    ]
    assert [p.roster_order for p in repositories.people.list_all()] == [1, 2, 3, 4, 5, 6]
    assert table.rowCount() == 3
    assert [table.item(row, 3).text() for row in range(3)] == ["批王", "批张", "批李"]
    # 界面优化 §4.1：行内操作列已取消（编辑移至工具栏）。
    assert table.columnCount() == 9  # 复选框列（DEC-06 按图推翻）+ 8 业务列
    assert all(table.cellWidget(row, 6) is None for row in range(3))
    # 落点降级成功：Qt 不会动模型，被拖动的人在自己的新位置保持选中
    assert [index.row() for index in table.selectionModel().selectedRows()] == [0]


def test_move_only_drop_leaves_no_stale_selection(populated, tmp_path: Path) -> None:
    """落点无法降级为复制时，选区必须清空（内部移动就删不到任何行）。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("批张", "EA1"), ("批李", "EA2"), ("批王", "EA3"),
    ], tag="stale")
    page.resize(900, 620)  # D-4 聚类区加入后页面更高：给表格稳定几何，避免拖拽落点漂移
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
    assert [p.name for p in repositories.people.list_all()] == [
        "张三", "李四", "王五", "批王", "批张", "批李",
    ]
    assert table.rowCount() == 3
    assert not table.selectionModel().selectedRows()


def test_foreign_drag_payload_never_reorders_the_roster(populated) -> None:
    """验收 #2：外部拖拽载荷（文本等）不得被当作重排请求。"""
    page, _, repositories = populated
    page.resize(900, 620)  # D-4 聚类区加入后页面更高：给表格稳定几何，避免拖拽落点漂移
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


def test_all_batches_view_is_readonly(populated) -> None:
    """Owner 裁决（2026-10-28）：全部批次视图只读——拖拽关闭、移动按钮禁用、
    move_selected 第二道门 no-op、提示为只读文案。"""
    page, _, _ = populated
    page.show()
    assert page._batch_filter is None
    assert page._batch_hint.text() == text.PEOPLE_PAGE_BATCH_READONLY_HINT

    assert not page._table.dragEnabled()
    page._table.selectRow(0)
    assert page._edit_button.isEnabled()  # 编辑与顺序无关，仍可用
    assert not page._move_up_button.isEnabled()
    assert not page._move_down_button.isEnabled()

    page.move_selected(1)  # 第二道门：全部批次必须 no-op
    assert [p.name for p in page.visible_people()] == ["张三", "李四", "王五"]


def test_batch_view_permutation_keeps_other_batches_positions(
    populated, tmp_path: Path,
) -> None:
    """置换语义：批次成员只在本批次名次块内重排，其他批次人员的名次与
    相对位置完全不变（合并会把成员重排进批次块，块内置换即全部语义）。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("赵六", "EC1"),
    ], tag="p1")
    _import_batch_and_select(page, repositories, tmp_path, [
        ("钱七", "EC2"), ("孙八", "EC3"),
    ], tag="p2")
    page._batch_combo.setCurrentIndex(page._batch_combo.findText(
        "batch_p1.csv", flags=Qt.MatchFlag.MatchContains))
    page._on_batch_selected(page._batch_combo.currentIndex())
    assert [p.name for p in page.visible_people()] == ["赵六"]

    # 切到批次2（末位两人）并交换
    page._batch_combo.setCurrentIndex(page._batch_combo.findText(
        "batch_p2.csv", flags=Qt.MatchFlag.MatchContains))
    page._on_batch_selected(page._batch_combo.currentIndex())
    page._table.selectRow(0)  # 钱七
    page.move_selected(1)  # 钱七 与 孙八 交换

    names = [p.name for p in repositories.people.list_all()]
    assert names == ["张三", "李四", "王五", "赵六", "孙八", "钱七"]
    # 前四名（批次1 与无批次人员）名次完全不变
    assert [p.roster_order for p in repositories.people.list_all()][:4] == [1, 2, 3, 4]


def test_batch_review_disables_row_drops(populated) -> None:
    """全部批次只读：页面渲染即关闭拖拽，拖拽载荷一律不接受。"""
    page, _, _ = populated
    page.resize(900, 360)
    page.show()
    table = page._table
    assert not table.dragEnabled()  # 全部批次：_render_action_state 关闭拖拽
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
    manage, list_persons, delete_person, _, _, _, _ = _services(tmp_path)
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


def test_move_buttons_keep_the_person_selected_at_the_new_position(
    populated, tmp_path: Path,
) -> None:
    """复审追问：上移/下移后高亮必须跟着人走，不能留在原行号。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("批张", "EA1"), ("批李", "EA2"), ("批王", "EA3"),
    ], tag="sel")
    page._table.selectRow(0)  # 批张（批次视图首位）
    page._move_down_button.click()

    assert [p.name for p in repositories.people.list_all()] == [
        "张三", "李四", "王五", "批李", "批张", "批王",
    ]
    assert page._table.item(1, 3).text() == "批张"
    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [1]
    assert page._table.currentRow() == 1
    assert page._move_down_button.isEnabled()  # 行 1/3：仍可下移

    page._move_down_button.click()  # 批张 到批次视图末尾
    assert [p.name for p in repositories.people.list_all()] == [
        "张三", "李四", "王五", "批李", "批王", "批张",
    ]
    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [2]
    assert not page._move_down_button.isEnabled()  # 已到末尾：置灰而非静默无效

    page._move_up_button.click()  # 批张 回退一行
    assert [p.name for p in repositories.people.list_all()] == [
        "张三", "李四", "王五", "批李", "批张", "批王",
    ]
    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [1]
    assert page._move_up_button.isEnabled()

    page._move_up_button.click()  # 再退一行：批张 到批次视图开头
    assert [p.name for p in repositories.people.list_all()] == [
        "张三", "李四", "王五", "批张", "批李", "批王",
    ]
    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [0]
    assert page._table.item(0, 3).text() == "批张"
    assert not page._move_up_button.isEnabled()  # 已到开头


def test_repeated_move_clicks_move_the_same_person(populated, tmp_path: Path) -> None:
    """连续两次下移必须移动同一个人（旧行为第二次移动的是取而代之的那位）。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("批张", "EA1"), ("批李", "EA2"), ("批王", "EA3"),
    ], tag="rep")
    page._table.selectRow(0)  # 批张
    page._move_down_button.click()
    page._move_down_button.click()

    assert [p.name for p in repositories.people.list_all()] == [
        "张三", "李四", "王五", "批李", "批王", "批张",
    ]
    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [2]
    assert page._table.item(2, 3).text() == "批张"


def test_move_buttons_grey_out_at_the_roster_edges(populated, tmp_path: Path) -> None:
    """边界态（批次视图）：首行不能上移、末行不能下移、无选区两个都禁用；
    全部批次视图：即使有选区，移动按钮也一律禁用（只读）。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("批张", "EA1"), ("批李", "EA2"), ("批王", "EA3"),
    ], tag="edge")
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

    # 全部批次视图：只读——有选区也不启用移动
    page._batch_combo.setCurrentIndex(0)
    page._on_batch_selected(0)
    page._table.selectRow(1)
    assert not page._move_up_button.isEnabled()
    assert not page._move_down_button.isEnabled()


def test_selection_follows_the_person_across_refreshes(
    populated, tmp_path: Path,
) -> None:
    """任何重载（导入/删除/排序）后仍锁定同一个人，而不是同一个行号；
    批次筛选在刷新后保持，批次视图调序后选区跟随。"""
    page, manage, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("批王", "EA1"), ("批孙", "EA2"),
    ], tag="follow")
    page._table.selectRow(0)  # 批王（批次视图）
    manage.add_person(AddPersonCommand(name="赵六"))  # 名单变化（窗口会重载本页）
    page.refresh()

    # 批次筛选在刷新后保持：视图仍是本批次两人，选区跟随 批王
    assert [p.name for p in page.visible_people()] == ["批王", "批孙"]
    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [0]
    assert page._table.item(0, 3).text() == "批王"

    page.move_row(0, 1)  # 批次视图调序：批王 移到末位，选区跟随
    assert [index.row() for index in page._table.selectionModel().selectedRows()] == [1]
    assert page._table.item(1, 3).text() == "批王"


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


def test_move_renders_the_table_exactly_once(populated, tmp_path: Path, monkeypatch) -> None:
    """一次移动只整表重建一次，且重排发出的是「纯顺序变化」信号（窗口不再级联重建）。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("批张", "EA1"), ("批李", "EA2"),
    ], tag="render")
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


# ── D-4 聚类入口 ────────────────────────────────────────────────────────────


def _seed_recognition_run(repositories, *, captured=None, index=0):
    from photo_archiver.domain import Photo, PhotoPath, RecognitionRun, RunPhotoSnapshot
    photo = Photo(path=PhotoPath(f"photos/run-{index}-{uuid4()}.jpg"))
    repositories.photos.add(photo)
    run = RecognitionRun(parameters={}, created_at=captured or datetime(2026, 3, 1))
    repositories.recognition_runs.add_run(run)
    repositories.recognition_runs.add_run_photos(run.id, [
        RunPhotoSnapshot(run.id, photo.id, "photos/a.jpg", datetime(2026, 3, 1)),
    ])
    assert run.id is not None
    return run


def test_clustering_section_disabled_without_recognition_runs(tmp_path, qtbot) -> None:
    manage, list_persons, delete_person, runs, results, _stats, _ = _services(tmp_path)
    page = PeopleAdminPage(manage, list_persons, delete_person, runs, results, _stats)
    qtbot.addWidget(page)

    assert page._cluster_run_button.isEnabled() is False
    assert "尚无特征数据" in page._cluster_hint.text()
    assert page.selected_recognition_run_id() is None


def test_clustering_run_selector_populates_and_keeps_selection(tmp_path, qtbot) -> None:
    manage, list_persons, delete_person, runs, results, _stats, repositories = _services(tmp_path)
    page = PeopleAdminPage(manage, list_persons, delete_person, runs, results, _stats)
    qtbot.addWidget(page)
    run_a = _seed_recognition_run(repositories, captured=datetime(2026, 1, 1), index=1)
    run_b = _seed_recognition_run(repositories, captured=datetime(2026, 2, 1), index=2)
    page.refresh_clustering()

    assert page._cluster_run_combo.count() == 2
    assert page._cluster_run_button.isEnabled() is True
    assert page.selected_recognition_run_id() == run_b.id  # 默认选最新

    page._cluster_run_combo.setCurrentIndex(1)  # 用户选择：第 2 行（run_a）
    page.refresh_clustering()
    assert page.selected_recognition_run_id() == run_a.id  # 刷新保持当前选择


def test_clustering_results_button_needs_a_generation(tmp_path, qtbot) -> None:
    manage, list_persons, delete_person, runs, results, _stats, repositories = _services(tmp_path)
    page = PeopleAdminPage(manage, list_persons, delete_person, runs, results, _stats)
    qtbot.addWidget(page)
    run = _seed_recognition_run(repositories)

    page.refresh_clustering()
    assert page._cluster_results_button.isEnabled() is False  # 尚无聚类代

    from photo_archiver.domain import FaceClusterRun
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="v1")
    repositories.face_clusters.add_cluster_run(cluster_run)
    cluster_run.start()
    cluster_run.complete(1, 1, 0)
    page.refresh_clustering()
    assert page._cluster_results_button.isEnabled() is True


def test_clustering_buttons_emit_request_signals(tmp_path, qtbot) -> None:
    manage, list_persons, delete_person, runs, results, _stats, repositories = _services(tmp_path)
    page = PeopleAdminPage(manage, list_persons, delete_person, runs, results, _stats)
    qtbot.addWidget(page)
    run = _seed_recognition_run(repositories)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="v1")
    repositories.face_clusters.add_cluster_run(cluster_run)
    cluster_run.start()
    cluster_run.complete(1, 1, 0)
    page.refresh_clustering()
    assert page._cluster_run_button.isEnabled()
    assert page._cluster_results_button.isEnabled()
    runs_requested, results_requested = [], []
    page.cluster_run_requested.connect(lambda: runs_requested.append(1))
    page.cluster_results_requested.connect(lambda: results_requested.append(1))

    page._cluster_run_button.click()
    page._cluster_results_button.click()

    assert runs_requested == [1]
    assert results_requested == [1]


# ── 阶段 2 方案 a：「组/序」派生列 ───────────────────────────────────────────


def test_derive_group_ordinals_counts_jumps_as_group_boundaries() -> None:
    """跳变分组：序号链不再接续（前序+1）即开启新组（跳变处组号 +1）。"""
    names = ["1张三", "2李四", "3王五", "1赵六", "2钱七"]
    assert derive_group_ordinals(names) == [
        (1, 1), (1, 2), (1, 3), (2, 1), (2, 2),
    ]


def test_derive_group_ordinals_single_group_has_no_group_number() -> None:
    """仅一组（整条序号链无跳变）→ 组号全部为 None（显示「—」）。"""
    assert derive_group_ordinals(["1张三", "2李四", "3王五"]) == [
        (None, 1), (None, 2), (None, 3),
    ]


def test_derive_group_ordinals_without_prefix_degrades_to_none() -> None:
    """无数字前缀：序号 None；组链未开启前组号同为 None。"""
    assert derive_group_ordinals(["张三", "李四"]) == [(None, None), (None, None)]
    # 前缀非数字同样不匹配（^\d+ 降级为无前缀）。
    assert derive_group_ordinals(["a1张三", "2李四"]) == [(None, None), (None, 2)]


def test_derive_group_ordinals_prefixless_people_inherit_current_group() -> None:
    """无前缀者不参与链比较，继承当前组号；空名单返回空列表。"""
    assert derive_group_ordinals(["张三", "1李四", "2王五", "1赵六"]) == [
        (None, None), (1, 1), (1, 2), (2, 1),
    ]
    assert derive_group_ordinals([]) == []


def test_format_group_ordinal_renders_placeholder_for_none_parts() -> None:
    assert format_group_ordinal(2, 3) == "2/3"
    assert format_group_ordinal(1, None) == "1/—"
    assert format_group_ordinal(None, 2) == "—/2"
    assert format_group_ordinal(None, None) == "—"


def test_people_table_renders_group_ordinal_column(tmp_path: Path, qtbot) -> None:
    """页面渲染：新列在「顺序」之后，派生值/表头/派生依据 tooltip 正确。"""
    manage, list_persons, delete_person, runs, results, _stats, _ = _services(tmp_path)
    for name in ("1张三", "2李四", "1王五", "赵六"):
        manage.add_person(AddPersonCommand(name=name))
    page = PeopleAdminPage(manage, list_persons, delete_person, runs, results, _stats)
    qtbot.addWidget(page)

    table = page._table
    headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
    assert headers == [
        "",  # 复选框选择列（DEC-06 按图推翻；无表头文字）
        text.PEOPLE_PAGE_COL_ORDER,
        text.PEOPLE_PAGE_COL_GROUP_ORDINAL,
        text.PEOPLE_PAGE_COL_NAME,
        text.PEOPLE_PAGE_COL_IDENTITY,
        text.PEOPLE_PAGE_COL_DEPARTMENT,
        text.PEOPLE_PAGE_COL_NOTE,
        text.PEOPLE_PAGE_COL_BATCH,
        text.PEOPLE_PAGE_COL_MATCH_STATUS,
    ]
    # 1张三/2李四 → 第 1 组；1王五 → 第 2 组；赵六无前缀 → 序号「—」。
    assert [table.item(row, 2).text() for row in range(table.rowCount())] == [
        "1/1", "1/2", "2/1", "2/—",
    ]
    # 派生依据说明在该列 tooltip（其余列 tooltip 为单元格值本身）。
    assert table.item(0, 2).toolTip() == text.PEOPLE_PAGE_GROUP_ORDINAL_TOOLTIP
    assert table.item(0, 3).toolTip() == "1张三"


def test_group_ordinal_column_recomputes_after_reorder(populated, tmp_path: Path) -> None:
    """批次视图排序改 roster_order 后，组/序按新顺序自然重算（零持久化）；
    连续序号链收敛为单组时组号显示「—」。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("2批乙", "EB1"), ("1批甲", "EB2"),
    ], tag="grp")
    table = page._table
    # 批次视图（按导入序）：序号链 2→1 不接续 → 两个组
    assert [table.item(row, 2).text() for row in range(table.rowCount())] == [
        "1/2", "2/1",
    ]
    page.move_row(0, 1)  # 批次视图内交换：1批甲 移后 → 序号链 1→2 连续 → 单组
    assert [table.item(row, 3).text() for row in range(table.rowCount())] == [
        "1批甲", "2批乙",
    ]
    assert [table.item(row, 2).text() for row in range(table.rowCount())] == [
        "—/1", "—/2",
    ]


# ── P4：统计面板与行内匹配状态（锚点 = 最新代际；批次筛选不联动） ─────────────


_NEW_GEN_TIME = datetime(2026, 2, 1, 8, 0)
_OLD_GEN_TIME = datetime(2026, 1, 1, 8, 0)


class _StatsWorld:
    """Seed a run with photos/observations, generations and decisions."""

    def __init__(self, repositories) -> None:
        self.repos = repositories

    def add_person(self, name: str):
        person = Person(name=name)
        self.repos.people.add(person)
        return person

    def add_run(self, photo_count: int = 2, created_at: datetime | None = None):
        run = RecognitionRun(
            parameters={}, created_at=created_at or datetime(2026, 3, 1),
        )
        self.repos.recognition_runs.add_run(run)
        photos = []
        for index in range(photo_count):
            from photo_archiver.domain import Photo, PhotoPath

            photo = Photo(path=PhotoPath(f"photos/p{index}-{uuid4()}.jpg"))
            self.repos.photos.add(photo)
            self.repos.recognition_runs.add_run_photos(run.id, [
                RunPhotoSnapshot(
                    run.id, photo.id, f"photos/p{index}-{uuid4()}.jpg",
                    datetime(2026, 3, 1),
                ),
            ])
            photos.append(photo)
        return run, photos

    def add_observation(self, run, photo, index: int):
        observation = FaceObservation(
            run_id=run.id, photo_id=photo.id, face_index=index,
            photo_face_count=index + 1, det_score=0.9,
            box=FaceBox(index, 0, index + 10, 10),
            embedding=FaceEmbedding((1.0, 0.0)),
            scope_verdict="in_selected_scope",
        )
        self.repos.face_observations.add_many([observation])
        return observation

    def add_generation(self, run, member_groups, created_at: datetime):
        generation = FaceClusterRun(
            recognition_run_id=run.id, algorithm_version="v1", created_at=created_at,
        )
        self.repos.face_clusters.add_cluster_run(generation)
        clusters = []
        for ordinal, observations in enumerate(member_groups):
            cluster = FaceCluster(
                cluster_run_id=generation.id, run_id=run.id, ordinal=ordinal,
                member_count=len(observations), sort_key=f"cluster-{ordinal}",
                first_captured_at=datetime(2026, 3, 1),
            )
            self.repos.face_clusters.add_clusters([cluster])
            clusters.append(cluster)
            for observation in observations:
                self.repos.face_clusters.add_members([
                    FaceClusterMember(
                        cluster_id=cluster.id, observation_id=observation.id,
                    ),
                ])
        generation.start()
        generation.complete(len(clusters), sum(len(g) for g in member_groups), 0)
        return generation, clusters

    def add_decision(self, cluster, person, created_at=_NEW_GEN_TIME):
        decision = ClusterPersonAssignment(
            cluster_id=cluster.id, person_id=person.id,
            status=ASSIGNMENT_STATUS_CONFIRMED, created_at=created_at,
        )
        self.repos.cluster_assignments.add_assignments([decision])
        return decision


def _page_with_stats(tmp_path: Path, qtbot, names=("张三", "李四", "王五")):
    """Page wired to the stats service; returns (page, repositories, world)."""
    repositories = build_sqlite_repositories(tmp_path / "stats-page.db")
    manage = ManagePeopleService(repositories.people, repositories.import_batches)
    for name in names:
        manage.add_person(AddPersonCommand(name=name))
    stats = RosterClusterStatsService(
        repositories.face_clusters,
        repositories.face_observations,
        repositories.cluster_assignments,
    )
    page = PeopleAdminPage(
        manage,
        ListPersonsService(repositories.people),
        DeletePersonService(
            repositories.people,
            repositories.photos,
            repositories.recognition,
            repositories.face_embeddings,
        ),
        ListRecognitionRunsService(repositories.recognition_runs),
        ClusterResultsService(
            repositories.recognition_runs,
            repositories.face_observations,
            repositories.face_clusters,
        ),
        stats,
    )
    qtbot.addWidget(page)
    return page, repositories, _StatsWorld(repositories)


def _stats_texts(page) -> dict[str, str]:
    return {
        "anchor": page._stats_anchor_label.text(),
        "photo": page._stats_photo_label.text(),
        "face": page._stats_face_label.text(),
        "matched": page._stats_matched_label.text(),
        "unmatched": page._stats_unmatched_label.text(),
    }


def test_stats_panel_matches_direct_query(tmp_path: Path, qtbot) -> None:
    """验收①：面板四数字与仓储直查对拍一致（多代际 + 多决策）。"""
    page, repositories, world = _page_with_stats(tmp_path, qtbot)
    zhang = world.add_person("入册张三")  # roster 第 4 人
    run, photos = world.add_run(photo_count=2)
    o1 = world.add_observation(run, photos[0], 0)
    o2 = world.add_observation(run, photos[0], 1)  # 同照片第二张脸
    o3 = world.add_observation(run, photos[1], 0)
    world.add_generation(run, [[o1, o2, o3]], _OLD_GEN_TIME)  # 旧代际（无决策）
    new_gen, new_clusters = world.add_generation(run, [[o1, o3], [o2]], _NEW_GEN_TIME)
    world.add_decision(new_clusters[0], zhang)  # 仅锚点代际 1 人 active

    page.refresh_clustering()
    page.refresh()

    values = _stats_texts(page)
    # 直查 oracle：不经页面/用例代码重算同一口径。
    anchor = repositories.face_clusters.list_cluster_runs(run.id)[0]
    observations = {
        o.id: o for o in repositories.face_observations.list_by_run(run.id)
    }
    members = repositories.face_clusters.list_members(anchor.id)
    oracle_photos = len({
        observations[m.observation_id].photo_id for m in members
        if m.observation_id in observations
    })
    oracle_faces = len(members)
    oracle_matched = len({
        a.person_id
        for a in repositories.cluster_assignments.list_active_by_cluster_run(anchor.id)
        if a.person_id is not None
    })
    roster_total = len(repositories.people.list_all())

    assert anchor.id == new_gen.id  # 锚点 = 最新代际
    assert values["anchor"] == text.PEOPLE_PAGE_STATS_ANCHOR_LABEL.format(
        anchor=_NEW_GEN_TIME.strftime("%Y-%m-%d %H:%M"),
    )
    assert oracle_photos == 2  # o1/o2 同照片去重
    assert values["photo"] == text.PEOPLE_PAGE_STATS_PHOTO_COUNT.format(count=oracle_photos)
    assert oracle_faces == 3
    assert values["face"] == text.PEOPLE_PAGE_STATS_FACE_COUNT.format(count=oracle_faces)
    assert oracle_matched == 1
    assert values["matched"] == text.PEOPLE_PAGE_STATS_MATCHED_COUNT.format(
        count=oracle_matched,
    )
    assert roster_total == 4
    assert values["unmatched"] == text.PEOPLE_PAGE_STATS_UNMATCHED_COUNT.format(
        count=roster_total - oracle_matched,
    )


def test_stats_panel_ignores_batch_filter(tmp_path: Path, qtbot) -> None:
    """验收①：批次筛选不联动统计（数值不变，未匹配按全名单口径）。"""
    page, repositories, world = _page_with_stats(tmp_path, qtbot)
    zhang = world.add_person("批次张三")
    run, photos = world.add_run(photo_count=1)
    observation = world.add_observation(run, photos[0], 0)
    _, clusters = world.add_generation(run, [[observation]], _NEW_GEN_TIME)
    world.add_decision(clusters[0], zhang)

    page.refresh_clustering()
    page.refresh()

    from photo_archiver.application.commands import (
        ConfirmImportCommand,
        ParseImportDraftCommand,
    )
    from photo_archiver.application.services import (
        ConfirmImportService,
        ParseImportDraftService,
    )
    from photo_archiver.infrastructure.importers import FileRosterTableReader

    csv = tmp_path / "batch.csv"
    csv.write_text("姓名,工号\n王五,E009\n", encoding="utf-8")
    parse = ParseImportDraftService(
        FileRosterTableReader(), repositories.import_batches, repositories.people,
    )
    confirm = ConfirmImportService(repositories.import_batches, repositories.people)
    confirm.execute(ConfirmImportCommand(parse.execute(
        ParseImportDraftCommand(csv),
    ).batch.id))
    page.refresh()
    assert "batch.csv" in page._batch_combo.itemText(1)
    before = _stats_texts(page)  # 导入后的基线（roster 5 人）

    page._batch_combo.setCurrentIndex(1)
    page._on_batch_selected(1)
    assert page._table.rowCount() == 1  # 回看态只显示该批次人员

    after = _stats_texts(page)
    assert after == before  # 数值不变（不随筛选联动）
    assert after["unmatched"] == text.PEOPLE_PAGE_STATS_UNMATCHED_COUNT.format(count=4)
    # 口径标注常驻面板。
    assert text.PEOPLE_PAGE_STATS_CALIBER_NOTE in "".join(
        label.text() for label in page.findChildren(QLabel)
    )


def test_row_match_status_marks_follow_anchor_generation(
    tmp_path: Path, qtbot,
) -> None:
    """验收②：行内匹配状态按锚点代际判定；无代际时显示「—」。"""
    page, repositories, world = _page_with_stats(tmp_path, qtbot)
    zhang, li, wang = (world.add_person(n) for n in ("册上张三", "册上李四", "册上王五"))
    run, photos = world.add_run(photo_count=2)
    o1 = world.add_observation(run, photos[0], 0)
    o2 = world.add_observation(run, photos[1], 0)

    page.refresh_clustering()  # 选中 run 尚无代际
    page.refresh()
    assert [page._table.item(row, 8).text() for row in range(6)] == ["—"] * 6
    assert page._table.item(0, 8).toolTip() == text.PEOPLE_PAGE_MATCH_STATUS_TOOLTIP

    old_gen, old_clusters = world.add_generation(run, [[o1], [o2]], _OLD_GEN_TIME)
    world.add_decision(old_clusters[0], zhang, created_at=_OLD_GEN_TIME)
    world.add_decision(old_clusters[1], wang, created_at=_OLD_GEN_TIME)
    page.refresh()
    marks = {
        page._table.item(row, 3).text(): page._table.item(row, 8).text()
        for row in range(page._table.rowCount())
    }
    # 锚点 = 旧代际（当时最新）：张三/王五 已匹配。
    assert marks["册上张三"] == text.PEOPLE_PAGE_MATCH_STATUS_MARKED
    assert marks["册上王五"] == text.PEOPLE_PAGE_MATCH_STATUS_MARKED

    new_gen, new_clusters = world.add_generation(run, [[o1]], _NEW_GEN_TIME)
    world.add_decision(new_clusters[0], li)  # 仅李四在新（锚点）代际 active
    page.refresh()
    marks = {
        page._table.item(row, 3).text(): page._table.item(row, 8).text()
        for row in range(page._table.rowCount())
    }
    # 锚点切到最新代际：李四 已匹配；张三/王五只有旧代际决策 → 未匹配（D3-A）。
    assert marks["册上李四"] == text.PEOPLE_PAGE_MATCH_STATUS_MARKED
    assert marks["册上张三"] == text.PEOPLE_PAGE_MATCH_STATUS_UNMATCHED
    assert marks["册上王五"] == text.PEOPLE_PAGE_MATCH_STATUS_UNMATCHED
    assert marks["张三"] == text.PEOPLE_PAGE_MATCH_STATUS_UNMATCHED


def test_stats_panel_empty_states(tmp_path: Path, qtbot) -> None:
    """验收①：空名单 / 无 run / 无代际 → 面板空态文案（按该优先级）。"""
    page, repositories, world = _page_with_stats(tmp_path, qtbot, names=())
    page.refresh()
    assert page._stats_empty_label.text() == text.PEOPLE_PAGE_STATS_EMPTY_NO_ROSTER
    assert not page._stats_values.isVisible()

    # 名单非空后才进入「无 run」/「无代际」的空态分支。
    page._manage_people.add_person(AddPersonCommand(name="册上张三"))
    page.refresh()
    assert page._stats_empty_label.text() == text.PEOPLE_PAGE_STATS_EMPTY_NO_RUN

    run2, photos2 = world.add_run(photo_count=1)
    page.refresh_clustering()  # 默认选最新 run（run2），仍无代际
    page.refresh()
    assert page._stats_empty_label.text() == text.PEOPLE_PAGE_STATS_EMPTY_NO_GENERATION

    observation = world.add_observation(run2, photos2[0], 0)
    world.add_generation(run2, [[observation]], _NEW_GEN_TIME)
    page.refresh_clustering()
    page.refresh()
    assert page._stats_empty_label.isVisibleTo(page) is False
    assert page._stats_photo_label.text() == text.PEOPLE_PAGE_STATS_PHOTO_COUNT.format(count=1)
    assert page._stats_unmatched_label.text() == text.PEOPLE_PAGE_STATS_UNMATCHED_COUNT.format(count=1)


def test_stats_panel_follows_run_switch(tmp_path: Path, qtbot) -> None:
    """切换识别运行 → 锚点代际变化 → 统计联动重渲染。"""
    page, repositories, world = _page_with_stats(tmp_path, qtbot)
    zhang = world.add_person("切换张三")
    run_old, photos_old = world.add_run(
        photo_count=1, created_at=datetime(2026, 1, 1),
    )
    o_old = world.add_observation(run_old, photos_old[0], 0)
    world.add_generation(run_old, [[o_old]], _OLD_GEN_TIME)  # 1 簇 1 脸，无决策
    run_new, photos_new = world.add_run(
        photo_count=2, created_at=datetime(2026, 2, 1),
    )
    o_new1 = world.add_observation(run_new, photos_new[0], 0)
    o_new2 = world.add_observation(run_new, photos_new[1], 0)
    new_gen, new_clusters = world.add_generation(run_new, [[o_new1, o_new2]], _NEW_GEN_TIME)
    world.add_decision(new_clusters[0], zhang)

    page.refresh_clustering()
    page.refresh()
    assert page.selected_recognition_run_id() == run_new.id
    values = _stats_texts(page)
    assert values["face"] == text.PEOPLE_PAGE_STATS_FACE_COUNT.format(count=2)
    assert values["matched"] == text.PEOPLE_PAGE_STATS_MATCHED_COUNT.format(count=1)

    page._cluster_run_combo.setCurrentIndex(1)  # 用户切到旧 run
    page._on_cluster_run_changed(1)
    values = _stats_texts(page)
    assert values["face"] == text.PEOPLE_PAGE_STATS_FACE_COUNT.format(count=1)
    assert values["matched"] == text.PEOPLE_PAGE_STATS_MATCHED_COUNT.format(count=0)
    assert values["unmatched"] == text.PEOPLE_PAGE_STATS_UNMATCHED_COUNT.format(count=4)
    assert values["anchor"] == text.PEOPLE_PAGE_STATS_ANCHOR_LABEL.format(
        anchor=_OLD_GEN_TIME.strftime("%Y-%m-%d %H:%M"),
    )


# ── P11：人员多选最小版（删除所选 / 拖拽互斥 / 单选门控） ────────────────────


def _select_extra_row(page, row: int) -> None:
    """Extend the current selection by one more row (Ctrl+click semantics)."""
    model = page._table.selectionModel()
    model.select(
        model.model().index(row, 2),
        QItemSelectionModel.SelectionFlag.Select
        | QItemSelectionModel.SelectionFlag.Rows,
    )


def test_multi_selection_disables_drag_and_gates_buttons(
    populated, tmp_path: Path,
) -> None:
    """验收⑤：多选（>1）拖拽关闭；上移/下移/编辑仅恰选中 1 行可用。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("批张", "EA1"), ("批李", "EA2"), ("批王", "EA3"),
    ], tag="multi")
    page._table.selectRow(0)
    assert page._table.dragEnabled()  # 批次视图单选：拖拽可用
    assert page._move_up_button.isEnabled() is False  # 批次视图首行不能上移（原有规则）
    assert page._move_down_button.isEnabled()
    assert page._edit_button.isEnabled()

    _select_extra_row(page, 2)  # Ctrl+点击 → 2 行选中
    assert len(page._selected_row_indices()) == 2
    assert page._table.dragEnabled() is False  # 互斥规则：多选拖拽关闭
    assert page._move_up_button.isEnabled() is False
    assert page._move_down_button.isEnabled() is False
    assert page._edit_button.isEnabled() is False
    assert page._delete_button.isEnabled()  # 删除所选对多选可用

    page._table.clearSelection()
    assert page._delete_button.isEnabled() is False
    assert page._table.dragEnabled() is True  # 回到无选区（仍批次视图）：拖拽恢复


def test_move_selected_is_gated_to_single_selection(populated, tmp_path: Path) -> None:
    """P11：move_selected 仅在恰选中 1 行时执行（按钮禁用之外的第二道门）。"""
    page, _, repositories = populated
    _import_batch_and_select(page, repositories, tmp_path, [
        ("批张", "EA1"), ("批李", "EA2"), ("批王", "EA3"),
    ], tag="gate")
    page._table.selectRow(0)
    _select_extra_row(page, 2)
    page.move_selected(-1)  # 多选：必须 no-op

    assert [p.name for p in repositories.people.list_all()] == [
        "张三", "李四", "王五", "批张", "批李", "批王",
    ]

    page._table.clearSelection()
    page._table.selectRow(1)
    page.move_selected(-1)
    assert [p.name for p in repositories.people.list_all()] == [
        "张三", "李四", "王五", "批李", "批张", "批王",
    ]


def test_multi_select_delete_opens_preview_dialog_for_selected_people(
    populated, monkeypatch,
) -> None:
    """验收⑤：多选删除走批量预览对话框（复用 DeletePersonService.preview）。"""
    page, _, _ = populated
    captured: dict[str, object] = {}

    class _StubDialog:
        def __init__(self, people, delete_person, parent=None) -> None:
            captured["people"] = people
            captured["delete_person"] = delete_person
            captured["parent"] = parent

        def exec(self) -> int:
            return 0  # 取消：不得删除

        def last_message(self) -> str:
            return ""

    monkeypatch.setattr(
        "photo_archiver.presentation.views.people_admin_page.MultiPersonDeletionDialog",
        _StubDialog,
    )
    page._table.selectRow(0)
    _select_extra_row(page, 2)  # 张三 + 王五
    page._delete_button.click()

    selected: list[tuple] = captured["people"]  # type: ignore[assignment]
    assert [(str(pid), name) for pid, name in selected] == [
        (str(page.visible_people()[0].id), "张三"),
        (str(page.visible_people()[2].id), "王五"),
    ]
    assert captured["parent"] is page


def test_multi_person_deletion_dialog_previews_and_deletes_in_transaction(
    tmp_path: Path, qtbot,
) -> None:
    """验收⑤：构造 2 人删除 → 确认后两行消失，级联计数如实呈现。"""
    repositories = build_sqlite_repositories(tmp_path / "multi-del.db")
    manage = ManagePeopleService(repositories.people, repositories.import_batches)
    for name in ("张三", "李四", "王五"):
        manage.add_person(AddPersonCommand(name=name))
    delete_person = DeletePersonService(
        repositories.people,
        repositories.photos,
        repositories.recognition,
        repositories.face_embeddings,
        assignment_repository=repositories.cluster_assignments,
    )
    # 给 李四 造 1 条身份决策历史（预览/结果的级联计数应对拍为 1）。
    world = _StatsWorld(repositories)
    zhang, li, wang = repositories.people.list_all()
    run, photos = world.add_run(photo_count=1)
    observation = world.add_observation(run, photos[0], 0)
    generation, clusters = world.add_generation(run, [[observation]], _NEW_GEN_TIME)
    decision = ClusterPersonAssignment(
        cluster_id=clusters[0].id, person_id=li.id,
        status=ASSIGNMENT_STATUS_CONFIRMED,
        source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION, created_at=_NEW_GEN_TIME,
    )
    repositories.cluster_assignments.add_assignments([decision])

    preview = delete_person.preview([zhang.id, li.id])
    assert preview.person_count == 2
    assert preview.assignment_count == 1  # 李四的 1 条决策历史

    dialog = MultiPersonDeletionDialog(
        [(zhang.id, "张三"), (li.id, "李四")], delete_person,
    )
    qtbot.addWidget(dialog)
    impact = dialog._impact_label.text()
    assert "张三" in impact and "李四" in impact
    assert "1 条身份决策历史" in impact

    dialog._on_confirm()  # 事务执行（绕过模态 exec，与批次删除对话框测试同法）

    remaining = [p.name for p in repositories.people.list_all()]
    assert remaining == ["王五"]  # 两行消失
    assert repositories.cluster_assignments.count_by_person(li.id) == 0  # 决策级联
    assert "已删除 2 名人员" in dialog.last_message()
    assert "决策历史 1 条" in dialog.last_message()


# ── 阶段 3：统计卡组（P0-4 QFrame#Card）＋工具行分组 ─────────────────────────


def test_stats_panel_is_card_block_with_preserved_title_and_width(populated) -> None:
    """阶段 3 卡组化（P0-4 N4；决策项 #2 保守值）：统计面板外壳由 QGroupBox
    换为 QFrame#Card（style_card）；标题/口径说明文本不变（零新键、不加粗）、
    maxWidth(280) 与既有标签属性名全部保持。"""
    page, _, _ = populated
    cards = page.findChildren(QFrame, CARD_OBJECT_NAME)
    # 视觉对齐（2026-10-30 参考图基线）：统计卡＋人脸聚类区 Card（E1 容器化）
    # 共两处 Card；统计卡契约（maxWidth/属性名）零变化。
    assert len(cards) == 2
    card = next(c for c in cards if c.maximumWidth() == 280)  # 统计卡
    assert card.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    assert card.maximumWidth() == 280
    texts = {label.text() for label in card.findChildren(QLabel)}
    assert text.PEOPLE_PAGE_STATS_TITLE in texts
    assert text.PEOPLE_PAGE_STATS_CALIBER_NOTE in texts
    # 既有统计标签仍挂在卡组下（属性名零变化＝既有用例的访问面不变）；
    # 四数标签经 ``_stats_values`` 间接挂在卡组下（嵌套关系与原实现一致）。
    descendants = set(card.findChildren(QWidget))
    for attribute in (
        "_stats_anchor_label", "_stats_values", "_stats_photo_label",
        "_stats_face_label", "_stats_matched_label", "_stats_unmatched_label",
        "_stats_empty_label",
    ):
        assert getattr(page, attribute) in descendants


def test_stats_card_keeps_empty_state_visibility_semantics(
    tmp_path: Path, qtbot,
) -> None:
    """空态语义（F-PEO①）：四数区隐藏时卡组本身与口径说明仍常驻。"""
    page, _repositories, _world = _page_with_stats(tmp_path, qtbot, names=())
    card = page.findChild(QFrame, CARD_OBJECT_NAME)
    assert card is not None
    assert page._stats_empty_label.text() == text.PEOPLE_PAGE_STATS_EMPTY_NO_ROSTER
    assert page._stats_values.isVisibleTo(page) is False
    assert page._stats_empty_label.isVisibleTo(card) is True
    notes = [
        label for label in card.findChildren(QLabel)
        if label.text() == text.PEOPLE_PAGE_STATS_CALIBER_NOTE
    ]
    assert len(notes) == 1
    assert notes[0].isVisibleTo(card) is True


def test_toolbar_row_groups_preserve_order_and_roles(populated) -> None:
    """工具行分组＋B4「更多▾」收纳（决策项 #5 按图推翻 2026-10-30）：
    平铺按钮＝添加(primary)｜编辑/上移/下移(无角色)｜删除所选(danger)｜更多；
    按批次删除/清空所有人员收入「更多」菜单——按钮角色赋值零变化、菜单项
    触发既有按钮点击槽（处理器与确认对话框链零变化）。"""
    page, _, _ = populated
    toolbar = None
    for index in range(page.layout().count()):
        item = page.layout().itemAt(index)
        candidate = item.layout() if item is not None else None
        if candidate is not None and candidate.indexOf(page._add_button) >= 0:
            toolbar = candidate
            break
    assert toolbar is not None
    flat_buttons = (
        page._add_button, page._edit_button, page._move_up_button,
        page._move_down_button, page._delete_button,
    )
    roles = (ROLE_PRIMARY, None, None, None, ROLE_DANGER)
    indices = [toolbar.indexOf(button) for button in flat_buttons]
    assert indices == sorted(indices)  # 平铺按钮顺序不变
    for button, role in zip(flat_buttons, roles, strict=True):
        assert toolbar.indexOf(button) >= 0
        assert button_role(button) == role
    # 收纳：两个危险按钮不在工具栏布局中，但角色保持 danger 且可经菜单触达。
    assert toolbar.indexOf(page._delete_batch_button) == -1
    assert toolbar.indexOf(page._clear_all_button) == -1
    assert button_role(page._delete_batch_button) == ROLE_DANGER
    assert button_role(page._clear_all_button) == ROLE_DANGER
    menu = page._more_button.menu()
    actions = [action.text() for action in menu.actions()]
    assert text.PEOPLE_PAGE_DELETE_BATCH_BUTTON in actions
    assert text.PEOPLE_PAGE_CLEAR_ALL_BUTTON in actions
    spacers = [
        toolbar.itemAt(index) for index in range(toolbar.count())
        if toolbar.itemAt(index).spacerItem() is not None
    ]
    assert len(spacers) == 3  # 两组间距＋末尾 stretch




# ── 视觉对齐定向断言（参考图基线 2026-10-30；Owner 五项按图推翻）──────────


def test_people_page_header_and_icons_present(tmp_path: Path, qtbot) -> None:
    """A1/A2 页头＋DEC-10 按图推翻的工具栏图标（缺失字体优雅降级为纯文字）。"""
    from photo_archiver.presentation.visual_style import (
        PAGE_SUBTITLE_OBJECT_NAME, PAGE_TITLE_OBJECT_NAME,
    )

    manage, list_persons, delete_person, runs, results, _stats, _ = _services(tmp_path)
    page = PeopleAdminPage(manage, list_persons, delete_person, runs, results, _stats)
    qtbot.addWidget(page)

    title = page.findChild(QLabel, PAGE_TITLE_OBJECT_NAME)
    subtitle = page.findChild(QLabel, PAGE_SUBTITLE_OBJECT_NAME)
    assert title is not None and title.text() == text.PEOPLE_PAGE_TITLE
    assert subtitle is not None and subtitle.text() == text.PEOPLE_PAGE_SUBTITLE
    # 图标：五按钮挂 Fluent 图标（字体可用时非空 QIcon；缺失时为空 QIcon）。
    for button in (
        page._add_button, page._edit_button, page._move_up_button,
        page._move_down_button, page._delete_button,
    ):
        assert not button.icon().isNull() or button.text()  # 文字永在


def test_people_checkbox_column_mirrors_selection(tmp_path: Path, qtbot) -> None:
    """C1 复选框列（DEC-06 按图推翻）：勾选＝选中行；行选中镜像勾选态。"""
    from PySide6.QtCore import Qt

    manage, list_persons, delete_person, runs, results, _stats, _ = _services(tmp_path)
    for name in ("张三", "李四"):
        manage.add_person(AddPersonCommand(name=name))
    page = PeopleAdminPage(manage, list_persons, delete_person, runs, results, _stats)
    qtbot.addWidget(page)
    table = page._table
    assert table.columnCount() == 9

    # 勾选第 0 行复选框 → 该行进入选中集（「删除所选」语义源不变）。
    check_item = table.item(0, 0)
    check_item.setCheckState(Qt.CheckState.Checked)
    assert [index.row() for index in table.selectionModel().selectedRows()] == [0]
    # 行选中变化（程序化选择）→ 勾选态镜像。
    table.selectRow(1)
    assert table.item(0, 0).checkState() == Qt.CheckState.Unchecked
    assert table.item(1, 0).checkState() == Qt.CheckState.Checked
    # 取消勾选 → 行退出选中集。
    table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
    assert [index.row() for index in table.selectionModel().selectedRows()] == []


def test_people_clustering_section_is_card_with_danger_entries_in_place(
    tmp_path: Path, qtbot,
) -> None:
    """E1 聚类区 Card 化；D1-A 两个危险入口原位保留（F-PEO 保全）。"""
    from photo_archiver.presentation.visual_style import CARD_OBJECT_NAME, button_role
    from PySide6.QtWidgets import QPushButton

    manage, list_persons, delete_person, runs, results, _stats, _ = _services(tmp_path)
    page = PeopleAdminPage(manage, list_persons, delete_person, runs, results, _stats)
    qtbot.addWidget(page)
    cards = page.findChildren(QFrame, CARD_OBJECT_NAME)
    assert len(cards) == 2  # 统计卡 + 聚类区卡
    cluster_card = next(c for c in cards if c.maximumWidth() != 280)
    assert page._cluster_run_button in cluster_card.findChildren(QPushButton)
    assert page._delete_run_people_button in cluster_card.findChildren(QPushButton)
    assert page._delete_run_photos_button in cluster_card.findChildren(QPushButton)
    assert button_role(page._delete_run_people_button) == ROLE_DANGER
    assert button_role(page._delete_run_photos_button) == ROLE_DANGER
