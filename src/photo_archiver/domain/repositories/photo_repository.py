"""Photo repository interface."""

from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities import Photo
from photo_archiver.domain.value_objects import PhotoPath, PhotoSearchCriteria


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

    def search(self, criteria: PhotoSearchCriteria) -> list[Photo]:
        """Return photos matching every supplied criterion (AND combination).

        All fields of ``criteria`` are optional; an unset field means "no
        constraint on this axis". The empty criteria (all None) matches every
        photo — equivalent to ``list_all`` but routed through the same search
        contract for UI consistency.

        Field semantics:
            person_id: photos linked to this person via a recognition result
                (JOIN recognition_results); status filtering is independent
                — use ``match_status`` to additionally constrain the result status.
            match_status: photos having ≥1 recognition result in this status.
                ``MatchStatus.PENDING/APROVED/REJECTED`` filter by that status.
                Photos with NO recognition results at all are **excluded** from
                any ``match_status`` filter (a sentinel "no result" axis is not
                covered by ``MatchStatus`` enum; future extension if needed).
            captured_from / captured_to: inclusive closed interval over
                ``Photo.captured_at``. Photos with NULL ``captured_at`` are
                **excluded** from any date-axis constraint (documented default).

        Returns:
            A list of matching ``Photo`` aggregates ordered by ``created_at``
            then ``id`` for stable presentation. Empty when no photo matches.
        """

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