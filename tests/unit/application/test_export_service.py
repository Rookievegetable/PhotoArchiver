"""ExportService scope-dispatch unit tests (Phase 7 Commit 2 — FEATURE-004).

Pins the three-branch scope dispatch contract
(docs/health-check/PHASE_7_SCOPE_CONTRACT_REVISION.md §3/§6 Commit 2):

- ALL: full catalog with approved-only matches — behavior unchanged;
- FILTERED: photo main set via search(criteria) + derived sections, with the
  matches section keeping ALL statuses (a Status=Pending export must still
  see its matches — §3/F4 rationale);
- CURRENT_BATCH: rejected with ValueError (§2/D4) — never a silent ALL
  fallback;
- FILTERED without a criteria snapshot: rejected with ValueError (§3/F3/F6).

Test-double boundary: the four repositories are small in-memory fakes because
the unit under test is the SERVICE's dispatch/derivation logic, not storage.
The repository layer — including the list_by_photo_ids default vs SQLite
push-down contrast — is covered by
tests/unit/infrastructure/test_list_by_photo_ids.py, and the full chain
incl. real SQLite by tests/integration/export/. The photo fake implements
the DOCUMENTED search semantics (AND axes: match_status joins the injected
recognitions; person_id via recognition link; captured range over
Photo.captured_at) — the production InMemoryPhotoRepository holds no
recognitions and returns [] for those axes, so the fake mirrors the SQLite
semantics the FILTERED contract is written against. What remains real:
ExportService (dispatch asserted via the private _gather_data for
section-level ExportData; the public export() path is e2e-covered),
ExportScope, PhotoSearchCriteria, domain entities, ExportData, and the
Protocol-default list_by_photo_ids inherited by the recognition fake.
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.application.services.export_service import ExportService
from photo_archiver.domain import (
    ArchiveRecord,
    ArchiveStatus,
    MatchStatus,
    Person,
    Photo,
    PhotoPath,
    PhotoSearchCriteria,
    RecognitionResult,
)
from photo_archiver.domain.repositories import (
    ArchiveRecordRepository,
    PersonRepository,
    PhotoRepository,
    RecognitionRepository,
)


# ── Fakes ────────────────────────────────────────────────────────────────────


class _FakePersonRepository(PersonRepository):
    """In-memory person repo (find_by_id drives FILTERED people derivation)."""

    def __init__(self) -> None:
        self._persons: list[Person] = []

    def add(self, person: Person) -> None:
        self._persons.append(person)

    def find_by_id(self, person_id: UUID) -> Person | None:
        return next((p for p in self._persons if p.id == person_id), None)

    def find_by_identity(self, identity) -> Person | None:  # noqa: ANN001
        return None

    def list_all(self) -> list[Person]:
        return list(self._persons)


class _FakePhotoRepository(PhotoRepository):
    """In-memory photo repo implementing the documented search axis semantics."""

    def __init__(self, recognitions: Sequence[RecognitionResult] = ()) -> None:
        self._photos: list[Photo] = []
        self._recognitions = list(recognitions)

    def add(self, photo: Photo) -> None:
        self._photos.append(photo)

    def find_by_id(self, photo_id: UUID) -> Photo | None:
        return next((p for p in self._photos if p.id == photo_id), None)

    def find_by_path(self, path: PhotoPath) -> Photo | None:
        return next((p for p in self._photos if p.path == path), None)

    def list_all(self) -> list[Photo]:
        return list(self._photos)

    def list_by_folder_id(self, folder_id: UUID) -> list[Photo]:
        return [p for p in self._photos if p.folder_id == folder_id]

    def list_duplicate_groups(self) -> list[list[Photo]]:
        return []

    def search(self, criteria: PhotoSearchCriteria) -> list[Photo]:
        """AND semantics per PhotoRepository.search docstring (insertion order)."""
        matched = list(self._photos)
        if criteria.match_status is not None:
            recognized = {
                r.photo_id
                for r in self._recognitions
                if r.status is criteria.match_status
            }
            matched = [p for p in matched if p.id in recognized]
        if criteria.person_id is not None:
            linked = {
                r.photo_id
                for r in self._recognitions
                if r.person_id == criteria.person_id
            }
            matched = [p for p in matched if p.id in linked]
        if criteria.captured_from is not None:
            matched = [
                p for p in matched
                if p.captured_at is not None and p.captured_at >= criteria.captured_from
            ]
        if criteria.captured_to is not None:
            matched = [
                p for p in matched
                if p.captured_at is not None and p.captured_at <= criteria.captured_to
            ]
        return matched



class _FakeRecognitionRepository(RecognitionRepository):
    """In-memory recognition repo inheriting the Protocol-default
    list_by_photo_ids (loop list_by_photo + global sort) — recording calls so
    the tests can pin that the service queries with exactly the main-set ids.
    """

    def __init__(self) -> None:
        self._results: list[RecognitionResult] = []
        self.list_by_photo_ids_calls: list[list[UUID]] = []

    def add(self, result: RecognitionResult) -> None:
        self._results.append(result)

    def find_by_id(self, result_id: UUID) -> RecognitionResult | None:
        return next((r for r in self._results if r.id == result_id), None)

    def list_by_photo(self, photo_id: UUID) -> list[RecognitionResult]:
        return [r for r in self._results if r.photo_id == photo_id]

    def list_by_photo_ids(
        self, photo_ids: Sequence[UUID],
    ) -> list[RecognitionResult]:
        self.list_by_photo_ids_calls.append(list(photo_ids))
        return super().list_by_photo_ids(photo_ids)

    def list_pending(self) -> list[RecognitionResult]:
        return [r for r in self._results if r.status is MatchStatus.PENDING]

    def list_approved_by_person(self, person_id: UUID) -> list[RecognitionResult]:
        return [
            r for r in self._results
            if r.person_id == person_id and r.status is MatchStatus.APPROVED
        ]

    def update_status(self, result_id: UUID, status: MatchStatus) -> int:
        count = 0
        for r in self._results:
            if r.id == result_id:
                r.status = status
                count = 1
        return count


class _FakeArchiveRecordRepository(ArchiveRecordRepository):
    """In-memory archive repo inheriting the Protocol-default list_by_photo_ids."""

    def __init__(self) -> None:
        self._records: list[ArchiveRecord] = []

    def add(self, record: ArchiveRecord) -> None:
        self._records.append(record)

    def find_by_id(self, record_id: UUID) -> ArchiveRecord | None:
        return next((r for r in self._records if r.id == record_id), None)

    def find_by_photo(self, photo_id: UUID) -> ArchiveRecord | None:
        return next((r for r in self._records if r.photo_id == photo_id), None)

    def list_by_status(self, status: ArchiveStatus) -> list[ArchiveRecord]:
        return [r for r in self._records if r.status == status]

    def list_all(self) -> list[ArchiveRecord]:
        return list(self._records)


# ── Builders ─────────────────────────────────────────────────────────────────


def _make_photo(name: str) -> Photo:
    return Photo(path=PhotoPath(f"photos/{name}.jpg"), id=uuid4())


def _make_recognition(
    photo_id: UUID,
    person_id: UUID | None,
    status: MatchStatus,
    created_at: datetime | None = None,
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


def _make_archive_record(photo_id: UUID, person_name: str = "Carol") -> ArchiveRecord:
    return ArchiveRecord(
        photo_id=photo_id,
        target_archive_root="Z:/Archive",
        target_person_name=person_name,
        target_event_or_date="2026-08-30",
        target_original_name="x.jpg",
        status=ArchiveStatus.PLANNED,
    )


def _make_service(
    persons: list[Person],
    photos: list[Photo],
    recognitions: list[RecognitionResult],
    records: list[ArchiveRecord],
) -> tuple[ExportService, _FakeRecognitionRepository]:
    person_repo = _FakePersonRepository()
    for person in persons:
        person_repo.add(person)
    photo_repo = _FakePhotoRepository(recognitions)
    for photo in photos:
        photo_repo.add(photo)
    recognition_repo = _FakeRecognitionRepository()
    for result in recognitions:
        recognition_repo.add(result)
    archive_repo = _FakeArchiveRecordRepository()
    for record in records:
        archive_repo.add(record)
    service = ExportService(
        person_repository=person_repo,
        photo_repository=photo_repo,
        recognition_repository=recognition_repo,
        archive_record_repository=archive_repo,
    )
    return service, recognition_repo



# ── ALL scope ────────────────────────────────────────────────────────────────


def test_all_scope_keeps_approved_only_matches_and_full_catalog() -> None:
    """ALL: full people/photos/archive + approved-only matches (unchanged)."""
    person_a = Person(name="Alice", id=uuid4())
    person_b = Person(name="Bob", id=uuid4())
    photo_1 = _make_photo("wedding")
    photo_2 = _make_photo("graduation")
    recognitions = [
        _make_recognition(photo_1.id, person_a.id, MatchStatus.APPROVED),
        _make_recognition(photo_2.id, person_b.id, MatchStatus.PENDING),
    ]
    record = _make_archive_record(photo_1.id)
    service, _ = _make_service(
        [person_a, person_b], [photo_1, photo_2], recognitions, [record],
    )

    data = service._gather_data(ExportScope.ALL)  # noqa: SLF001 - dispatch unit

    assert [p.name for p in data.people] == ["Alice", "Bob"]
    assert [ph.path for ph in data.photos] == [str(photo_1.path), str(photo_2.path)]
    # ALL semantics: approved-only matches — the PENDING result is absent.
    assert len(data.matches) == 1
    assert data.matches[0].photo_id == str(photo_1.id)
    assert data.matches[0].status == "approved"
    assert [a.photo_id for a in data.archive_records] == [str(photo_1.id)]


# ── CURRENT_BATCH ────────────────────────────────────────────────────────────


def test_current_batch_is_rejected_with_value_error() -> None:
    """D4: CURRENT_BATCH is deferred — explicit rejection, never silent ALL."""
    service, _ = _make_service([], [], [], [])

    with pytest.raises(ValueError, match="CURRENT_BATCH is deferred"):
        service._gather_data(ExportScope.CURRENT_BATCH)  # noqa: SLF001


# ── FILTERED: defense ────────────────────────────────────────────────────────


def test_filtered_without_criteria_is_rejected_with_value_error() -> None:
    """F3/F6: FILTERED without a criteria snapshot is a service-layer error."""
    service, _ = _make_service([], [], [], [])

    with pytest.raises(ValueError, match="FILTERED requires a PhotoSearchCriteria"):
        service._gather_data(ExportScope.FILTERED, criteria=None)  # noqa: SLF001


# ── FILTERED: four-section semantics ─────────────────────────────────────────


def test_filtered_by_pending_keeps_matches_and_derives_sections() -> None:
    """F4 core: Status=Pending main set keeps ALL match statuses in the section.

    Main set = photos with >=1 PENDING recognition. The section must still
    carry the main set's APPROVED recognition too (re-filtering would empty
    the evidence chain), people derive from matches, and archive_records /
    photos contain only main-set entries.
    """
    person_a = Person(name="Alice", id=uuid4())
    person_b = Person(name="Bob", id=uuid4())
    photo_pending = _make_photo("pending_shot")    # PENDING -> in main set
    photo_approved = _make_photo("approved_shot")  # APPROVED only -> excluded
    photo_unmatched = _make_photo("unmatched")     # no recognition -> excluded
    recognitions = [
        _make_recognition(
            photo_pending.id, person_a.id, MatchStatus.PENDING,
            created_at=datetime(2026, 8, 1, 12, 0, 0),
        ),
        _make_recognition(
            photo_pending.id, person_b.id, MatchStatus.APPROVED,
            created_at=datetime(2026, 8, 1, 12, 0, 1),
        ),
        _make_recognition(
            photo_approved.id, person_b.id, MatchStatus.APPROVED,
            created_at=datetime(2026, 8, 1, 12, 0, 2),
        ),
    ]
    records = [
        _make_archive_record(photo_pending.id, "Alice"),
        _make_archive_record(photo_approved.id, "Bob"),
    ]
    service, recognition_repo = _make_service(
        [person_a, person_b],
        [photo_pending, photo_approved, photo_unmatched],
        recognitions,
        records,
    )

    data = service._gather_data(  # noqa: SLF001 - dispatch unit
        ExportScope.FILTERED,
        criteria=PhotoSearchCriteria(match_status=MatchStatus.PENDING),
    )

    # photos: only the main set
    assert [ph.photo_id for ph in data.photos] == [str(photo_pending.id)]
    # matches: ALL statuses of the main set — Pending AND Approved both present
    assert {(m.photo_id, m.status) for m in data.matches} == {
        (str(photo_pending.id), "pending"),
        (str(photo_pending.id), "approved"),
    }
    # people: derived from matches, first-appearance order (created_at sorted)
    assert [p.name for p in data.people] == ["Alice", "Bob"]
    # archive_records: only main-set records
    assert [a.photo_id for a in data.archive_records] == [str(photo_pending.id)]
    # the service queried the recognition repo with exactly the main-set ids
    assert recognition_repo.list_by_photo_ids_calls == [[photo_pending.id]]


def test_filtered_no_matches_yields_all_sections_empty() -> None:
    """An empty main set yields empty sections — no error, no ALL fallback."""
    service, recognition_repo = _make_service(
        [Person(name="Alice", id=uuid4())], [], [], [],
    )

    data = service._gather_data(  # noqa: SLF001 - dispatch unit
        ExportScope.FILTERED,
        criteria=PhotoSearchCriteria(match_status=MatchStatus.REJECTED),
    )

    assert data.people == ()
    assert data.photos == ()
    assert data.matches == ()
    assert data.archive_records == ()
    # empty main set still routes through list_by_photo_ids (empty input)
    assert recognition_repo.list_by_photo_ids_calls == [[]]


