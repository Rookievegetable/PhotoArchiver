"""In-memory implementation of the folder repository interface."""

from uuid import UUID

from photo_archiver.domain import Folder, FolderRepository, PhotoPath


class InMemoryFolderRepository(FolderRepository):
    """Store folders in memory for tests and early application wiring."""

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._folders_by_id: dict[UUID, Folder] = {}

    def add(self, folder: Folder) -> None:
        """Persist a folder entity in memory."""
        self._folders_by_id[folder.id] = folder

    def find_by_id(self, folder_id: UUID) -> Folder | None:
        """Find a folder by its domain identifier."""
        return self._folders_by_id.get(folder_id)

    def find_by_path(self, path: PhotoPath) -> Folder | None:
        """Find a folder by its path value."""
        return next((folder for folder in self._folders_by_id.values() if folder.path == path), None)

    def list_all(self) -> list[Folder]:
        """Return all known folders."""
        return list(self._folders_by_id.values())