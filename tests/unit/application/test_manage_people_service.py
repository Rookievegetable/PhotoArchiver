"""ManagePeopleService unit tests (stage B of the people-import redesign).

Covers the roster administration rules with in-memory repositories: manual
add appends to the global roster order, identity uniqueness is enforced on
both add and edit, reorder validates ids and writes absolute positions, and
the roster view carries per-batch counts.
"""

from uuid import uuid4

import pytest

from photo_archiver.application.commands.people_admin import (
    AddPersonCommand,
    EditPersonCommand,
    ReorderPeopleCommand,
)
from photo_archiver.application.services import ManagePeopleService
from photo_archiver.domain.entities import ImportBatch
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.infrastructure import InMemoryPersonRepository


class _FakeImportBatches:
    """Minimal ImportBatchRepository stand-in for the roster query."""

    def __init__(self, batches=()):
        self._batches = list(batches)

    def list_batches(self):
        return list(self._batches)


def _service(batches=()) -> tuple[ManagePeopleService, InMemoryPersonRepository]:
    people = InMemoryPersonRepository()
    return ManagePeopleService(people, _FakeImportBatches(batches)), people


def test_add_person_appends_to_the_global_roster_order() -> None:
    service, people = _service()
    first = service.add_person(AddPersonCommand(name="张三", identity="E001", department="技术部"))
    second = service.add_person(AddPersonCommand(name="李四"))

    assert first.roster_order == 1
    assert second.roster_order == 2  # 全局续编（F-A1 裁决），不从 1 重起
    assert [p.name for p in people.list_all()] == ["张三", "李四"]


def test_add_person_rejects_duplicate_identity() -> None:
    service, _ = _service()
    service.add_person(AddPersonCommand(name="张三", identity="E001"))
    with pytest.raises(ValidationError, match="工号已被其他人员占用"):
        service.add_person(AddPersonCommand(name="李四", identity="E001"))


def test_add_person_rejects_empty_name() -> None:
    service, _ = _service()
    with pytest.raises(ValidationError, match="姓名不能为空"):
        service.add_person(AddPersonCommand(name="  "))


def test_empty_name_rejection_is_chinese_on_both_write_paths() -> None:
    """阶段 B 验收 #1：界面原文回显的校验消息必须是中文（不再出现英文原文）。"""
    service, _ = _service()
    person = service.add_person(AddPersonCommand(name="张三"))

    with pytest.raises(ValidationError) as added:
        service.add_person(AddPersonCommand(name=""))
    with pytest.raises(ValidationError) as edited:
        service.edit_person(EditPersonCommand(person_id=person.id, name="   "))

    assert str(added.value) == "姓名不能为空"
    assert str(edited.value) == "姓名不能为空"
    assert "must not be empty" not in str(added.value)
    assert "must not be empty" not in str(edited.value)


def test_edit_person_updates_fields_and_rejects_unknown_person() -> None:
    service, people = _service()
    person = service.add_person(AddPersonCommand(name="张三", identity="E001"))

    updated = service.edit_person(EditPersonCommand(
        person_id=person.id, name="张三", identity="E009", department="财务部", note="调任",
    ))
    assert updated.identity is not None and updated.identity.value == "E009"
    assert updated.department == "财务部"
    assert people.find_by_id(person.id).department == "财务部"

    with pytest.raises(ValidationError, match="人员不存在"):
        service.edit_person(EditPersonCommand(person_id=uuid4(), name="没人"))


def test_edit_person_identity_uniqueness_excludes_self() -> None:
    service, _ = _service()
    first = service.add_person(AddPersonCommand(name="张三", identity="E001"))
    second = service.add_person(AddPersonCommand(name="李四", identity="E002"))

    with pytest.raises(ValidationError, match="工号已被其他人员占用"):
        service.edit_person(EditPersonCommand(person_id=second.id, name="李四", identity="E001"))

    updated = service.edit_person(EditPersonCommand(person_id=first.id, name="张三", identity="E001"))
    assert updated.identity is not None and updated.identity.value == "E001"  # 自身放行


def test_reorder_people_writes_absolute_positions() -> None:
    service, people = _service()
    a = service.add_person(AddPersonCommand(name="张三"))
    b = service.add_person(AddPersonCommand(name="李四"))
    c = service.add_person(AddPersonCommand(name="王五"))

    updated = service.reorder_people(ReorderPeopleCommand(ordered_ids=(c.id, a.id, b.id)))
    assert updated == 3
    assert [p.name for p in people.list_all()] == ["王五", "张三", "李四"]
    assert [p.roster_order for p in people.list_all()] == [1, 2, 3]


def test_reorder_people_rejects_unknown_or_duplicate_ids() -> None:
    service, _ = _service()
    person = service.add_person(AddPersonCommand(name="张三"))

    with pytest.raises(ValidationError, match="重排序目标不存在"):
        service.reorder_people(ReorderPeopleCommand(ordered_ids=(person.id, uuid4())))
    with pytest.raises(ValidationError, match="重排序列表包含重复的人员"):
        service.reorder_people(ReorderPeopleCommand(ordered_ids=(person.id, person.id)))


def test_reorder_people_validates_with_a_single_roster_read(monkeypatch) -> None:
    """P0-1 回归：存在性校验一次 list_all 完成，不再逐 id find_by_id（每查开一次连接）。"""
    service, people = _service()
    a = service.add_person(AddPersonCommand(name="张三"))
    b = service.add_person(AddPersonCommand(name="李四"))
    calls = 0
    original_find = people.find_by_id

    def counting_find(person_id):
        nonlocal calls
        calls += 1
        return original_find(person_id)

    monkeypatch.setattr(people, "find_by_id", counting_find)

    updated = service.reorder_people(ReorderPeopleCommand(ordered_ids=(b.id, a.id)))

    assert updated == 2
    assert calls == 0
    assert [p.name for p in people.list_all()] == ["李四", "张三"]


def test_roster_counts_people_per_source_batch() -> None:
    batch = ImportBatch(file_name="roster.csv", file_hash="hash", source_type="csv")
    service, _ = _service(batches=[batch])
    inside = service.add_person(AddPersonCommand(name="张三"))
    inside.source_batch_id = batch.id
    service.edit_person(EditPersonCommand(person_id=inside.id, name="张三"))
    service.add_person(AddPersonCommand(name="李四"))  # 手工新增，无批次

    roster = service.roster()
    assert [p.name for p in roster.people] == ["张三", "李四"]
    assert len(roster.batches) == 1
    assert roster.batches[0].person_count == 1  # 李四不在批次计数内
