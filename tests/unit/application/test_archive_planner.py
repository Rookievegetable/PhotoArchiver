"""Tests for ArchivePlanner — 裁决 #3 第一段：纯领域计算，零 IO 副作用.

用 in-memory fake repositories 隔离 SQLite / filesystem；planner 不碰文件系统，
所以测试无需 tmp_path。覆盖：
    approved 聚合 / 缺 captured_at 降级 / 跨 person 不串 /
    缺 photo 跳过 / 已 archived 跳过 / 相对路径 photo 跳过 / 空 person_ids 展开全部.
"""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from photo_archiver.application.services import ArchivePlanner
from photo_archiver.domain import (
    ArchiveStatus,
    Person,
    Photo,
    PhotoPath,
    PhotoPathBase,
)
from photo_archiver.domain.entities.archive import ArchiveRecord
from photo_archiver.domain.value_objects.archive_path import (
    UNKNOWN_EVENT_SEGMENT,
)


class _FakeArchivePathBuilder:
    """Drop-in ArchivePathBuilder stub returning a fixed-shape segment object.

    The planner only calls build() — we capture (person_name, captured_at,
    original_name) per photo and return a hand-rolled ArchivePath-like object
    so assertions can inspect what the planner passed without going through the
    real builder's date formatting.
    """

    def __init__(self) -> None:
        self.calls: list = []

    def build(self, archive_root, person_name, captured_at, original_name):
        from photo_archiver.domain import ArchivePath

        self.calls.append((person_name, captured_at, original_name))
        # captured_at None 时复用 unknown-date，与真实 builder 一致；测试可借此断言。
        event = captured_at.strftime("%Y-%m-%d") if captured_at else UNKNOWN_EVENT_SEGMENT
        return ArchivePath(
            archive_root=archive_root,
            person_name=person_name or "unknown-person",
            event_or_date=event,
            original_name=original_name,
        )


class _FakePersonRepository:
    def __init__(self, persons: list[Person]) -> None:
        self._persons = {p.id: p for p in persons}

    def find_by_id(self, person_id):
        return self._persons.get(person_id)

    def list_all(self) -> list[Person]:
        return list(self._persons.values())


class _FakePhotoRepository:
    def __init__(self, photos: list[Photo]) -> None:
        self._photos = {p.id: p for p in photos}

    def find_by_id(self, photo_id):
        return self._photos.get(photo_id)


class _FakeRecognitionRepository:
    def __init__(self, approved_by_person: dict) -> None:
        self._approved = approved_by_person  # person_id -> list[RecognitionResult]

    def list_approved_by_person(self, person_id):
        return list(self._approved.get(person_id, []))


class _FakeArchiveRecordRepository:
    def __init__(self, existing: dict | None = None) -> None:
        self._existing = existing or {}  # photo_id -> ArchiveRecord (past PLANNED)

    def find_by_photo(self, photo_id):
        return self._existing.get(photo_id)


def _make_recognition(photo_id, person_id) -> object:
    """Build a minimal APPROVED-shape object exposing photo_id/person_id."""
    from dataclasses import dataclass

    @dataclass
    class _R:
        photo_id: object
        person_id: object

    return _R(photo_id=photo_id, person_id=person_id)


def _absolute_photo(file_name: str = "x.jpg", captured_at: datetime | None = None, tmp_path: Path | None = None) -> Photo:
    """Build a Photo with an absolute path.

    On Windows, ``Path("/src/x.jpg")`` is NOT absolute (absolute requires a drive
    letter or UNC root). Callers pass ``tmp_path`` to materialize a real absolute
    path under the test's temp directory. When ``tmp_path`` is None we fall back
    to the cwd-based absolute form so the photo's ``is_absolute`` check passes.
    """
    if tmp_path is not None:
        absolute = tmp_path / file_name
    else:
        absolute = Path.cwd() / "src" / file_name
    return Photo(
        path=PhotoPath(absolute, base=PhotoPathBase.ABSOLUTE),
        original_name=file_name,
        captured_at=captured_at,
    )


def test_plan_gathers_approved_photos_per_person() -> None:
    """plan() returns one ArchivePlanItem per APPROVED recognition."""
    person = Person(name="Alice")
    photo = _absolute_photo("a.jpg", captured_at=datetime(2024, 5, 1))
    recognition = _make_recognition(photo.id, person.id)
    planner = ArchivePlanner(
        path_builder=_FakeArchivePathBuilder(),
        person_repository=_FakePersonRepository([person]),
        photo_repository=_FakePhotoRepository([photo]),
        recognition_repository=_FakeRecognitionRepository({person.id: [recognition]}),
        archive_record_repository=_FakeArchiveRecordRepository(),
    )
    plan = planner.plan("/archive", ())
    assert plan.planned_count == 1
    assert plan.skipped_count == 0
    assert plan.items[0].photo_id == photo.id
    assert plan.items[0].person_name == "Alice"


def test_plan_falls_back_to_unknown_date_when_captured_at_none() -> None:
    """Photo without captured_at still plans, with the unknown-date segment."""
    person = Person(name="Alice")
    photo = _absolute_photo("a.jpg", captured_at=None)
    recognition = _make_recognition(photo.id, person.id)
    builder = _FakeArchivePathBuilder()
    planner = ArchivePlanner(
        path_builder=builder,
        person_repository=_FakePersonRepository([person]),
        photo_repository=_FakePhotoRepository([photo]),
        recognition_repository=_FakeRecognitionRepository({person.id: [recognition]}),
        archive_record_repository=_FakeArchiveRecordRepository(),
    )
    plan = planner.plan("/archive", ())
    assert plan.planned_count == 1
    # builder stub recorded None captured_at — the real ArchivePathBuilderService
    # would turn it into UNKNOWN_EVENT_SEGMENT; planner just forwards the field.
    assert builder.calls[0] == ("Alice", None, "a.jpg")


def test_plan_dedupes_photo_across_persons() -> None:
    """A photo approved under two persons plans once; second is skipped."""
    alice = Person(name="Alice")
    bob = Person(name="Bob")
    photo = _absolute_photo("a.jpg", captured_at=datetime(2024, 5, 1))
    recognition = _make_recognition(photo.id, alice.id)
    recognition2 = _make_recognition(photo.id, bob.id)
    planner = ArchivePlanner(
        path_builder=_FakeArchivePathBuilder(),
        person_repository=_FakePersonRepository([alice, bob]),
        photo_repository=_FakePhotoRepository([photo]),
        recognition_repository=_FakeRecognitionRepository({
            alice.id: [recognition],
            bob.id: [recognition2],
        }),
        archive_record_repository=_FakeArchiveRecordRepository(),
    )
    plan = planner.plan("/archive", (alice.id, bob.id))
    assert plan.planned_count == 1
    assert plan.skipped_count == 1
    assert plan.items[0].person_name == "Alice"  # first APPROVED wins per 1:N Top-1


def test_plan_skips_missing_photo() -> None:
    """Photo deleted between match and plan is counted in skipped_count."""
    person = Person(name="Alice")
    photo = _absolute_photo("a.jpg", captured_at=datetime(2024, 5, 1))
    recognition = _make_recognition(photo.id, person.id)
    planner = ArchivePlanner(
        path_builder=_FakeArchivePathBuilder(),
        person_repository=_FakePersonRepository([person]),
        photo_repository=_FakePhotoRepository([]),  # photo vanished
        recognition_repository=_FakeRecognitionRepository({person.id: [recognition]}),
        archive_record_repository=_FakeArchiveRecordRepository(),
    )
    plan = planner.plan("/archive", ())
    assert plan.planned_count == 0
    assert plan.skipped_count >= 1


def test_plan_skips_already_archived_photo() -> None:
    """A photo with a past-PLANNED ArchiveRecord is skipped."""
    person = Person(name="Alice")
    photo = _absolute_photo("a.jpg", captured_at=datetime(2024, 5, 1))
    recognition = _make_recognition(photo.id, person.id)
    existing_record = ArchiveRecord(
        photo_id=photo.id,
        target_archive_root="/archive",
        target_person_name="Alice",
        target_event_or_date="2024-05-01",
        target_original_name="a.jpg",
        status=ArchiveStatus.ARCHIVED,
    )
    planner = ArchivePlanner(
        path_builder=_FakeArchivePathBuilder(),
        person_repository=_FakePersonRepository([person]),
        photo_repository=_FakePhotoRepository([photo]),
        recognition_repository=_FakeRecognitionRepository({person.id: [recognition]}),
        archive_record_repository=_FakeArchiveRecordRepository({photo.id: existing_record}),
    )
    plan = planner.plan("/archive", ())
    assert plan.planned_count == 0


def test_plan_skips_relative_path_photo() -> None:
    """Photos with relative paths require PHOTO_ROOT resolution — out of scope this round."""
    person = Person(name="Alice")
    photo = Photo(
        path=PhotoPath(Path("a.jpg"), base=PhotoPathBase.PHOTO_ROOT),
        original_name="a.jpg",
        captured_at=datetime(2024, 5, 1),
    )
    recognition = _make_recognition(photo.id, person.id)
    planner = ArchivePlanner(
        path_builder=_FakeArchivePathBuilder(),
        person_repository=_FakePersonRepository([person]),
        photo_repository=_FakePhotoRepository([photo]),
        recognition_repository=_FakeRecognitionRepository({person.id: [recognition]}),
        archive_record_repository=_FakeArchiveRecordRepository(),
    )
    plan = planner.plan("/archive", ())
    assert plan.planned_count == 0


def test_plan_empty_person_ids_expands_to_all_with_approvals() -> None:
    """Empty person_ids tuple means "all persons with approved photos"."""
    alice = Person(name="Alice")
    bob = Person(name="Bob")  # bob has no approved photos
    photo = _absolute_photo("a.jpg", captured_at=datetime(2024, 5, 1))
    recognition = _make_recognition(photo.id, alice.id)
    planner = ArchivePlanner(
        path_builder=_FakeArchivePathBuilder(),
        person_repository=_FakePersonRepository([alice, bob]),
        photo_repository=_FakePhotoRepository([photo]),
        recognition_repository=_FakeRecognitionRepository({alice.id: [recognition]}),
        archive_record_repository=_FakeArchiveRecordRepository(),
    )
    plan = planner.plan("/archive", ())
    assert plan.planned_count == 1
    assert plan.items[0].person_name == "Alice"


def test_plan_empty_person_ids_with_no_approvals_anywhere_yields_empty_plan() -> None:
    """review m-6 fix: N=0 boundary — no approved photos anywhere → empty plan, no crash.

    Exercises the _resolve_target_persons expansion when every person has zero
    approved recognitions; the comprehension filters them all out so the plan
    stays empty without throwing on the empty iteration.
    """
    alice = Person(name="Alice")
    bob = Person(name="Bob")
    planner = ArchivePlanner(
        path_builder=_FakeArchivePathBuilder(),
        person_repository=_FakePersonRepository([alice, bob]),
        photo_repository=_FakePhotoRepository([]),
        recognition_repository=_FakeRecognitionRepository({}),  # no approvals anywhere
        archive_record_repository=_FakeArchiveRecordRepository(),
    )
    plan = planner.plan("/archive", ())
    assert plan.planned_count == 0
    assert plan.skipped_count == 0
    assert plan.items == ()


def test_plan_skips_missing_person() -> None:
    """A person_id that no longer exists contributes to skipped_count."""
    person = Person(name="Alice")
    photo = _absolute_photo("a.jpg", captured_at=datetime(2024, 5, 1))
    recognition = _make_recognition(photo.id, person.id)
    planner = ArchivePlanner(
        path_builder=_FakeArchivePathBuilder(),
        person_repository=_FakePersonRepository([person]),
        photo_repository=_FakePhotoRepository([photo]),
        recognition_repository=_FakeRecognitionRepository({person.id: [recognition]}),
        archive_record_repository=_FakeArchiveRecordRepository(),
    )
    plan = planner.plan("/archive", (uuid4(),))  # person_id missing
    assert plan.planned_count == 0
    assert plan.skipped_count >= 1
