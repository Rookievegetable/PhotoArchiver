"""Filter criteria combination matrix — Phase 9 FEAT-P9-3 (P0 Filter Completeness).

Verifies the AND semantics of ``PhotoSearchCriteria`` over a REAL SQLite
database through the real ``SearchPhotosService`` for every axis combination
the P0 authorization requires:

    empty (all axes unset) · status only · person only · date only ·
    person+date · person+status · date+status · person+date+status ·
    no-match combinations · from>to · inclusive boundary dates

Seeding (real repositories, FK order, one shared Folder honouring the
production UNIQUE(raw_path, path_base)):

    Photo A alice_portrait.jpg  captured 2023-05-01  Alice PENDING + APPROVED
    Photo B bob_candid.jpg      captured 2024-06-15  Bob APPROVED
    Photo C alice_party.jpg     captured 2024-06-20  Alice REJECTED + PENDING

The person axis filters through ``recognition_results.person_id`` (the
repository's JOIN semantics, consumed verbatim — nothing reimplemented here);
the date axis through ``photos.captured_at`` (ISO strings, inclusive bounds).
No OR leakage, criteria loss, or overwrite may occur — the exact expected
photo set is asserted per combination.
"""

from datetime import datetime
from pathlib import Path

from photo_archiver.app import bootstrap_application
from photo_archiver.application.services import SearchPhotosService
from photo_archiver.domain import (
    ArchiveStatus,
    Folder,
    MatchStatus,
    Person,
    Photo,
    PhotoPath,
    PhotoSearchCriteria,
    RecognitionResult,
)
from photo_archiver.infrastructure.config import AppSettings

_FROM_2023 = datetime(2023, 1, 1, 0, 0, 0)
_TO_2023 = datetime(2023, 12, 31, 23, 59, 59)
_FROM_2024 = datetime(2024, 1, 1, 0, 0, 0)
_TO_2024 = datetime(2024, 12, 31, 23, 59, 59)


def _seed(tmp_path: Path):
    """Seed the real SQLite database; return (service, ids) for the matrix."""
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'filter_matrix.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    repositories = context.repositories

    folder = Folder(path=PhotoPath("photos"), total_photos=3)
    repositories.folders.add(folder)
    photo_a = Photo(
        path=PhotoPath("photos/alice_portrait.jpg"),
        folder_id=folder.id,
        original_name="alice_portrait.jpg",
        captured_at=datetime(2023, 5, 1, 10, 0, 0),
    )
    photo_b = Photo(
        path=PhotoPath("photos/bob_candid.jpg"),
        folder_id=folder.id,
        original_name="bob_candid.jpg",
        captured_at=datetime(2024, 6, 15, 10, 0, 0),
    )
    photo_c = Photo(
        path=PhotoPath("photos/alice_party.jpg"),
        folder_id=folder.id,
        original_name="alice_party.jpg",
        captured_at=datetime(2024, 6, 20, 10, 0, 0),
    )
    repositories.photos.add(photo_a)
    repositories.photos.add(photo_b)
    repositories.photos.add(photo_c)

    alice = Person(name="Alice")
    bob = Person(name="Bob")
    repositories.people.add(alice)
    repositories.people.add(bob)

    a_pending = RecognitionResult(photo_id=photo_a.id, confidence=0.87, person_id=alice.id)  # type: ignore[arg-type]
    repositories.recognition.add(a_pending)
    a_approved = RecognitionResult(photo_id=photo_a.id, confidence=0.92, person_id=alice.id)  # type: ignore[arg-type]
    a_approved.approve()
    repositories.recognition.add(a_approved)
    b_approved = RecognitionResult(photo_id=photo_b.id, confidence=0.81, person_id=bob.id)  # type: ignore[arg-type]
    b_approved.approve()
    repositories.recognition.add(b_approved)
    c_rejected = RecognitionResult(photo_id=photo_c.id, confidence=0.44, person_id=alice.id)  # type: ignore[arg-type]
    c_rejected.reject()
    repositories.recognition.add(c_rejected)
    c_pending = RecognitionResult(photo_id=photo_c.id, confidence=0.55, person_id=alice.id)  # type: ignore[arg-type]
    repositories.recognition.add(c_pending)

    # Give every photo one archive record too — the photo axis must be the
    # only discriminator, archive rows never leak into search results.
    from photo_archiver.domain.entities.archive import ArchiveRecord

    for photo, name in ((photo_a, "Alice"), (photo_b, "Bob"), (photo_c, "Alice")):
        repositories.archive_records.add(
            ArchiveRecord(
                photo_id=photo.id,  # type: ignore[arg-type]
                target_archive_root=str(tmp_path),
                target_person_name=name,
                target_event_or_date="2024-01",
                target_original_name=photo.original_name or "x.jpg",
                status=ArchiveStatus.PLANNED,
            )
        )

    return context, {
        "service": SearchPhotosService(repositories.photos),
        "photo_a": photo_a,
        "photo_b": photo_b,
        "photo_c": photo_c,
        "alice": alice,
        "bob": bob,
    }


def _paths(result, ids) -> set:
    return {photo.original_name for photo in result}


def test_empty_criteria_and_list_all_return_everything(tmp_path) -> None:
    context, ids = _seed(tmp_path)
    service = ids["service"]
    all_names = {"alice_portrait.jpg", "bob_candid.jpg", "alice_party.jpg"}
    # All-None criteria object: matches everything per the search contract.
    assert _paths(service.execute(PhotoSearchCriteria()), ids) == all_names
    assert _paths(context.repositories.photos.list_all(), ids) == all_names


def test_status_axis_single_combinations(tmp_path) -> None:
    _, ids = _seed(tmp_path)
    service = ids["service"]
    assert _paths(
        service.execute(PhotoSearchCriteria(match_status=MatchStatus.PENDING)), ids
    ) == {"alice_portrait.jpg", "alice_party.jpg"}
    assert _paths(
        service.execute(PhotoSearchCriteria(match_status=MatchStatus.APPROVED)), ids
    ) == {"alice_portrait.jpg", "bob_candid.jpg"}
    assert _paths(
        service.execute(PhotoSearchCriteria(match_status=MatchStatus.REJECTED)), ids
    ) == {"alice_party.jpg"}


def test_person_axis_single_combination(tmp_path) -> None:
    _, ids = _seed(tmp_path)
    service = ids["service"]
    assert _paths(
        service.execute(PhotoSearchCriteria(person_id=ids["alice"].id)), ids
    ) == {"alice_portrait.jpg", "alice_party.jpg"}
    assert _paths(
        service.execute(PhotoSearchCriteria(person_id=ids["bob"].id)), ids
    ) == {"bob_candid.jpg"}


def test_date_axis_single_combinations(tmp_path) -> None:
    _, ids = _seed(tmp_path)
    service = ids["service"]
    assert _paths(
        service.execute(PhotoSearchCriteria(captured_from=_FROM_2023, captured_to=_TO_2023)), ids
    ) == {"alice_portrait.jpg"}
    assert _paths(
        service.execute(PhotoSearchCriteria(captured_from=_FROM_2024, captured_to=_TO_2024)), ids
    ) == {"bob_candid.jpg", "alice_party.jpg"}


def test_person_and_date_double_combination(tmp_path) -> None:
    _, ids = _seed(tmp_path)
    service = ids["service"]
    assert _paths(
        service.execute(
            PhotoSearchCriteria(person_id=ids["alice"].id, captured_from=_FROM_2024, captured_to=_TO_2024)
        ),
        ids,
    ) == {"alice_party.jpg"}


def test_person_and_status_double_combination(tmp_path) -> None:
    _, ids = _seed(tmp_path)
    service = ids["service"]
    assert _paths(
        service.execute(
            PhotoSearchCriteria(person_id=ids["alice"].id, match_status=MatchStatus.APPROVED)
        ),
        ids,
    ) == {"alice_portrait.jpg"}
    assert _paths(
        service.execute(
            PhotoSearchCriteria(person_id=ids["bob"].id, match_status=MatchStatus.PENDING)
        ),
        ids,
    ) == set()  # Bob has no pending recognition — honest empty


def test_date_and_status_double_combination(tmp_path) -> None:
    _, ids = _seed(tmp_path)
    service = ids["service"]
    assert _paths(
        service.execute(
            PhotoSearchCriteria(match_status=MatchStatus.APPROVED, captured_from=_FROM_2024, captured_to=_TO_2024)
        ),
        ids,
    ) == {"bob_candid.jpg"}


def test_person_date_status_triple_combination(tmp_path) -> None:
    _, ids = _seed(tmp_path)
    service = ids["service"]
    assert _paths(
        service.execute(
            PhotoSearchCriteria(
                person_id=ids["alice"].id,
                match_status=MatchStatus.PENDING,
                captured_from=_FROM_2024,
                captured_to=_TO_2024,
            )
        ),
        ids,
    ) == {"alice_party.jpg"}
    # Same triple with approved → empty (Alice's approved recognition is 2023).
    assert _paths(
        service.execute(
            PhotoSearchCriteria(
                person_id=ids["alice"].id,
                match_status=MatchStatus.APPROVED,
                captured_from=_FROM_2024,
                captured_to=_TO_2024,
            )
        ),
        ids,
    ) == set()


def test_no_match_and_inverted_range_return_empty_without_error(tmp_path) -> None:
    """No-hit ranges and from>to both yield the honest empty result."""
    _, ids = _seed(tmp_path)
    service = ids["service"]
    inverted = service.execute(
        PhotoSearchCriteria(captured_from=_TO_2024, captured_to=_FROM_2023)
    )
    assert _paths(inverted, ids) == set()  # from > to — passed through, matches nothing


def test_boundary_dates_are_inclusive(tmp_path) -> None:
    _, ids = _seed(tmp_path)
    service = ids["service"]
    # Bounds exactly equal to B's and C's captured_at → both included.
    exact = service.execute(
        PhotoSearchCriteria(
            captured_from=datetime(2024, 6, 15, 10, 0, 0),
            captured_to=datetime(2024, 6, 20, 10, 0, 0),
        )
    )
    assert _paths(exact, ids) == {"bob_candid.jpg", "alice_party.jpg"}
