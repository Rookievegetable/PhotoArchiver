"""Tests for PhotoRepository.list_duplicate_groups protocol contract (B1).

核验 SQLite 与 InMemory 双实现的查重语义一致性（B2-a 裁决已拍板：SQLite 走
SQL 下推、InMemory 走内存过滤，对照测试守护一致性）。

测试矩阵覆盖：
    - 全不重复 → 空列表
    - 全部重复（同一哈希 N 张）→ 1 组 N 张
    - 多组重复 → 组数与成员数
    - NULL 哈希的历史照片不参与分组
    - 单独哈希（仅 1 张）不构成组
"""

from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest

from photo_archiver.domain import (
    Photo,
    PhotoMetadata,
    PhotoPath,
    PhotoPathBase,
    PhotoRepository,
)
from photo_archiver.infrastructure.database.sqlite_connection import (
    SQLiteConnectionProvider,
)
from photo_archiver.infrastructure.database.sqlite_photo_repository import (
    SQLitePhotoRepository,
)
from photo_archiver.infrastructure.repositories.in_memory_photo_repository import (
    InMemoryPhotoRepository,
)


def _make_photo(name: str, content_hash: str | None) -> Photo:
    """Build a Photo with absolute path and optional content hash."""
    return Photo(
        path=PhotoPath(raw_path=Path(f"/tmp/{name}").resolve(), base=PhotoPathBase.ABSOLUTE),
        folder_id=None,
        metadata=PhotoMetadata(
            content_hash=content_hash,
            modified_at=datetime(2026, 8, 1),
            captured_at=datetime(2026, 8, 1),
        ),
        original_name=name,
        captured_at=datetime(2026, 8, 1),
    )


# ---- InMemory repository ----


def test_in_memory_no_duplicates_returns_empty() -> None:
    """全不重复照片产出空分组列表。"""
    repo = InMemoryPhotoRepository()
    for name in ("a", "b", "c"):
        repo.add(_make_photo(name, f"hash_{name}"))

    assert repo.list_duplicate_groups() == []


def test_in_memory_one_group_two_members() -> None:
    """两张同哈希照片归一组。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", "dup"))
    repo.add(_make_photo("b", "dup"))

    groups = repo.list_duplicate_groups()

    assert len(groups) == 1
    assert len(groups[0]) == 2
    assert {p.original_name for p in groups[0]} == {"a", "b"}


def test_in_memory_null_hash_excluded_from_groups() -> None:
    """NULL 哈希的历史照片不参与分组——契约与 B1-a 回填链路衔接。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", "dup"))
    repo.add(_make_photo("b", "dup"))
    repo.add(_make_photo("historic", None))

    groups = repo.list_duplicate_groups()

    assert len(groups) == 1
    assert len(groups[0]) == 2
    assert all("historic" != p.original_name for p in groups[0])


def test_in_memory_single_hash_not_a_group() -> None:
    """仅 1 张的哈希不构成组。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", "unique"))

    assert repo.list_duplicate_groups() == []


def test_in_memory_multiple_groups_sorted_by_desc_size() -> None:
    """多组按成员数降序——便于 DetectDuplicatesService 展示"最重复者先列"。"""
    repo = InMemoryPhotoRepository()
    for name in ("a", "b", "c"):
        repo.add(_make_photo(name, "hash_big"))  # 3 张
    for name in ("d", "e"):
        repo.add(_make_photo(name, "hash_small"))  # 2 张

    groups = repo.list_duplicate_groups()

    assert len(groups) == 2
    # InMemory 不保证组间顺序（dict 迭代），但成员数断言可守护语义
    sizes = sorted((len(g) for g in groups), reverse=True)
    assert sizes == [3, 2]


# ---- SQLite repository ----


@pytest.fixture()
def sqlite_repo(tmp_path: Path) -> SQLitePhotoRepository:
    """Provide a SQLite-backed photo repository on a fresh database."""
    provider = SQLiteConnectionProvider(tmp_path / "test.db")
    provider.initialize_schema()
    return SQLitePhotoRepository(provider)


def test_sqlite_no_duplicates_returns_empty(sqlite_repo: SQLitePhotoRepository) -> None:
    """SQLite 实现的"全不重复"返回空列表——与 InMemory 一致。"""
    sqlite_repo.add(_make_photo("a", "hash_a"))
    sqlite_repo.add(_make_photo("b", "hash_b"))

    assert sqlite_repo.list_duplicate_groups() == []


def test_sqlite_one_group_two_members(sqlite_repo: SQLitePhotoRepository) -> None:
    """SQLite 实现的"两同哈希"归一组——与 InMemory 一致。"""
    sqlite_repo.add(_make_photo("a", "dup"))
    sqlite_repo.add(_make_photo("b", "dup"))

    groups = sqlite_repo.list_duplicate_groups()

    assert len(groups) == 1
    assert len(groups[0]) == 2
    assert {p.original_name for p in groups[0]} == {"a", "b"}


def test_sqlite_null_hash_excluded(sqlite_repo: SQLitePhotoRepository) -> None:
    """SQLite 实现的 NULL 哈希排除——WHERE metadata_content_hash IS NOT NULL 守护。"""
    sqlite_repo.add(_make_photo("a", "dup"))
    sqlite_repo.add(_make_photo("b", "dup"))
    sqlite_repo.add(_make_photo("historic", None))

    groups = sqlite_repo.list_duplicate_groups()

    assert len(groups) == 1
    assert len(groups[0]) == 2
    assert all("historic" != p.original_name for p in groups[0])


def test_sqlite_and_in_memory_consistent_for_mixed_hashes() -> None:
    """对照测试：SQLite 与 InMemory 在混合场景下产出相同分组语义。

    混合：2 张同哈希 dup / 1 张单独 unique / 1 张 NULL 哈希 → 应仅 1 组 2 张。

    Windows 下 sqlite3 connection 锁 .db 文件：TemporaryDirectory 的 with 块退出
    即 unlink，但句柄有微秒释放延迟致 WinError 32。改用显式 mkdtemp + gc +
    ignore_errors rmtree 自管生命周期，避开竞态。
    """
    photos = [
        _make_photo("a", "dup"),
        _make_photo("b", "dup"),
        _make_photo("c", "unique"),
        _make_photo("historic", None),
    ]

    in_memory = InMemoryPhotoRepository()
    for p in photos:
        in_memory.add(p)
    in_memory_groups = in_memory.list_duplicate_groups()

    import gc
    import shutil
    import tempfile
    import time

    from pathlib import Path

    from photo_archiver.infrastructure.database.sqlite_connection import (
        SQLiteConnectionProvider,
    )

    tmp_dir = Path(tempfile.mkdtemp(prefix="photo_archiver_b1_"))
    try:
        provider = SQLiteConnectionProvider(tmp_dir / "consistency.db")
        provider.initialize_schema()
        sqlite = SQLitePhotoRepository(provider)
        for p in photos:
            sqlite.add(p)
        sqlite_groups = sqlite.list_duplicate_groups()
        # 显式释放底层 sqlite3 connection + 触发 GC，避免 Win 锁文件
        del sqlite
        del provider
        gc.collect()
        time.sleep(0.05)  # Windows 下 sqlite3 connection 释放有微秒延迟
    finally:
        # ignore_errors=True 兜底——Win 首次 unlink 失败时跳过而非炸测试
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 双实现应同：1 组 2 张 dup，c 与 historic 不在内
    assert len(in_memory_groups) == len(sqlite_groups) == 1
    assert len(in_memory_groups[0]) == len(sqlite_groups[0]) == 2
    assert {p.original_name for p in in_memory_groups[0]} == {"a", "b"}
    assert {p.original_name for p in sqlite_groups[0]} == {"a", "b"}


def test_photo_repository_protocol_accepts_list_duplicate_groups() -> None:
    """Protocol 契约：仓储替身可实现 list_duplicate_groups 而不破依赖。"""

    class _MinimalRepo:
        """Minimal stub satisfying the extended PhotoRepository protocol."""

        def add(self, photo: Photo) -> None:
            raise NotImplementedError

        def find_by_id(self, photo_id: UUID) -> Photo | None:
            raise NotImplementedError

        def find_by_path(self, path: PhotoPath) -> Photo | None:
            raise NotImplementedError

        def list_all(self) -> list[Photo]:
            raise NotImplementedError

        def list_by_folder_id(self, folder_id: UUID) -> list[Photo]:
            raise NotImplementedError

        def list_duplicate_groups(self) -> list[list[Photo]]:
            return []

    repository: PhotoRepository = _MinimalRepo()  # type: ignore[assignment]
    assert repository.list_duplicate_groups() == []
