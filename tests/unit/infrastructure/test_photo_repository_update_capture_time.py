"""Tests for PhotoRepository.update_capture_time (Phase F F-1, ADR-035).

Issue-019 后历史照片拍摄时刻回填的仓储侧契约：只更新 captured_at 列、
metadata 与 created_at 等列不动、幂等返回受影响行数。SQLite 与 InMemory
双实现一致（对照守护，与 update_metadata 同模式）。
"""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

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

NEW_CAPTURE = datetime(2024, 7, 13, 16, 42, 1)


def create_provider(tmp_path: Path) -> SQLiteConnectionProvider:
    """Create and initialize a temporary SQLite database provider."""
    provider = SQLiteConnectionProvider(tmp_path / "capture.sqlite3")
    provider.initialize_schema()
    return provider


def _photo(name: str = "a.jpg") -> Photo:
    """Build a photo with the legacy (mtime-pretender) captured_at and metadata."""
    return Photo(
        path=PhotoPath(raw_path=Path(f"/photos/{name}").resolve(), base=PhotoPathBase.ABSOLUTE),
        original_name=name,
        metadata=PhotoMetadata(width=800, height=600, file_size_bytes=1024),
        captured_at=datetime(2023, 1, 1, 0, 0, 0),  # 旧 reader 的 mtime 冒名值
    )


def test_sqlite_update_capture_time_updates_only_capture_column(tmp_path: Path) -> None:
    """SQLite：captured_at 刷新，metadata/created_at/original_name 不动。"""
    repository = SQLitePhotoRepository(create_provider(tmp_path))
    photo = _photo()
    repository.add(photo)
    original_metadata = photo.metadata
    original_created_at = photo.created_at

    updated = repository.update_capture_time(photo.id, NEW_CAPTURE)

    assert updated == 1
    refreshed = repository.find_by_id(photo.id)
    assert refreshed is not None
    assert refreshed.captured_at == NEW_CAPTURE  # 拍摄时刻已纠错
    assert refreshed.metadata == original_metadata  # metadata 列不动
    assert refreshed.created_at == original_created_at
    assert refreshed.original_name == "a.jpg"


def test_sqlite_update_capture_time_idempotent_missing_id(tmp_path: Path) -> None:
    """SQLite：不存在的 id 返回 0，不抛错。"""
    repository = SQLitePhotoRepository(create_provider(tmp_path))

    assert repository.update_capture_time(uuid4(), NEW_CAPTURE) == 0


def test_in_memory_update_capture_time_updates_only_capture_column() -> None:
    """InMemory：与 SQLite 语义一致——replace 仅替 captured_at 字段。"""
    repository = InMemoryPhotoRepository()
    photo = _photo()
    repository.add(photo)

    updated = repository.update_capture_time(photo.id, NEW_CAPTURE)

    assert updated == 1
    refreshed = repository.find_by_id(photo.id)
    assert refreshed is not None
    assert refreshed.captured_at == NEW_CAPTURE
    assert refreshed.metadata is not None
    assert refreshed.metadata.width == 800  # metadata 列不动


def test_in_memory_update_capture_time_idempotent_missing_id() -> None:
    """InMemory：不存在的 id 返回 0，不抛错。"""
    repository = InMemoryPhotoRepository()

    assert repository.update_capture_time(uuid4(), NEW_CAPTURE) == 0


def test_sqlite_and_in_memory_agree_on_capture_time_semantics(tmp_path: Path) -> None:
    """SQLite 与 InMemory 的 update_capture_time 语义一致（对照守护）。"""
    sqlite = SQLitePhotoRepository(create_provider(tmp_path))
    memory = InMemoryPhotoRepository()
    sqlite_photo, memory_photo = _photo("s.jpg"), _photo("m.jpg")
    sqlite.add(sqlite_photo)
    memory.add(memory_photo)

    assert sqlite.update_capture_time(sqlite_photo.id, NEW_CAPTURE) == memory.update_capture_time(
        memory_photo.id, NEW_CAPTURE
    ) == 1
    assert sqlite.find_by_id(sqlite_photo.id).captured_at == memory.find_by_id(
        memory_photo.id
    ).captured_at == NEW_CAPTURE