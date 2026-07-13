"""In-memory implementation of the photo repository interface."""

from uuid import UUID

from photo_archiver.domain import Photo, PhotoPath, PhotoRepository


class InMemoryPhotoRepository(PhotoRepository):
    """Store photos in memory for tests and early application wiring."""

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._photos_by_id: dict[UUID, Photo] = {}

    def add(self, photo: Photo) -> None:
        """Persist a photo entity in memory."""
        self._photos_by_id[photo.id] = photo

    def find_by_id(self, photo_id: UUID) -> Photo | None:
        """Find a photo by its domain identifier."""
        return self._photos_by_id.get(photo_id)

    def find_by_path(self, path: PhotoPath) -> Photo | None:
        """Find a photo by its path value."""
        return next((photo for photo in self._photos_by_id.values() if photo.path == path), None)

    def list_all(self) -> list[Photo]:
        """Return all known photos."""
        return list(self._photos_by_id.values())

    def list_by_folder_id(self, folder_id: UUID) -> list[Photo]:
        """Return photos belonging to the given folder."""
        return [photo for photo in self._photos_by_id.values() if photo.folder_id == folder_id]