"""Recognition result repository interface."""

from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities import MatchStatus, RecognitionResult


class RecognitionRepository(Protocol):
    """Define persistence operations for recognition result aggregates."""

    def add(self, result: RecognitionResult) -> None:
        """Add a recognition result or replace the existing aggregate by id."""

    def find_by_id(self, result_id: UUID) -> RecognitionResult | None:
        """Find a recognition result by its domain identifier."""

    def list_by_photo(self, photo_id: UUID) -> list[RecognitionResult]:
        """Return all recognition results for the given photo."""

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
