"""Archive record repository interface."""

from collections.abc import Sequence
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

    def list_by_photo_ids(
        self, photo_ids: Sequence[UUID],
    ) -> list[ArchiveRecord]:
        """Return all archive records for the supplied photos.

        FILTERED-export query (FEATURE-004 contract
        ``docs/health-check/PHASE_7_SCOPE_CONTRACT_REVISION.md`` §3/F4): every
        ``ArchiveRecord`` — any ``ArchiveStatus`` — whose ``photo_id`` is in
        ``photo_ids`` (the full per-photo history, mirroring the ``ALL``
        scope's ``list_all`` section). Unlike ``find_by_photo``, which returns
        only the latest SUCCESS record of a single photo. Ordering matches
        ``list_all`` (recency) so both scopes emit consistent archive sections.

        Default implementation filters ``list_all``, so minimal implementations
        (e.g. test fakes) keep working unchanged — the ``add_many``
        default-implementation precedent. SQL-backed repositories SHOULD
        override with a single-trip IN-clause push-down (see
        ``SQLiteArchiveRecordRepository.list_by_photo_ids``).
        """
        wanted_photo_ids = set(photo_ids)
        return [
            record for record in self.list_all() if record.photo_id in wanted_photo_ids
        ]
