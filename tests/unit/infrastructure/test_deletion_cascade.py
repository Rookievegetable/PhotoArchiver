"""ADR-034 删除级联矩阵测试（Phase E E-2）——真实 SQLite 是唯一裁判.

逐关系断言 schema 既有 ON DELETE 语义在仓储删除路径下真实生效：

- 删照片 → 识别结果 CASCADE 清空 + 归档记录 CASCADE 清空（D1）；
- 删人员 → 人脸嵌入 CASCADE 清空 + 识别结果归属 SET NULL + 照片保留（D2）；
- 文件夹删除 → 照片 SET NULL 保留（既有语义参照）；
- 幂等：remove 不存在 id 返回 0；批量混合存在/不存在部分删除；
- 磁盘文件不动由服务层不变量保证，本文件只锁库态。

InMemory 替身**有意不模拟级联**（ADR-034 §4.4）——因此本文件全部使用
真实 SQLite 仓储。
"""

from pathlib import Path
from uuid import uuid4

from photo_archiver.domain import (
    ArchiveRecord,
    ArchiveStatus,
    FaceEmbedding,
    Folder,
    MatchStatus,
    Person,
    PersonIdentity,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionResult,
)
from photo_archiver.infrastructure import (
    SQLiteArchiveRecordRepository,
    SQLiteConnectionProvider,
    SQLiteFaceEmbeddingRepository,
    SQLiteFolderRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRepository,
)


def create_provider(tmp_path: Path) -> SQLiteConnectionProvider:
    provider = SQLiteConnectionProvider(tmp_path / "cascade.sqlite3")
    provider.initialize_schema()
    return provider


def _add_person(provider, name: str = "张三"):
    repository = SQLitePersonRepository(provider)
    person = Person(name=name, identity=PersonIdentity(f"ID-{uuid4().hex[:8]}"))
    repository.add(person)
    return person


def _add_photo(provider, name: str, folder_id=None) -> Photo:
    repository = SQLitePhotoRepository(provider)
    photo = Photo(
        path=PhotoPath(raw_path=Path(f"/photos/{name}").resolve(), base=PhotoPathBase.ABSOLUTE),
        original_name=name,
        folder_id=folder_id,
    )
    repository.add(photo)
    return photo


def _add_recognition(provider, photo: Photo, person=None) -> RecognitionResult:
    repository = SQLiteRecognitionRepository(provider)
    result = RecognitionResult(
        photo_id=photo.id,
        person_id=person.id if person else None,
        status=MatchStatus.PENDING,
        confidence=0.88,
    )
    repository.add(result)
    return result


def _add_archive_record(provider, photo: Photo) -> ArchiveRecord:
    repository = SQLiteArchiveRecordRepository(provider)
    record = ArchiveRecord(
        photo_id=photo.id,
        target_archive_root="/archive",
        target_person_name="张三",
        target_event_or_date="2026-09",
        target_original_name=photo.original_name or "photo.jpg",
        status=ArchiveStatus.ARCHIVED,
    )
    repository.add(record)
    return record


def test_remove_photos_cascades_recognition_and_archive(
    tmp_path: Path,
) -> None:
    """D1：删照片 → 识别结果 + 归档记录级联清空（F1/F4 实证）。"""
    provider = create_provider(tmp_path)
    photo_repo = SQLitePhotoRepository(provider)
    recognition_repo = SQLiteRecognitionRepository(provider)
    archive_repo = SQLiteArchiveRecordRepository(provider)
    keep_photo = _add_photo(provider, "keep.jpg")
    remove_photo = _add_photo(provider, "remove.jpg")
    _add_recognition(provider, remove_photo)
    _add_recognition(provider, remove_photo, person=_add_person(provider))
    _add_recognition(provider, keep_photo)
    _add_archive_record(provider, remove_photo)
    _add_archive_record(provider, keep_photo)

    removed = photo_repo.remove([remove_photo.id, uuid4()])  # 混入不存在 id

    assert removed == 1  # 幂等：不存在 id 计 0
    assert photo_repo.find_by_id(remove_photo.id) is None
    assert photo_repo.find_by_id(keep_photo.id) is not None
    # 级联：remove_photo 的识别结果清空，keep 的保留
    assert recognition_repo.list_by_photo(remove_photo.id) == []
    assert len(recognition_repo.list_by_photo(keep_photo.id)) == 1
    # 级联：remove_photo 的归档记录清空，keep 的保留（归档产物文件不动属 D3 服务层不变量，本文件只锁库态）
    assert archive_repo.list_by_photo_ids([remove_photo.id]) == []
    assert len(archive_repo.list_by_photo_ids([keep_photo.id])) == 1


def test_remove_person_sets_recognition_null_and_cascades_embeddings(
    tmp_path: Path,
) -> None:
    """D2：删人员 → 嵌入清空 + 识别结果 SET NULL + 照片/归档保留（F2/F3）。"""
    provider = create_provider(tmp_path)
    person_repo = SQLitePersonRepository(provider)
    photo_repo = SQLitePhotoRepository(provider)
    recognition_repo = SQLiteRecognitionRepository(provider)
    embedding_repo = SQLiteFaceEmbeddingRepository(provider)

    person = _add_person(provider, "被删人员")
    photo = _add_photo(provider, "p.jpg")
    _add_recognition(provider, photo, person=person)
    embedding_repo.save(person.id, FaceEmbedding(vector=(0.1, 0.2, 0.3)))

    removed = person_repo.remove(person.id)

    assert removed == 1
    assert person_repo.find_by_id(person.id) is None
    assert embedding_repo.list_all() == {}  # 嵌入 CASCADE 清空（list_all 返回映射）
    after = recognition_repo.list_by_photo(photo.id)
    assert len(after) == 1  # 识别结果保留
    assert after[0].person_id is None  # 归属置空 → "未知人员"
    assert photo_repo.find_by_id(photo.id) is not None  # 照片保留


def test_remove_folder_sets_photos_folder_null(tmp_path: Path) -> None:
    """既有语义参照（F5）：删文件夹 → 照片保留且 folder_id 置空。"""
    provider = create_provider(tmp_path)
    folder_repo = SQLiteFolderRepository(provider)
    photo_repo = SQLitePhotoRepository(provider)

    folder = Folder(
        path=PhotoPath(raw_path=Path("/photos").resolve(), base=PhotoPathBase.ABSOLUTE),
        display_name="photos",
        total_photos=1,
        scanned_photos=1,
    )
    folder_repo.add(folder)
    photo = _add_photo(provider, "in_folder.jpg", folder_id=folder.id)
    assert photo.folder_id == folder.id

    # 直接走 SQL 删文件夹（folders 无仓储删除方法，属本 ADR 范围外）
    with provider.connect() as connection:
        connection.execute("DELETE FROM folders WHERE id = ?", (str(folder.id),))

    kept = photo_repo.find_by_id(photo.id)
    assert kept is not None
    assert kept.folder_id is None  # SET NULL


def test_remove_empty_ids_is_noop(tmp_path: Path) -> None:
    """幂等：空 id 列表 = no-op，返回 0。"""
    provider = create_provider(tmp_path)
    repository = SQLitePhotoRepository(provider)
    assert repository.remove([]) == 0
