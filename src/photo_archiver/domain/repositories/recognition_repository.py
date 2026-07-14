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

    def update_status(self, result_id: UUID, status: MatchStatus) -> None:
        """Transition a recognition result's review status."""
