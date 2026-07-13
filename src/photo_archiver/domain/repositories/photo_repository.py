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