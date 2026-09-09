"""Tests for PhotoRepository.update_metadata (Phase E E-5, ADR-034 D5).

重扫对账的仓储侧契约：只更新 metadata 相关列、保留快照列（captured_at /
created_at / folder_id / path）、幂等返回受影响行数。SQLite 与 InMemory
双实现一致（对照守护，与 search/duplicate-groups 同模式）。
"""

from datetime import datetime
from pathlib import Path

from photo_archiver.domain import (
    Photo,
    PhotoMetadata,
    PhotoPath,
    PhotoPathBase,
)
from photo_archiver.infrastructure import (
    InMemoryPhotoRepository,
    SQLiteConnectionProvider,
    SQLitePhotoRepository,
)


def create_provider(tmp_path: Path) -> SQLiteConnectionProvider:
    """Create and initialize a temporary SQLite database provider."""
    provider = SQLiteConnectionProvider(tmp_path / "update_meta.sqlite3")
    provider.initialize_schema()
    return provider


def _photo(name: str = "a.jpg") -> Photo:
    """Build a photo with absolute path and fixed snapshot fields."""
    return Photo(
        path=PhotoPath(raw_path=Path(f"/photos/{name}").resolve(), base=PhotoPathBase.ABSOLUTE),
        original_name=name,
        captured_at=datetime(2024, 5, 1, 10, 0, 0),  # 快照列：不得被刷新覆盖
    )


def _new_metadata() -> PhotoMetadata:
    """Return fresh metadata reflecting a changed file."""
    return PhotoMetadata(
        width=1920,
        height=1080,
        file_size_bytes=2048,
        modified_at=datetime(2026, 9, 8, 12, 0, 0),
        content_hash="new-hash",
    )


def test_sqlite_update_metadata_refreshes_columns_and_preserves_snapshot(tmp_path: Path) -> None:
    """SQLite：metadata 五列刷新；captured_at/created_at/folder_id/path 保留。"""
    provider = create_provider(tmp_path)
    repository = SQLitePhotoRepository(provider)
    photo = _photo()
    repository.add(photo)

    updated = repository.update_metadata(photo.id, _new_metadata())

    assert updated == 1
    refreshed = repository.find_by_id(photo.id)
    assert refreshed is not None and refreshed.metadata is not None
    assert refreshed.metadata.width == 1920
    assert refreshed.metadata.content_hash == "new-hash"
    assert refreshed.metadata.modified_at == datetime(2026, 9, 8, 12, 0, 0)
    # 快照列保留（ISSUE-019 快照语义：已入库不回填拍摄时刻）
    assert refreshed.captured_at == datetime(2024, 5, 1, 10, 0, 0)
    assert refreshed.original_name == "a.jpg"
    assert refreshed.path == photo.path


def test_sqlite_update_metadata_idempotent_missing_id(tmp_path: Path) -> None:
    """SQLite：不存在的 id 返回 0，不抛错。"""
    provider = create_provider(tmp_path)
    repository = SQLitePhotoRepository(provider)
    from uuid import uuid4

    assert repository.update_metadata(uuid4(), _new_metadata()) == 0


def test_in_memory_update_metadata_refreshes_and_preserves_snapshot() -> None:
    """InMemory：与 SQLite 语义一致——replace 仅替 metadata 字段。"""
    repository = InMemoryPhotoRepository()
    photo = _photo()
    repository.add(photo)

    updated = repository.update_metadata(photo.id, _new_metadata())

    assert updated == 1
    refreshed = repository.find_by_id(photo.id)
    assert refreshed is not None
    assert refreshed.metadata is not None
    assert refreshed.metadata.content_hash == "new-hash"
    assert refreshed.captured_at == datetime(2024, 5, 1, 10, 0, 0)  # 快照保留
    assert refreshed.path == photo.path


def test_in_memory_update_metadata_idempotent_missing_id() -> None:
    """InMemory：不存在的 id 返回 0，不抛错。"""
    repository = InMemoryPhotoRepository()
    from uuid import uuid4

    assert repository.update_metadata(uuid4(), _new_metadata()) == 0


def test_sqlite_and_in_memory_agree_on_contract_semantics(tmp_path: Path) -> None:
    """SQLite 与 InMemory 的 update_metadata 语义一致（对照守护）。"""
    provider = create_provider(tmp_path)
    sqlite = SQLitePhotoRepository(provider)
    memory = InMemoryPhotoRepository()
    sqlite_photo = _photo("s.jpg")
    memory_photo = _photo("m.jpg")
    sqlite.add(sqlite_photo)
    memory.add(memory_photo)

    assert sqlite.update_metadata(sqlite_photo.id, _new_metadata()) == memory.update_metadata(
        memory_photo.id, _new_metadata()
    ) == 1
    assert sqlite.find_by_id(sqlite_photo.id).metadata.content_hash == memory.find_by_id(
        memory_photo.id
    ).metadata.content_hash == "new-hash"