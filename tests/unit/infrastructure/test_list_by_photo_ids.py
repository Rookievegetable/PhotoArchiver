"""Tests for the list_by_photo_ids repository contract (Phase 7 Commit 2).

核验 FILTERED 导出所需的批量照片轴查询（契约：
docs/health-check/PHASE_7_SCOPE_CONTRACT_REVISION.md §3/F4 / §6 Commit 2）：

- RecognitionRepository.list_by_photo_ids：返回这些照片的**全部**识别结果
  （任意 MatchStatus），区别于 list_first_by_photo_ids（每照片仅最早一条）
  与 list_by_photo（单照片）；排序 created_at, id；
- ArchiveRecordRepository.list_by_photo_ids：返回这些照片的**全部**归档记录
  （任意 ArchiveStatus），区别于 find_by_photo（单照片最新成功一条）；排序
  archived_at DESC, id DESC（NULL 最后，与 list_all 一致）；
- Protocol 默认实现 vs SQLite IN-clause 下推：同数据同输入（含重复 id、乱序）
  产出完全一致——对照测试，沿 test_photo_repository_search.py 双实现对照模式；
- 空集合：不打开连接直接返回空；批量：覆盖 >500（_SQLITE_PARAMETER_CHUNK）
  分块边界。

对照的双实现：SQLite 为生产实现；"默认实现"侧用最小测试替身（只实现默认
方法依赖的 list_by_photo / list_all）——替身继承 Protocol 默认实现本身，
这正是契约要保护的兼容面（add_many 先例）。Test-double boundary：替身仅是
默认实现的宿主，被测对象是两个 list_by_photo_ids 实现；What remains real：
真实 SQLite 仓储 + 真实 schema + 真实 domain 实体。

SQLite 测试数据按真实外键关系 seed：Folder → Photo（→ Person）→
recognition_results / archive_records——schema 对 photo_id / person_id 持
真实 FOREIGN KEY（alembic/versions/002_split_create_ddl.py :92-93/:119），
子行必须先有父行（FK-honest seeding，禁关闭 foreign_keys 绕过）。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from photo_archiver.domain import (
    ArchiveRecord,
    ArchiveStatus,
    Folder,
    MatchStatus,
    Person,
    Photo,
    PhotoPath,
    RecognitionResult,
    RecognitionRepository,
    ArchiveRecordRepository,
)
from photo_archiver.infrastructure.database.sqlite_archive_record_repository import (
    SQLiteArchiveRecordRepository,
)
from photo_archiver.infrastructure.database.sqlite_connection import (
    SQLiteConnectionProvider,
)
from photo_archiver.infrastructure.database.sqlite_folder_repository import (
    SQLiteFolderRepository,
)
from photo_archiver.infrastructure.database.sqlite_person_repository import (
    SQLitePersonRepository,
)
from photo_archiver.infrastructure.database.sqlite_photo_repository import (
    SQLitePhotoRepository,
)
from photo_archiver.infrastructure.database.sqlite_recognition_repository import (
    SQLiteRecognitionRepository,
)

_CHUNK_BOUNDARY_SIZE = 501  # _SQLITE_PARAMETER_CHUNK(500) + 1 → 恰跨一个分块


# ── Default-implementation hosts (minimal Protocol fakes) ────────────────────


class _DefaultLoopRecognitionRepository(RecognitionRepository):
    """Minimal repo exercising the Protocol-default list_by_photo_ids."""

    def __init__(self) -> None:
        self._results: list[RecognitionResult] = []

    def add(self, result: RecognitionResult) -> None:
        self._results.append(result)

    def list_by_photo(self, photo_id: UUID) -> list[RecognitionResult]:
        return [r for r in self._results if r.photo_id == photo_id]


class _DefaultFilterArchiveRepository(ArchiveRecordRepository):
    """Minimal repo exercising the Protocol-default list_by_photo_ids.

    list_all 实现遵守 Protocol 文档化的 recency 排序契约（archived_at DESC,
    id DESC，NULL 最后）——默认实现按 list_all 过滤，排序质量由此保证。
    """

    def __init__(self) -> None:
        self._records: list[ArchiveRecord] = []

    def add(self, record: ArchiveRecord) -> None:
        self._records.append(record)

    def list_all(self) -> list[ArchiveRecord]:
        return sorted(
            self._records,
            key=lambda r: (
                r.archived_at is not None,
                r.archived_at or datetime.min,
                r.id,
            ),
            reverse=True,
        )


# ── Builders ─────────────────────────────────────────────────────────────────


def _make_recognition(
    photo_id: UUID,
    person_id: UUID | None,
    status: MatchStatus,
    created_at: datetime,
) -> RecognitionResult:
    result = RecognitionResult(
        photo_id=photo_id,
        confidence=0.9,
        person_id=person_id,
        created_at=created_at,
    )
    if status is MatchStatus.APPROVED:
        result.approve()
    elif status is MatchStatus.REJECTED:
        result.reject()
    return result


def _make_archived_record(photo_id: UUID) -> ArchiveRecord:
    record = ArchiveRecord(
        photo_id=photo_id,
        target_archive_root="Z:/Archive",
        target_person_name="Carol",
        target_event_or_date="2026-08-30",
        target_original_name="x.jpg",
        status=ArchiveStatus.PLANNED,
    )
    record.mark_archived()
    return record


def _make_planned_record(photo_id: UUID) -> ArchiveRecord:
    return ArchiveRecord(
        photo_id=photo_id,
        target_archive_root="Z:/Archive",
        target_person_name="Carol",
        target_event_or_date="2026-08-30",
        target_original_name="x.jpg",
        status=ArchiveStatus.PLANNED,
    )


# ── SQLite stack（FK-honest seeding：Folder → Photo → Person → 子行）─────────


@dataclass
class _SQLiteStack:
    """Real repositories over one fresh SQLite database, plus FK-honest seeds.

    Schema 外键（002_split_create_ddl.py）：recognition_results.photo_id /
    archive_records.photo_id → photos(id)；recognition_results.person_id →
    people(id)；photos.folder_id → folders(id)。seed 顺序必须
    Folder → Photo（→ Person）→ 子行，禁关闭 foreign_keys 绕过。
    """

    folders: SQLiteFolderRepository
    photos: SQLitePhotoRepository
    people: SQLitePersonRepository
    recognition: SQLiteRecognitionRepository
    archive: SQLiteArchiveRecordRepository
    _folder: Folder | None = None

    def seed_photo(self) -> Photo:
        """Seed one (shared) Folder → Photo pair and return the Photo.

        A single folder is created lazily and reused for every photo in this
        stack: the ``folders`` table has a UNIQUE(raw_path, path_base)
        constraint (real schema), so each stack hosts one folder that holds
        many photos — the normal data shape. Every photo gets a unique path.
        """
        if self._folder is None:
            self._folder = Folder(path=PhotoPath("photos"), total_photos=1)
            self.folders.add(self._folder)
        photo = Photo(
            path=PhotoPath(f"photos/{uuid4().hex}.jpg"),
            folder_id=self._folder.id,
            original_name=uuid4().hex,
        )
        self.photos.add(photo)
        return photo

    def seed_person(self, name: str = "Carol") -> Person:
        """Seed one Person row (recognition_results.person_id FK parent)."""
        person = Person(name=name)
        self.people.add(person)
        return person


@pytest.fixture()
def stack(tmp_path: Path) -> _SQLiteStack:
    """Provide real repositories over one fresh SQLite database."""
    provider = SQLiteConnectionProvider(tmp_path / "test.db")
    provider.initialize_schema()
    return _SQLiteStack(
        folders=SQLiteFolderRepository(provider),
        photos=SQLitePhotoRepository(provider),
        people=SQLitePersonRepository(provider),
        recognition=SQLiteRecognitionRepository(provider),
        archive=SQLiteArchiveRecordRepository(provider),
    )



# ── RecognitionRepository.list_by_photo_ids ──────────────────────────────────


def test_recognition_sqlite_returns_all_statuses_for_photo_set(
    stack: _SQLiteStack,
) -> None:
    """按照片集合返回全部状态的结果（含 Pending），不漏不重。"""
    photo_a = stack.seed_photo()
    photo_b = stack.seed_photo()
    photo_c = stack.seed_photo()
    person = stack.seed_person("Carol")
    stack.recognition.add_many(
        [
            _make_recognition(photo_a.id, person.id, MatchStatus.PENDING, datetime(2026, 8, 1, 12, 0, 0)),
            _make_recognition(photo_a.id, person.id, MatchStatus.APPROVED, datetime(2026, 8, 1, 12, 0, 1)),
            _make_recognition(photo_b.id, person.id, MatchStatus.REJECTED, datetime(2026, 8, 1, 12, 0, 2)),
            _make_recognition(photo_c.id, person.id, MatchStatus.APPROVED, datetime(2026, 8, 1, 12, 0, 3)),
        ]
    )

    got = stack.recognition.list_by_photo_ids([photo_a.id, photo_b.id])

    # photo_a 的两条（全状态）+ photo_b 的一条；photo_c 不在集合内被排除
    assert [(r.photo_id, r.status) for r in got] == [
        (photo_a.id, MatchStatus.PENDING),
        (photo_a.id, MatchStatus.APPROVED),
        (photo_b.id, MatchStatus.REJECTED),
    ]


def test_recognition_single_photo_id_returns_only_that_photo(
    stack: _SQLiteStack,
) -> None:
    """单个 photo_id：仅返回该照片的结果。"""
    photo_a = stack.seed_photo()
    photo_b = stack.seed_photo()
    person = stack.seed_person()
    stack.recognition.add_many(
        [
            _make_recognition(photo_a.id, person.id, MatchStatus.APPROVED, datetime(2026, 8, 1, 12, 0, 0)),
            _make_recognition(photo_a.id, person.id, MatchStatus.PENDING, datetime(2026, 8, 1, 12, 0, 1)),
            _make_recognition(photo_b.id, person.id, MatchStatus.APPROVED, datetime(2026, 8, 1, 12, 0, 2)),
        ]
    )

    got = stack.recognition.list_by_photo_ids([photo_a.id])

    assert [(r.photo_id, r.status) for r in got] == [
        (photo_a.id, MatchStatus.APPROVED),
        (photo_a.id, MatchStatus.PENDING),
    ]


def test_recognition_nonexistent_photo_id_returns_empty(stack: _SQLiteStack) -> None:
    """不存在的 photo_id：返回空（库内有其他数据也不误返）。"""
    stack.seed_photo()
    stack.seed_person()

    assert stack.recognition.list_by_photo_ids([uuid4()]) == []


def test_recognition_default_and_sqlite_implementations_agree(
    stack: _SQLiteStack,
) -> None:
    """对照：默认实现（循环 list_by_photo + 全局排序）与 SQLite 下推产出一致。

    输入乱序 + 重复 id——两实现都必须按 IN 语义去重、按 created_at, id 全局
    排序，产出完全相同的列表。
    """
    photo_a = stack.seed_photo()
    photo_b = stack.seed_photo()
    photo_c = stack.seed_photo()
    person = stack.seed_person()
    results = [
        _make_recognition(photo_a.id, person.id, MatchStatus.PENDING, datetime(2026, 8, 1, 12, 0, 0)),
        _make_recognition(photo_a.id, person.id, MatchStatus.APPROVED, datetime(2026, 8, 1, 12, 0, 1)),
        _make_recognition(photo_b.id, person.id, MatchStatus.REJECTED, datetime(2026, 8, 1, 12, 0, 2)),
        _make_recognition(photo_c.id, person.id, MatchStatus.APPROVED, datetime(2026, 8, 1, 12, 0, 3)),
    ]
    default_repo = _DefaultLoopRecognitionRepository()
    for result in results:
        default_repo.add(result)
        stack.recognition.add(result)

    query = [photo_b.id, photo_a.id, photo_c.id, photo_b.id]  # 乱序 + 重复

    from_default = default_repo.list_by_photo_ids(query)
    from_sqlite = stack.recognition.list_by_photo_ids(query)

    assert [(r.photo_id, r.status, r.id) for r in from_default] == [
        (r.photo_id, r.status, r.id) for r in from_sqlite
    ]
    # 重复的 photo_b 不产生重复行（IN 语义）
    assert len(from_default) == 4
    # 全局排序：created_at 升序
    created_order = [r.created_at for r in from_default]
    assert created_order == sorted(created_order)


def test_recognition_empty_photo_ids_returns_empty(stack: _SQLiteStack) -> None:
    """空集合：两实现都直接返回空，不查询。"""
    default_repo = _DefaultLoopRecognitionRepository()

    assert default_repo.list_by_photo_ids([]) == []
    assert stack.recognition.list_by_photo_ids([]) == []


def test_recognition_chunk_boundary_beyond_500_photo_ids(
    stack: _SQLiteStack,
) -> None:
    """501 个 photo id（恰跨 500 参数分块边界）全量返回且排序稳定。"""
    base = datetime(2026, 8, 1, 12, 0, 0)
    folder = Folder(path=PhotoPath("photos"), total_photos=_CHUNK_BOUNDARY_SIZE)
    stack.folders.add(folder)
    results: list[RecognitionResult] = []
    for index in range(_CHUNK_BOUNDARY_SIZE):
        photo = Photo(
            path=PhotoPath(f"photos/{uuid4().hex}.jpg"),
            folder_id=folder.id,
            original_name=uuid4().hex,
        )
        stack.photos.add(photo)
        results.append(
            _make_recognition(
                photo.id, None, MatchStatus.APPROVED,
                created_at=base + timedelta(seconds=index),
            )
        )
    stack.recognition.add_many(results)

    shuffled_ids = [r.photo_id for r in reversed(results)]
    got = stack.recognition.list_by_photo_ids(shuffled_ids)

    assert len(got) == _CHUNK_BOUNDARY_SIZE
    # 跨分块后仍按 created_at, id 全局排序（首尾为时间最早/最晚的结果）
    assert got[0].created_at == base
    assert got[-1].created_at == base + timedelta(seconds=_CHUNK_BOUNDARY_SIZE - 1)



# ── ArchiveRecordRepository.list_by_photo_ids ────────────────────────────────


def test_archive_sqlite_returns_all_statuses_for_photo_set(
    stack: _SQLiteStack,
) -> None:
    """按照片集合返回全部状态的记录（ARCHIVED + PLANNED），NULL archived_at 最后。"""
    photo_a = stack.seed_photo()
    photo_b = stack.seed_photo()
    photo_c = stack.seed_photo()
    stack.archive.add(_make_archived_record(photo_a.id))
    stack.archive.add(_make_planned_record(photo_b.id))
    stack.archive.add(_make_archived_record(photo_c.id))

    got = stack.archive.list_by_photo_ids([photo_a.id, photo_b.id, photo_c.id])

    assert len(got) == 3
    # PLANNED（archived_at NULL）在 DESC 排序下位于最后——与 list_all 一致
    assert got[-1].photo_id == photo_b.id
    assert got[-1].status is ArchiveStatus.PLANNED
    assert {r.photo_id for r in got[:2]} == {photo_a.id, photo_c.id}
    assert all(r.status is ArchiveStatus.ARCHIVED for r in got[:2])


def test_archive_single_photo_id_returns_only_that_photo(
    stack: _SQLiteStack,
) -> None:
    """单个 photo_id：返回该照片的完整历史（多状态多条），不含他照片。"""
    photo_a = stack.seed_photo()
    photo_b = stack.seed_photo()
    stack.archive.add(_make_archived_record(photo_a.id))
    stack.archive.add(_make_planned_record(photo_a.id))
    stack.archive.add(_make_archived_record(photo_b.id))

    got = stack.archive.list_by_photo_ids([photo_a.id])

    assert len(got) == 2
    assert {r.photo_id for r in got} == {photo_a.id}
    assert {r.status for r in got} == {ArchiveStatus.ARCHIVED, ArchiveStatus.PLANNED}


def test_archive_nonexistent_photo_id_returns_empty(stack: _SQLiteStack) -> None:
    """不存在的 photo_id：返回空（库内有其他数据也不误返）。"""
    stack.seed_photo()

    assert stack.archive.list_by_photo_ids([uuid4()]) == []


def test_archive_default_and_sqlite_implementations_agree(
    stack: _SQLiteStack,
) -> None:
    """对照：默认实现（list_all 过滤）与 SQLite 下推产出完全一致。"""
    photo_a = stack.seed_photo()
    photo_b = stack.seed_photo()
    photo_c = stack.seed_photo()
    records = [
        _make_archived_record(photo_a.id),
        _make_planned_record(photo_b.id),
        _make_archived_record(photo_c.id),
    ]
    default_repo = _DefaultFilterArchiveRepository()
    for record in records:
        default_repo.add(record)
        stack.archive.add(record)

    query = [photo_c.id, photo_b.id, photo_a.id, photo_c.id]  # 乱序 + 重复

    from_default = default_repo.list_by_photo_ids(query)
    from_sqlite = stack.archive.list_by_photo_ids(query)

    assert [(r.photo_id, r.status, r.id) for r in from_default] == [
        (r.photo_id, r.status, r.id) for r in from_sqlite
    ]
    # 重复的 photo_c 不产生重复行（IN 语义）
    assert len(from_default) == 3


def test_archive_empty_photo_ids_returns_empty(stack: _SQLiteStack) -> None:
    """空集合：两实现都直接返回空，不查询。"""
    default_repo = _DefaultFilterArchiveRepository()

    assert default_repo.list_by_photo_ids([]) == []
    assert stack.archive.list_by_photo_ids([]) == []


def test_archive_chunk_boundary_beyond_500_photo_ids(
    stack: _SQLiteStack,
) -> None:
    """501 个 photo id（恰跨 500 参数分块边界）全量返回。"""
    folder = Folder(path=PhotoPath("photos"), total_photos=_CHUNK_BOUNDARY_SIZE)
    stack.folders.add(folder)
    photo_ids: list[UUID] = []
    for _ in range(_CHUNK_BOUNDARY_SIZE):
        photo = Photo(
            path=PhotoPath(f"photos/{uuid4().hex}.jpg"),
            folder_id=folder.id,
            original_name=uuid4().hex,
        )
        stack.photos.add(photo)
        photo_ids.append(photo.id)
        stack.archive.add(_make_planned_record(photo.id))

    got = stack.archive.list_by_photo_ids(list(reversed(photo_ids)))

    assert len(got) == _CHUNK_BOUNDARY_SIZE
    assert {r.photo_id for r in got} == set(photo_ids)


