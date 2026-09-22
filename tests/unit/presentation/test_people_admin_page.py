"""Stage B people page tests: rendering, edit surface, reorder, batch review.

The page is exercised over real SQLite services (like the stage-A preview
dialog tests); no modal is opened — edits and actions are driven directly.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands import AddPersonCommand
from photo_archiver.application.services import (
    DeletePersonService,
    ListPersonsService,
    ManagePeopleService,
)
from photo_archiver.presentation.views.people_admin_page import PeopleAdminPage


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
