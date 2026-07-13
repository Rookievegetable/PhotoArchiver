"""Folder repository interface."""

from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities import Folder
from photo_archiver.domain.value_objects import PhotoPath


class FolderRepository(Protocol):
    """Define persistence operations for folder entities."""

    def add(self, folder: Folder) -> None:
        """Add a folder entity or replace the existing aggregate with the same id."""

    def find_by_id(self, folder_id: UUID) -> Folder | None:
        """Find a folder by its domain identifier."""

    def find_by_path(self, path: PhotoPath) -> Folder | None:
        """Find a folder by its path value."""

    def list_all(self) -> list[Folder]:
        """Return all known folders."""