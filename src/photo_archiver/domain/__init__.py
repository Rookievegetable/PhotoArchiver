"""Domain model public API for PhotoArchiver."""

from photo_archiver.domain.entities import Folder, Person, Photo
from photo_archiver.domain.exceptions import (
    PhotoArchiverDomainError,
    RepositoryError,
    ValidationError,
)
from photo_archiver.domain.repositories import (
    FolderRepository,
    PersonRepository,
    PhotoRepository,
)
from photo_archiver.domain.value_objects import (
    PersonIdentity,
    PhotoMetadata,
    PhotoPath,
    PhotoPathBase,
)

__all__ = [
    "Folder",
    "FolderRepository",
    "Person",
    "PersonIdentity",
    "PersonRepository",
    "Photo",
    "PhotoArchiverDomainError",
    "PhotoMetadata",
    "PhotoPath",
    "PhotoPathBase",
    "PhotoRepository",
    "RepositoryError",
    "ValidationError",
]
