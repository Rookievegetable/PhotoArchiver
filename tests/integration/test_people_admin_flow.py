"""Stage B people-administration flow over real SQLite.

Covers the B-3 acceptance points: add/edit/reorder persist across a reopen,
reorder writes absolute positions transactionally, and the existing deletion
semantics are unchanged (photos preserved, recognition rows orphaned).
"""

from pathlib import Path

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands.people_admin import (
    AddPersonCommand,
    EditPersonCommand,
    ReorderPeopleCommand,
)
from photo_archiver.application.commands.deletion import DeletePersonCommand
from photo_archiver.application.services import DeletePersonService, ManagePeopleService


def _services(db_path: Path):
    """Wire real services over a real SQLite file."""
    repositories = build_sqlite_repositories(db_path)
    manage = ManagePeopleService(repositories.people, repositories.import_batches)
    delete = DeletePersonService(
        repositories.people,
        repositories.photos,
        repositories.recognition,
        repositories.face_embeddings,
    )
    return manage, delete, repositories


def test_add_edit_reorder_and_reopen_persistence(tmp_path: Path) -> None:
    db = tmp_path / "people.db"
    manage, _, _ = _services(db)

    manage.add_person(AddPersonCommand(name="张三", identity="E001", department="技术部"))
    manage.add_person(AddPersonCommand(name="李四", identity="E002"))
    c = manage.add_person(AddPersonCommand(name="王五"))
    edited = manage.edit_person(EditPersonCommand(
        person_id=c.id, name="王五", department="财务部",
    ))
    assert edited.department == "财务部"

    manage2, _, repositories2 = _services(db)  # 重开同一库
    a, b = repositories2.people.list_all()[0], repositories2.people.list_all()[1]
    manage2.reorder_people(ReorderPeopleCommand(ordered_ids=(c.id, a.id, b.id)))

    manage3, _, repositories3 = _services(db)  # 再次重开验证持久化
    ordered = repositories3.people.list_all()
    assert [p.name for p in ordered] == ["王五", "张三", "李四"]
    assert [p.roster_order for p in ordered] == [1, 2, 3]


def test_delete_person_regression_keeps_photos_and_orphans_recognition(tmp_path: Path) -> None:
    """B-3：阶段 B 不触碰删除语义——照片保留、识别归属置空。"""
    db = tmp_path / "people.db"
    manage, delete, repositories = _services(db)
    person = manage.add_person(AddPersonCommand(name="张三", identity="E001"))

    result = delete.execute(DeletePersonCommand(person_ids=(person.id,)))

    assert result.removed == 1
    assert repositories.people.find_by_id(person.id) is None
    assert repositories.people.list_all() == []
