"""Tests for PhotoRepository.search protocol contract (B2 搜索/筛选).

核验 SQLite 与 InMemory 双实现的筛选语义一致性（裁决已拍板：SQLite 走
SQL 下推、InMemory 走内存过滤，对照测试守护一致性）。

对照测试只用 captured_from/to 轴——person_id/match_status 两轴在 InMemory
仓储下不持 recognition_results（契约："无 recognition 结果的照片被
match_status 排除"返回空），故 SQLite/InMemory 对照在 captured 轴做。
SQLite 单测覆盖 match_status 轴的 WHERE 拼装正确性。
"""

from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest

from photo_archiver.domain import (
    MatchStatus,
    Photo,
    PhotoMetadata,
    PhotoPath,
    PhotoPathBase,
    PhotoRepository,
    PhotoSearchCriteria,
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


def _make_photo(name: str, captured_at: datetime | None) -> Photo:
    """Build a Photo with absolute path and captured_at."""
    return Photo(
        path=PhotoPath(raw_path=Path(f"/tmp/{name}").resolve(), base=PhotoPathBase.ABSOLUTE),
        folder_id=None,
        metadata=PhotoMetadata(
            content_hash=None,
            modified_at=datetime(2026, 8, 1),
            captured_at=captured_at,
        ),
        original_name=name,
        captured_at=captured_at,
    )


# ---- InMemory repository ----


def test_in_memory_empty_criteria_matches_all() -> None:
    """空 criteria（全 None）匹配所有照片——契约等价 list_all。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", datetime(2026, 7, 1)))
    repo.add(_make_photo("b", datetime(2026, 7, 15)))

    results = repo.search(PhotoSearchCriteria())

    assert len(results) == 2
    assert {p.original_name for p in results} == {"a", "b"}


def test_in_memory_captured_from_inclusive() -> None:
    """captured_from 区间下界闭——恰好 captured_at == from 的应命中。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("early", datetime(2026, 6, 30)))
    repo.add(_make_photo("boundary", datetime(2026, 7, 1)))
    repo.add(_make_photo("late", datetime(2026, 7, 15)))

    results = repo.search(PhotoSearchCriteria(captured_from=datetime(2026, 7, 1)))

    assert {p.original_name for p in results} == {"boundary", "late"}


def test_in_memory_captured_to_inclusive() -> None:
    """captured_to 区间上界闭——恰好 captured_at == to 的应命中。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("early", datetime(2026, 6, 30)))
    repo.add(_make_photo("boundary", datetime(2026, 7, 15)))
    repo.add(_make_photo("late", datetime(2026, 7, 20)))

    results = repo.search(PhotoSearchCriteria(captured_to=datetime(2026, 7, 15)))

    assert {p.original_name for p in results} == {"early", "boundary"}


def test_in_memory_captured_range_combined() -> None:
    """from+to 组合区间——两侧闭，区间内命中区间外排除。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("before", datetime(2026, 6, 30)))
    repo.add(_make_photo("in_low", datetime(2026, 7, 1)))
    repo.add(_make_photo("in_mid", datetime(2026, 7, 10)))
    repo.add(_make_photo("in_high", datetime(2026, 7, 15)))
    repo.add(_make_photo("after", datetime(2026, 7, 20)))

    results = repo.search(
        PhotoSearchCriteria(
            captured_from=datetime(2026, 7, 1),
            captured_to=datetime(2026, 7, 15),
        ),
    )

    assert {p.original_name for p in results} == {"in_low", "in_mid", "in_high"}


def test_in_memory_null_captured_at_excluded_from_date_filter() -> None:
    """NULL captured_at 的照片被日期轴默认排除（契约文档化）。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("has_date", datetime(2026, 7, 1)))
    repo.add(_make_photo("null_date", None))

    results = repo.search(PhotoSearchCriteria(captured_from=datetime(2026, 1, 1)))

    assert {p.original_name for p in results} == {"has_date"}


def test_in_memory_match_status_excludes_when_no_recognition() -> None:
    """InMemory 仓储不持 recognition_results，match_status 非空时返回空。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", datetime(2026, 7, 1)))

    results = repo.search(PhotoSearchCriteria(match_status=MatchStatus.APPROVED))

    assert results == []


def test_in_memory_results_ordered_by_created_at_then_id() -> None:
    """排序与 SQLite 实现对齐——created_at + id 稳稳定。

    显式设 created_at 区分两张——避免 Photo.__post_init__ 的 datetime.now()
    使排序预期不可控（b 后建 created_at 更大却排前致测试不稳）。
    """
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo_with_created("b", datetime(2026, 7, 15), datetime(2026, 7, 15)))
    repo.add(_make_photo_with_created("a", datetime(2026, 7, 1), datetime(2026, 7, 1)))

    results = repo.search(PhotoSearchCriteria())

    assert results[0].original_name == "a"
    assert results[1].original_name == "b"


def _make_photo_with_created(name: str, captured_at: datetime, created_at: datetime) -> Photo:
    """Build a Photo with explicit created_at for stable ordering tests."""
    from dataclasses import replace

    base = _make_photo(name, captured_at)
    return replace(base, created_at=created_at)


# ---- SQLite repository ----


@pytest.fixture()
def sqlite_repo(tmp_path: Path) -> SQLitePhotoRepository:
    """Provide a SQLite-backed photo repository on a fresh database."""
    provider = SQLiteConnectionProvider(tmp_path / "test.db")
    provider.initialize_schema()
    return SQLitePhotoRepository(provider)


def test_sqlite_empty_criteria_matches_all(sqlite_repo: SQLitePhotoRepository) -> None:
    """SQLite 空 criteria 匹配全——与 InMemory 一致。"""
    sqlite_repo.add(_make_photo("a", datetime(2026, 7, 1)))
    sqlite_repo.add(_make_photo("b", datetime(2026, 7, 15)))

    results = sqlite_repo.search(PhotoSearchCriteria())

    assert len(results) == 2
    assert {p.original_name for p in results} == {"a", "b"}


def test_sqlite_captured_from_to_inclusive(sqlite_repo: SQLitePhotoRepository) -> None:
    """SQLite 日期区间两侧闭——与 InMemory 一致。"""
    sqlite_repo.add(_make_photo("before", datetime(2026, 6, 30)))
    sqlite_repo.add(_make_photo("in_low", datetime(2026, 7, 1)))
    sqlite_repo.add(_make_photo("in_high", datetime(2026, 7, 15)))
    sqlite_repo.add(_make_photo("after", datetime(2026, 7, 20)))

    results = sqlite_repo.search(
        PhotoSearchCriteria(
            captured_from=datetime(2026, 7, 1),
            captured_to=datetime(2026, 7, 15),
        ),
    )

    assert {p.original_name for p in results} == {"in_low", "in_high"}


def test_sqlite_null_captured_at_excluded(sqlite_repo: SQLitePhotoRepository) -> None:
    """SQLite NULL captured_at 被 captured_at >= ? 掖除——与 InMemory 一致。"""
    sqlite_repo.add(_make_photo("has_date", datetime(2026, 7, 1)))
    sqlite_repo.add(_make_photo("null_date", None))

    results = sqlite_repo.search(PhotoSearchCriteria(captured_from=datetime(2026, 1, 1)))

    assert {p.original_name for p in results} == {"has_date"}


# ---- 对照测试：SQLite 与 InMemory 在 captured 轴产出相同 ----


def test_sqlite_and_in_memory_consistent_for_captured_range() -> None:
    """对照测试：SQLite 与 InMemory 在日期区间下产出相同结果集。

    混合：5 张照片（区间前/下界/中/上界/区间后）→ from+to 应命中 3 张。
    """
    photos = [
        _make_photo_with_created("before", datetime(2026, 6, 30), datetime(2026, 6, 30)),
        _make_photo_with_created("in_low", datetime(2026, 7, 1), datetime(2026, 7, 1)),
        _make_photo_with_created("in_mid", datetime(2026, 7, 10), datetime(2026, 7, 10)),
        _make_photo_with_created("in_high", datetime(2026, 7, 15), datetime(2026, 7, 15)),
        _make_photo_with_created("after", datetime(2026, 7, 20), datetime(2026, 7, 20)),
    ]

    in_memory = InMemoryPhotoRepository()
    for p in photos:
        in_memory.add(p)
    in_memory_results = in_memory.search(
        PhotoSearchCriteria(
            captured_from=datetime(2026, 7, 1),
            captured_to=datetime(2026, 7, 15),
        ),
    )

    # Windows 下 sqlite3 connection 锁文件：用显式 mkdtemp + gc + ignore_errors
    # rmtree 自管生命周期，避开竞速（同 B1 repository 测试约定）。
    import gc
    import shutil
    import tempfile
    import time

    tmp_dir = Path(tempfile.mkdtemp(prefix="photo_archiver_b2_"))
    try:
        provider = SQLiteConnectionProvider(tmp_dir / "consistency.db")
        provider.initialize_schema()
        sqlite = SQLitePhotoRepository(provider)
        for p in photos:
            sqlite.add(p)
        sqlite_results = sqlite.search(
            PhotoSearchCriteria(
                captured_from=datetime(2026, 7, 1),
                captured_to=datetime(2026, 7, 15),
            ),
        )
        del sqlite
        del provider
        gc.collect()
        time.sleep(0.05)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 双实现应同：3 张 in_low/in_mid/in_high，排序 created_at + id 一致
    assert [p.original_name for p in in_memory_results] == ["in_low", "in_mid", "in_high"]
    assert [p.original_name for p in sqlite_results] == ["in_low", "in_mid", "in_high"]


def test_photo_repository_protocol_accepts_search() -> None:
    """Protocol 契约：仓储替身可实现 search 而不破依赖。"""

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

        def search(self, criteria: PhotoSearchCriteria) -> list[Photo]:
            return []

        def list_duplicate_groups(self) -> list[list[Photo]]:
            return []

    repository: PhotoRepository = _MinimalRepo()  # type: ignore[assignment]
    assert repository.search(PhotoSearchCriteria()) == []


# ---- SQLite person 轴：approved-only 归属口径（UI-01，Owner 决策）----


def _person_axis_world(tmp_path: Path):
    """4 照片 × 甲/乙两人识别行：approved、pending 猜测、rejected、他人 approved。

    全部 approved 行 ``assignment_id IS NULL``——即 legacy 人工决策形态
    （归档口径 ``list_approved_by_person`` 的消费对象），验证同一口径。
    """
    from photo_archiver.app.repositories import build_sqlite_repositories
    from photo_archiver.domain import Person, RecognitionResult

    repos = build_sqlite_repositories(tmp_path / "ui01.sqlite3")
    person = Person(name="人员甲", roster_order=1)
    other = Person(name="人员乙", roster_order=2)
    repos.people.add(person)
    repos.people.add(other)

    def add_photo(name: str) -> Photo:
        photo = _make_photo(name, datetime(2026, 7, 1))
        repos.photos.add(photo)
        return photo

    approved = add_photo("approved")
    pending = add_photo("pending_guess")
    rejected = add_photo("rejected")
    other_photo = add_photo("other_person")

    approved_row = RecognitionResult(
        photo_id=approved.id, confidence=0.9, person_id=person.id,
    )
    approved_row.approve()  # legacy approved（assignment_id 保持 NULL）
    repos.recognition.add(approved_row)
    # matcher 猜测形态：pending 行携带猜测身份（审核预览候选）。
    repos.recognition.add(RecognitionResult(
        photo_id=pending.id, confidence=0.42, person_id=person.id,
    ))
    rejected_row = RecognitionResult(
        photo_id=rejected.id, confidence=0.5, person_id=person.id,
    )
    rejected_row.reject()
    repos.recognition.add(rejected_row)
    other_row = RecognitionResult(
        photo_id=other_photo.id, confidence=0.8, person_id=other.id,
    )
    other_row.approve()
    repos.recognition.add(other_row)
    return repos, person, other, approved, pending, rejected, other_photo


def test_sqlite_person_axis_returns_only_approved(tmp_path: Path) -> None:
    """人员轴只返回已批准归属：pending 猜测/rejected/他人照片全部排除。"""
    repos, person, _other, approved, _pending, _rejected, _other_photo = (
        _person_axis_world(tmp_path)
    )

    results = repos.photos.search(PhotoSearchCriteria(person_id=person.id))

    assert [p.original_name for p in results] == ["approved"]


def test_sqlite_person_axis_pending_guess_not_shown(tmp_path: Path) -> None:
    """待审核关联（猜测 person_id 的 pending 行）不进入人员查询结果。"""
    repos, person, _other, _approved, pending, _rejected, _other_photo = (
        _person_axis_world(tmp_path)
    )

    results = repos.photos.search(PhotoSearchCriteria(person_id=person.id))

    assert pending.id not in {p.id for p in results}
    # 与归档口径互证：pending 猜测行不在 list_approved_by_person，也不在照片轴。
    assert pending.id not in {
        r.photo_id for r in repos.recognition.list_approved_by_person(person.id)
    }


def test_sqlite_person_axis_plus_non_approved_status_is_empty(tmp_path: Path) -> None:
    """person + 非 approved match_status 组合恒空（同一 rr 行不可能双状态）。"""
    repos, person, _other, *_rest = _person_axis_world(tmp_path)

    assert repos.photos.search(PhotoSearchCriteria(
        person_id=person.id, match_status=MatchStatus.PENDING,
    )) == []


def test_sqlite_person_axis_ordering_unchanged(tmp_path: Path) -> None:
    """多张 approved 归属按 created_at, id 稳定排序（排序行为不回归）。"""
    from photo_archiver.app.repositories import build_sqlite_repositories
    from photo_archiver.domain import Person, RecognitionResult

    repos = build_sqlite_repositories(tmp_path / "ui01_order.sqlite3")
    person = Person(name="人员甲", roster_order=1)
    repos.people.add(person)
    photos = []
    for index, captured in enumerate(
        (datetime(2026, 7, 15), datetime(2026, 7, 1), datetime(2026, 7, 8)),
    ):
        photo = _make_photo_with_created(
            f"p{index}", captured, captured,
        )
        repos.photos.add(photo)
        row = RecognitionResult(
            photo_id=photo.id, confidence=0.9, person_id=person.id,
        )
        row.approve()
        repos.recognition.add(row)
        photos.append(photo)

    results = repos.photos.search(PhotoSearchCriteria(person_id=person.id))

    assert [p.original_name for p in results] == ["p1", "p2", "p0"]
