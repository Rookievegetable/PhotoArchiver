"""Archive record repository interface."""

from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities import ArchiveRecord
from photo_archiver.domain.entities.archive import ArchiveStatus


class ArchiveRecordRepository(Protocol):
    """Define persistence operations for archive record aggregates."""

    def add(self, record: ArchiveRecord) -> None:
        """Add an archive record or replace the existing aggregate by id."""

    def find_by_id(self, record_id: UUID) -> ArchiveRecord | None:
        """Find an archive record by its domain identifier."""

    def find_by_photo(self, photo_id: UUID) -> ArchiveRecord | None:
        """Return the most recent archive record for the given photo.

        Returns:
            The latest record by ``archived_at`` (or creation order), or
            ``None`` when the photo has never been archived. Callers use
            this to detect "already archived" before planning a fresh run.
        """

    def list_by_status(self, status: ArchiveStatus) -> list[ArchiveRecord]:
        """Return all archive records in the given lifecycle state."""

    def list_all(self) -> list[ArchiveRecord]:
        """Return all archive records ordered by recency."""
