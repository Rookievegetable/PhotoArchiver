"""按导入批次删除人员 / 清空全部人员 — 界面优化 §4.3 验收测试（真实 SQLite）.

覆盖：执行时点批次归属解析（merge 改写 source_batch_id 语义）、可选批次
记录+草稿清理（单事务）、级联计数与 preview() 同口径、其他批次人员与
照片全保留、批次记录默认保留。
"""

from datetime import datetime
from pathlib import Path

import pytest

from photo_archiver.application import DeletePersonService
from photo_archiver.application.commands.deletion import (
    ClearAllPeopleCommand,
    DeletePeopleByBatchCommand,
)
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.domain import (
    FaceEmbedding,
    ImportBatch,
    ImportDraftRow,
    Person,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionResult,
)


@pytest.fixture()
def repos(tmp_path: Path):
    return build_sqlite_repositories(tmp_path / "batch_delete.db")


def _service(repos) -> DeletePersonService:
    from photo_archiver.infrastructure.database.sqlite_unit_of_work import (
        SQLiteUnitOfWork,
    )

    return DeletePersonService(
        repos.people,
        repos.photos,
        repos.recognition,
        repos.face_embeddings,
        unit_of_work=SQLiteUnitOfWork(repos._connection_provider),  # noqa: SLF001
        import_batch_repository=repos.import_batches,
    )


def _batch(repos, file_name: str) -> ImportBatch:
    batch = ImportBatch(
        file_name=file_name, file_hash=f"hash-{file_name}", source_type="txt",
    )
    repos.import_batches.add_batch(batch)
    return batch


def _draft_rows(repos, batch_id, count: int) -> None:
    repos.import_batches.replace_draft_rows(batch_id, [
        ImportDraftRow(
            batch_id=batch_id, source_row=index, raw_values=[f"row-{index}"],
            parsed_name=f"草稿{index}", order_index=index,
        )
        for index in range(count)
    ])


def _person(repos, name: str, batch_id=None) -> Person:
    person = Person(name=name, source_batch_id=batch_id)
    repos.people.add(person)
    return person


def _photo(repos, name: str) -> Photo:
    photo = Photo(
        path=PhotoPath(Path.cwd() / "photos" / name, base=PhotoPathBase.ABSOLUTE),
        original_name=name,
        captured_at=datetime(2026, 1, 1),
    )
    repos.photos.add(photo)
    return photo


def _recognition_row(repos, photo_id, person_id) -> None:
    repos.recognition.add(RecognitionResult(
        photo_id=photo_id, person_id=person_id, confidence=0.5,
    ))


def test_preview_batch_lists_current_members_and_batch_record(repos):
    batch_a = _batch(repos, "名单A.txt")
    _draft_rows(repos, batch_a.id, 3)
    person_a = _person(repos, "张三", batch_a.id)
    _person(repos, "李四", None)  # 手工添加，不属于批次

    service = _service(repos)
    preview = service.preview_batch(batch_a.id)

    assert preview.person_count == 1
    assert preview.people_names == ("张三",)
    assert preview.person_ids == (person_a.id,)
    assert preview.batch_record_found is True
    assert preview.draft_row_count == 3


def test_execute_batch_removes_only_batch_members_keeps_batch_record(repos):
    batch_a = _batch(repos, "名单A.txt")
    batch_b = _batch(repos, "名单B.txt")
    person_a = _person(repos, "张三", batch_a.id)
    person_b = _person(repos, "李四", batch_b.id)
    photo = _photo(repos, "p.jpg")
    _recognition_row(repos, photo.id, person_a.id)
    repos.face_embeddings.save(person_a.id, FaceEmbedding((1.0, 0.0)))
    _draft_rows(repos, batch_a.id, 2)

    result = _service(repos).execute_batch(
        DeletePeopleByBatchCommand(batch_id=batch_a.id, delete_batch_record=False),
    )

    assert result.succeeded and result.removed == 1
    assert result.embedding_cascade == 1
    assert result.recognition_orphaned == 1
    assert result.batch_record_deleted == 0  # 默认保留批次记录
    assert result.draft_rows_deleted == 0
    # 其他批次人员与照片保留；识别行保留、归属置空。
    assert repos.people.find_by_id(person_b.id) is not None
    assert repos.photos.find_by_id(photo.id) is not None
    rows = repos.recognition.list_by_photo_ids([photo.id])
    assert len(rows) == 1 and rows[0].person_id is None
    assert repos.import_batches.get_batch(batch_a.id) is not None
    assert len(repos.import_batches.list_draft_rows(batch_a.id)) == 2


def test_execute_batch_with_record_cleanup_removes_batch_and_drafts(repos):
    batch_a = _batch(repos, "名单A.txt")
    _person(repos, "张三", batch_a.id)
    _draft_rows(repos, batch_a.id, 2)

    result = _service(repos).execute_batch(
        DeletePeopleByBatchCommand(batch_id=batch_a.id, delete_batch_record=True),
    )

    assert result.succeeded
    assert result.batch_record_deleted == 1
    assert result.draft_rows_deleted == 2
    assert repos.import_batches.get_batch(batch_a.id) is None
    assert repos.import_batches.list_draft_rows(batch_a.id) == []


def test_batch_membership_follows_current_source_batch_id_after_merge(repos):
    """合并会改写 source_batch_id——删除范围基于执行时点当前归属。"""
    batch_a = _batch(repos, "名单A.txt")
    batch_b = _batch(repos, "名单B.txt")
    person = _person(repos, "张三", batch_a.id)

    service = _service(repos)
    preview_before = service.preview_batch(batch_a.id)
    assert preview_before.person_count == 1

    # 模拟合并：人员归属改写到批次 B。
    person.source_batch_id = batch_b.id
    repos.people.add(person)

    assert service.preview_batch(batch_a.id).person_count == 0
    assert service.preview_batch(batch_b.id).people_names == ("张三",)


def test_execute_clear_all_removes_every_person_keeps_photos(repos):
    batch_a = _batch(repos, "名单A.txt")
    person_a = _person(repos, "张三", batch_a.id)
    person_b = _person(repos, "李四", None)
    photo = _photo(repos, "p.jpg")
    _recognition_row(repos, photo.id, person_a.id)
    _recognition_row(repos, photo.id, person_b.id)
    repos.face_embeddings.save(person_a.id, FaceEmbedding((1.0, 0.0)))
    repos.face_embeddings.save(person_b.id, FaceEmbedding((0.0, 1.0)))

    service = _service(repos)
    preview = service.preview_clear_all()
    assert preview.person_count == 2
    assert set(preview.people_names) == {"张三", "李四"}

    result = service.execute_clear_all(ClearAllPeopleCommand())

    assert result.succeeded and result.removed == 2
    assert result.embedding_cascade == 2
    assert result.recognition_orphaned == 2
    assert repos.people.list_all() == []
    # 照片与批次记录全部保留。
    assert repos.photos.find_by_id(photo.id) is not None
    assert repos.import_batches.get_batch(batch_a.id) is not None
    rows = repos.recognition.list_by_photo_ids([photo.id])
    assert len(rows) == 2 and all(row.person_id is None for row in rows)


def test_execute_batch_on_empty_batch_with_cleanup_still_clears_record(repos):
    """无当前成员的批次 + 勾选清理：人员零删除、批次记录与草稿照常清理。"""
    batch_a = _batch(repos, "空名单.txt")
    _draft_rows(repos, batch_a.id, 1)

    result = _service(repos).execute_batch(
        DeletePeopleByBatchCommand(batch_id=batch_a.id, delete_batch_record=True),
    )

    assert result.succeeded and result.removed == 0
    assert result.batch_record_deleted == 1
    assert result.draft_rows_deleted == 1
    assert repos.import_batches.get_batch(batch_a.id) is None
