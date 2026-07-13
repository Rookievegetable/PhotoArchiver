"""Domain repository interfaces."""

from photo_archiver.domain.repositories.folder_repository import FolderRepository
from photo_archiver.domain.repositories.person_repository import PersonRepository
from photo_archiver.domain.repositories.photo_repository import PhotoRepository

__all__ = ["FolderRepository", "PersonRepository", "PhotoRepository"]