"""Recognition result repository interface."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities import MatchStatus, RecognitionResult


class RecognitionRepository(Protocol):
    """Define persistence operations for recognition result aggregates."""

    def add(self, result: RecognitionResult) -> None:
        """Add a recognition result or replace the existing aggregate by id."""

    def add_many(self, results: Sequence[RecognitionResult]) -> None:
        """Add a batch of recognition results in one call.

        Default implementation loops ``add`` so minimal implementations keep
        working unchanged; SQL-backed repositories SHOULD override this with a
        single-transaction push-down (see ``SQLiteRecognitionRepository.add_many``).
        """
        for result in results:
            self.add(result)

    def find_by_id(self, result_id: UUID) -> RecognitionResult | None:
        """Find a recognition result by its domain identifier."""

    def list_by_photo(self, photo_id: UUID) -> list[RecognitionResult]:
        """Return all recognition results for the given photo."""

    def list_first_by_photo_ids(
        self, photo_ids: Sequence[UUID]
    ) -> dict[UUID, RecognitionResult]:
        """Return the earliest recognition result per photo, in one round trip.

        Mirrors the "first element of ``list_by_photo``" semantics (ordered by
        ``created_at`` then ``id``) for every supplied photo id, so callers
        pairing photos with review status avoid N+1 per-photo lookups.
        Photo ids without any recognition result are absent from the mapping.
        """

    def list_by_photo_ids(
        self, photo_ids: Sequence[UUID],
    ) -> list[RecognitionResult]:
        """Return ALL recognition results for the supplied photos, in one batch.

        FILTERED-export query (FEATURE-004 contract
        ``docs/health-check/PHASE_7_SCOPE_CONTRACT_REVISION.md`` §3/F4): every
        result — any ``MatchStatus`` — whose ``photo_id`` is in ``photo_ids``.
        Unlike ``list_first_by_photo_ids`` (earliest per photo) and
        ``list_by_photo`` (single photo). Results are ordered by ``created_at``
        then ``id``; ``created_at`` is always populated by
        ``RecognitionResult.__post_init__`` so the ordering key is total.

        Default implementation loops ``list_by_photo`` (deduplicating inputs —
        duplicate photo ids must not duplicate rows, matching IN-clause
        semantics) and re-sorts globally, so minimal implementations (e.g.
        test fakes) keep working unchanged — the ``add_many`` default-
        implementation precedent. SQL-backed repositories SHOULD override with
        a single-trip IN-clause push-down (see
        ``SQLiteRecognitionRepository.list_by_photo_ids``).
        """
        collected: list[RecognitionResult] = []
        seen_photo_ids: set[UUID] = set()
        for photo_id in photo_ids:
            if photo_id in seen_photo_ids:
                continue
            seen_photo_ids.add(photo_id)
            collected.extend(self.list_by_photo(photo_id))
        collected.sort(
            key=lambda result: (
                result.created_at if result.created_at is not None else datetime.min,
                result.id,
            ),
        )
        return collected

    def list_pending(self) -> list[RecognitionResult]:
        """Return all recognition results awaiting user review."""

    def list_approved_by_person(self, person_id: UUID) -> list[RecognitionResult]:
        """Return all APPROVED recognition results for the given person.

        Used by Step 11 ArchivePlanner to gather a person's approved photos
        for归档组织。Results are ordered by ``created_at`` then ``id`` so
        the planner produces a stable archive ordering under re-invocation.
        """

    def update_status(self, result_id: UUID, status: MatchStatus) -> int:
        """Transition a recognition result's review status.

        Returns:
            The number of rows affected (1 on hit, 0 when the result id is
            missing). Callers SHOULD treat 0 as a concurrent-deletion signal
            rather than silently assuming success.
        """
