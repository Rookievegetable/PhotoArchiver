"""Tests for Phase E E-3 deletion management services (ADR-034).

四个删除/对账用例的核心风险面是**预览计数与实际级联一致**（plan §5 测试
矩阵）与**防误删防护**（失联清理只删仍失联者、重复处置拒绝保留者/非重复
id）。真实 SQLite 是级联唯一裁判（E-2 先例延续）；磁盘文件不动（D3）由
服务零文件系统依赖结构性保证。
"""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from photo_archiver.application import (
    DeletePersonService,
    DeletePhotosService,
    DisposeDuplicatesService,
    PruneMissingPhotosService,
)
from photo_archiver.application.commands import (
    DeletePersonCommand,
    DeletePhotosCommand,
    DisposeDuplicatesCommand,
    PruneMissingCommand,
)
from photo_archiver.domain import (
    ArchiveRecord,
    ArchiveStatus,
    FaceEmbedding,
    MatchStatus,
    Person,
    PersonIdentity,
    Photo,
    PhotoMetadata,
    PhotoPath,
    PhotoPathBase,
    RecognitionResult,
)
from photo_archiver.infrastructure import (
    SQLiteArchiveRecordRepository,
    SQLiteConnectionProvider,
    SQLiteFaceEmbeddingRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRepository,
)


def create_provider(tmp_path: Path) -> SQLiteConnectionProvider:
    """Create and initialize a temporary SQLite database provider."""
    provider = SQLiteConnectionProvider(tmp_path / "deletion.sqlite3")
    provider.initialize_schema()
    return provider


def _add_photo(
    provider: SQLiteConnectionProvider,
    name: str,
    disk_path: Path | None = None,
    created_at: datetime | None = None,
) -> Photo:
    """Register a photo with an absolute path (no file is created)."""
    repository = SQLitePhotoRepository(provider)
    path = disk_path if disk_path is not None else Path(f"/photos/{name}").resolve()
    photo = Photo(
        path=PhotoPath(raw_path=path, base=PhotoPathBase.ABSOLUTE),
        original_name=name,
        created_at=created_at,
    )
    repository.add(photo)
    return photo


def _add_person(provider: SQLiteConnectionProvider, name: str = "张三") -> Person:
    """Register a person with a unique external identity."""
    repository = SQLitePersonRepository(provider)
    person = Person(name=name, identity=PersonIdentity(f"ID-{uuid4().hex[:8]}"))
    repository.add(person)
    return person


def _add_recognition(
    provider: SQLiteConnectionProvider,
    photo: Photo,
    person: Person | None = None,
) -> RecognitionResult:
    """Register one recognition result for the photo."""
    repository = SQLiteRecognitionRepository(provider)
    result = RecognitionResult(
        photo_id=photo.id,
        person_id=person.id if person else None,
        status=MatchStatus.PENDING,
        confidence=0.88,
    )
    repository.add(result)
    return result


def _add_archive_record(provider: SQLiteConnectionProvider, photo: Photo) -> ArchiveRecord:
    """Register one archived outcome for the photo."""
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


def _add_embedding(provider: SQLiteConnectionProvider, person: Person) -> None:
    """Persist one face embedding for the person."""
    repository = SQLiteFaceEmbeddingRepository(provider)
    repository.save(person.id, FaceEmbedding(vector=(0.1, 0.2, 0.3)))


def _build_delete_photos_service(provider: SQLiteConnectionProvider) -> DeletePhotosService:
    """Assemble DeletePhotosService over the real SQLite repositories."""
    return DeletePhotosService(
        SQLitePhotoRepository(provider),
        SQLiteRecognitionRepository(provider),
        SQLiteArchiveRecordRepository(provider),
    )


# ---- DeletePhotosService（D1：级联计数一致性 + 幂等）----


def test_delete_photos_preview_counts_cascades_and_missing(tmp_path: Path) -> None:
    """预览正确分离存在者与不存在者，并统计将级联的识别/归档行数。"""
    provider = create_provider(tmp_path)
    service = _build_delete_photos_service(provider)
    keep = _add_photo(provider, "keep.jpg")
    remove = _add_photo(provider, "remove.jpg")
    _add_recognition(provider, remove)
    _add_recognition(provider, remove, person=_add_person(provider))
    _add_archive_record(provider, remove)
    _add_recognition(provider, keep)  # 留者的识别不进预览计数
    ghost_id = uuid4()

    preview = service.preview([remove.id, ghost_id, remove.id])  # 重复 id 去重

    assert preview.photo_count == 1
    assert preview.photo_ids == (remove.id,)
    assert preview.missing_count == 1
    assert preview.missing_ids == (ghost_id,)
    assert preview.recognition_count == 2
    assert preview.archive_count == 1
    assert preview.cascade_count == 3
    assert preview.is_empty is False


def test_delete_photos_execute_matches_preview_and_cascades(tmp_path: Path) -> None:
    """执行结果与预览一致（plan §5）：删登记、级联清空、留者完整。"""
    provider = create_provider(tmp_path)
    service = _build_delete_photos_service(provider)
    photo_repo = SQLitePhotoRepository(provider)
    recognition_repo = SQLiteRecognitionRepository(provider)
    archive_repo = SQLiteArchiveRecordRepository(provider)
    keep = _add_photo(provider, "keep.jpg")
    remove = _add_photo(provider, "remove.jpg")
    _add_recognition(provider, remove)
    _add_recognition(provider, remove)
    _add_archive_record(provider, remove)
    _add_recognition(provider, keep)
    ghost_id = uuid4()

    preview = service.preview([remove.id, ghost_id])
    result = service.execute(DeletePhotosCommand(photo_ids=(remove.id, ghost_id)))

    assert result.requested == 2
    assert result.removed == 1
    assert result.missing == 1
    assert result.succeeded is True
    # 预览计数 == 实际级联（删除后行不可再查，预览快照即审计值）
    assert result.recognition_cascade == preview.recognition_count == 2
    assert result.archive_cascade == preview.archive_count == 1
    # 库态：remove 照片与其识别/归档清空，keep 完整保留
    assert photo_repo.find_by_id(remove.id) is None
    assert recognition_repo.list_by_photo(remove.id) == []
    assert archive_repo.list_by_photo_ids([remove.id]) == []
    assert photo_repo.find_by_id(keep.id) is not None
    assert len(recognition_repo.list_by_photo(keep.id)) == 1


def test_delete_photos_empty_and_repeat_are_idempotent(tmp_path: Path) -> None:
    """空命令 no-op；重复删除同一 id 幂等返回 0 行。"""
    provider = create_provider(tmp_path)
    service = _build_delete_photos_service(provider)
    photo = _add_photo(provider, "once.jpg")

    empty = service.execute(DeletePhotosCommand())
    first = service.execute(DeletePhotosCommand(photo_ids=(photo.id,)))
    second = service.execute(DeletePhotosCommand(photo_ids=(photo.id,)))

    assert empty.removed == 0 and empty.succeeded is True
    assert first.removed == 1
    assert second.removed == 0 and second.missing == 1 and second.succeeded is True


# ---- DeletePersonService（D2：照片保留 + 嵌入级联 + 识别置空）----


def _build_delete_person_service(provider: SQLiteConnectionProvider) -> DeletePersonService:
    """Assemble DeletePersonService over the real SQLite repositories."""
    return DeletePersonService(
        SQLitePersonRepository(provider),
        SQLitePhotoRepository(provider),
        SQLiteRecognitionRepository(provider),
        SQLiteFaceEmbeddingRepository(provider),
    )


def test_delete_person_preview_counts_embeddings_and_orphans(tmp_path: Path) -> None:
    """预览统计将级联删除的嵌入数与将归属置空的识别结果数。"""
    provider = create_provider(tmp_path)
    service = _build_delete_person_service(provider)
    person = _add_person(provider, "被删人员")
    stranger = _add_person(provider, "路人")
    photo_a = _add_photo(provider, "a.jpg")
    photo_b = _add_photo(provider, "b.jpg")
    _add_recognition(provider, photo_a, person=person)
    _add_recognition(provider, photo_b, person=person)
    _add_recognition(provider, photo_b, person=stranger)  # 他人识别不计数
    _add_embedding(provider, person)
    _add_embedding(provider, stranger)
    ghost_id = uuid4()

    preview = service.preview([person.id, ghost_id])

    assert preview.person_count == 1
    assert preview.missing_count == 1
    assert preview.embedding_count == 1  # 仅被删人员的嵌入
    assert preview.recognition_count == 2  # 仅被删人员的识别归属
    assert preview.is_empty is False


def test_delete_person_execute_orphans_recognition_and_keeps_photos(tmp_path: Path) -> None:
    """执行后：人员与嵌入消失、识别保留但归属置空、照片全部保留。"""
    provider = create_provider(tmp_path)
    service = _build_delete_person_service(provider)
    person_repo = SQLitePersonRepository(provider)
    embedding_repo = SQLiteFaceEmbeddingRepository(provider)
    recognition_repo = SQLiteRecognitionRepository(provider)
    photo_repo = SQLitePhotoRepository(provider)
    person = _add_person(provider, "被删人员")
    photo = _add_photo(provider, "p.jpg")
    _add_recognition(provider, photo, person=person)
    _add_embedding(provider, person)
    ghost_id = uuid4()

    result = service.execute(DeletePersonCommand(person_ids=(person.id, ghost_id)))

    assert result.requested == 2
    assert result.removed == 1
    assert result.missing == 1
    assert result.succeeded is True
    assert result.embedding_cascade == 1
    assert result.recognition_orphaned == 1
    assert person_repo.find_by_id(person.id) is None
    assert embedding_repo.list_all() == {}  # 嵌入 CASCADE 清空
    after = recognition_repo.list_by_photo(photo.id)
    assert len(after) == 1  # 识别结果行保留
    assert after[0].person_id is None  # 归属置空 → "未知人员"
    assert photo_repo.find_by_id(photo.id) is not None  # D2：照片全部保留


def test_delete_person_empty_command_is_noop(tmp_path: Path) -> None:
    """空命令 no-op——显式确认流防误触发。"""
    provider = create_provider(tmp_path)
    service = _build_delete_person_service(provider)

    result = service.execute(DeletePersonCommand())

    assert result.removed == 0 and result.succeeded is True


# ---- PruneMissingPhotosService（D5：失联清理 + 防误删）----


def _build_prune_service(
    provider: SQLiteConnectionProvider,
    photo_root: Path | None = None,
) -> PruneMissingPhotosService:
    """Assemble PruneMissingPhotosService with optional photo root."""
    return PruneMissingPhotosService(
        SQLitePhotoRepository(provider),
        photo_root=photo_root,
    )


def test_prune_preview_lists_missing_keeps_present(tmp_path: Path) -> None:
    """在盘照片不列；失联照片入预览并携带解析后的期望路径。"""
    provider = create_provider(tmp_path)
    present_file = tmp_path / "present.jpg"
    present_file.write_bytes(b"stub")
    _add_photo(provider, "present.jpg", disk_path=present_file)
    _add_photo(provider, "gone.jpg", disk_path=tmp_path / "gone.jpg")
    service = _build_prune_service(provider)

    preview = service.preview()

    assert preview.scanned == 2
    assert preview.missing_count == 1
    assert preview.items[0].disk_path == tmp_path / "gone.jpg"
    assert preview.unresolvable == 0
    assert preview.is_empty is False


def test_prune_preview_unresolvable_relative_paths_are_conservative(tmp_path: Path) -> None:
    """PHOTO_ROOT 相对路径：无根 → unresolvable 不入清单；有根 → 正常判定。"""
    provider = create_provider(tmp_path)
    photo_repo = SQLitePhotoRepository(provider)
    relative_photo = Photo(
        path=PhotoPath(raw_path=Path("school/event.jpg"), base=PhotoPathBase.PHOTO_ROOT),
        original_name="event.jpg",
    )
    photo_repo.add(relative_photo)

    without_root = _build_prune_service(provider, photo_root=None).preview()
    assert without_root.unresolvable == 1
    assert without_root.missing_count == 0  # 保守：无法解析者永不视为失联

    with_root = _build_prune_service(provider, photo_root=tmp_path).preview()
    assert with_root.unresolvable == 0
    assert with_root.missing_count == 1  # tmp_path/school/event.jpg 不存在 → 失联


def test_prune_execute_only_removes_still_missing_and_rejects_stale(tmp_path: Path) -> None:
    """确认的失联 id 被清理；预览后已恢复/非失联 id 被拒绝绝不误删。"""
    provider = create_provider(tmp_path)
    photo_repo = SQLitePhotoRepository(provider)
    gone = _add_photo(provider, "gone.jpg", disk_path=tmp_path / "gone.jpg")
    present = _add_photo(provider, "present.jpg", disk_path=tmp_path / "present.jpg")
    (tmp_path / "present.jpg").touch()  # 磁盘文件在盘 → 非失联
    service = _build_prune_service(provider)

    result = service.execute(PruneMissingCommand(photo_ids=(gone.id, present.id)))

    assert result.pruned == 1
    assert result.rejected == 1  # present 仍在盘 → 拒绝
    assert result.succeeded is True
    assert photo_repo.find_by_id(gone.id) is None  # 失联登记已清
    assert photo_repo.find_by_id(present.id) is not None  # 在册有效照片保留
    # 失联清理幂等：再次确认同一 id（已不在失联集合）被拒绝
    repeat = service.execute(PruneMissingCommand(photo_ids=(gone.id,)))
    assert repeat.pruned == 0 and repeat.rejected == 1


def test_prune_empty_command_is_noop(tmp_path: Path) -> None:
    """空命令 no-op——清理必须显式携带确认 id。"""
    provider = create_provider(tmp_path)
    service = _build_prune_service(provider)

    result = service.execute(PruneMissingCommand())

    assert result.pruned == 0 and result.succeeded is True


# ---- DisposeDuplicatesService（D6：保留最早注册 + 防误删）----


def _build_dispose_service(provider: SQLiteConnectionProvider) -> DisposeDuplicatesService:
    """Assemble DisposeDuplicatesService over the real SQLite repositories."""
    return DisposeDuplicatesService(
        SQLitePhotoRepository(provider),
        SQLiteRecognitionRepository(provider),
        SQLiteArchiveRecordRepository(provider),
    )


def _add_duplicate_group(
    provider: SQLiteConnectionProvider,
    names: tuple[str, ...],
    base_time: datetime,
) -> list[Photo]:
    """Register one duplicate group sharing a content hash."""
    photos = []
    for index, name in enumerate(names):
        photo = Photo(
            path=PhotoPath(raw_path=Path(f"/photos/{name}").resolve(), base=PhotoPathBase.ABSOLUTE),
            original_name=name,
            created_at=base_time.replace(second=index),
            metadata=PhotoMetadata(content_hash="dup-hash", modified_at=base_time),
        )
        SQLitePhotoRepository(provider).add(photo)
        photos.append(photo)
    return photos


def test_dispose_preview_keeps_earliest_registration(tmp_path: Path) -> None:
    """组内保留 created_at 最小者，建议删除集与其级联计数正确。"""
    provider = create_provider(tmp_path)
    base_time = datetime(2026, 9, 8, 12, 0, 0)
    first, second, third = _add_duplicate_group(provider, ("a.jpg", "b.jpg", "c.jpg"), base_time)
    _add_recognition(provider, second)
    _add_archive_record(provider, third)
    _add_photo(provider, "unique.jpg")  # 唯一照片不入组
    service = _build_dispose_service(provider)

    preview = service.preview()

    assert preview.group_count == 1
    group = preview.groups[0]
    assert group.content_hash == "dup-hash"
    assert group.keep_photo_id == first.id  # 最早注册者保留
    assert group.remove_photo_ids == (second.id, third.id)  # (created_at, id) 序
    assert group.recognition_count == 1  # 建议删除集的识别计数
    assert group.archive_count == 1
    assert preview.photo_count == 2


def test_dispose_preview_id_tiebreak_on_same_timestamp(tmp_path: Path) -> None:
    """同刻注册按 id 决胜——排序确定性与仓储返回序无关。"""
    provider = create_provider(tmp_path)
    base_time = datetime(2026, 9, 8, 12, 0, 0)
    photos = []
    for name in ("x.jpg", "y.jpg"):
        photo = Photo(
            path=PhotoPath(raw_path=Path(f"/photos/{name}").resolve(), base=PhotoPathBase.ABSOLUTE),
            original_name=name,
            created_at=base_time,
            metadata=PhotoMetadata(content_hash="tie-hash"),
        )
        SQLitePhotoRepository(provider).add(photo)
        photos.append(photo)
    service = _build_dispose_service(provider)

    group = service.preview().groups[0]
    expected_keep = min(photo.id for photo in photos)  # 同刻 → id 小者保留

    assert group.keep_photo_id == expected_keep


def test_dispose_execute_removes_proposal_and_protects_keepers(tmp_path: Path) -> None:
    """确认建议集 → 删登记；保留者/非重复 id 被拒绝且绝不误删。"""
    provider = create_provider(tmp_path)
    photo_repo = SQLitePhotoRepository(provider)
    base_time = datetime(2026, 9, 8, 12, 0, 0)
    keep, second, third = _add_duplicate_group(provider, ("a.jpg", "b.jpg", "c.jpg"), base_time)
    unique = _add_photo(provider, "unique.jpg")
    _add_recognition(provider, second)
    service = _build_dispose_service(provider)

    result = service.execute(
        DisposeDuplicatesCommand(photo_ids=(second.id, third.id, keep.id, unique.id))
    )

    assert result.removed == 2  # 仅建议删除集内的 id 被删
    assert result.rejected == 2  # keep.id + unique.id 被拒绝
    assert result.groups_affected == 1
    assert photo_repo.find_by_id(keep.id) is not None  # 保留者完好
    assert photo_repo.find_by_id(unique.id) is not None  # 非重复照片完好
    assert photo_repo.find_by_id(second.id) is None
    assert photo_repo.find_by_id(third.id) is None


def test_dispose_empty_command_is_noop(tmp_path: Path) -> None:
    """空命令 no-op——处置必须显式携带确认 id。"""
    provider = create_provider(tmp_path)
    service = _build_dispose_service(provider)

    result = service.execute(DisposeDuplicatesCommand())

    assert result.removed == 0 and result.groups_affected == 0




