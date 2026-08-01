"""Photo repository interface."""

from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities import Photo
from photo_archiver.domain.value_objects import PhotoPath


class PhotoRepository(Protocol):
    """Define persistence operations for photo entities."""

    def add(self, photo: Photo) -> None:
        """Add a photo entity or replace the existing aggregate with the same id."""

    def find_by_id(self, photo_id: UUID) -> Photo | None:
        """Find a photo by its domain identifier."""

    def find_by_path(self, path: PhotoPath) -> Photo | None:
        """Find a photo by its path value."""

    def list_all(self) -> list[Photo]:
        """Return all known photos."""

    def list_by_folder_id(self, folder_id: UUID) -> list[Photo]:
        """Return photos belonging to the given folder."""

    def list_duplicate_groups(self) -> list[list[Photo]]:
        """Return groups of photos sharing the same non-null content hash.

        Each inner list contains two or more ``Photo`` aggregates that hashed
        to the same SHA-256 digest, indicating the same underlying file was
        imported more than once. Photos whose ``metadata.content_hash`` is
        ``None`` are excluded from grouping — they predate B1 wiring and are
        handled by the one-time backfill CLI rather than this query.

        Returns:
            A list of duplicate groups. Empty when no content hash appears
            on more than one photo. Group order and intra-group photo order
            are implementation-defined but stable across re-invocation.
        """