"""Domain model public API for PhotoArchiver."""

from photo_archiver.domain.entities import Folder, MatchStatus, Person, Photo, RecognitionResult
from photo_archiver.domain.exceptions import (
    PhotoArchiverDomainError,
    RepositoryError,
    ValidationError,
)
from photo_archiver.domain.repositories import (
    FaceEmbeddingRepository,
    FolderRepository,
    PersonRepository,
    PhotoRepository,
    RecognitionRepository,
)
from photo_archiver.domain.value_objects import (
    FaceBox,
    FaceEmbedding,
    PersonIdentity,
    PhotoMetadata,
    PhotoPath,
    PhotoPathBase,
)

__all__ = [
    "FaceBox",
    "FaceEmbedding",
    "FaceEmbeddingRepository",
    "Folder",
    "FolderRepository",
    "MatchStatus",
    "Person",
    "PersonIdentity",
    "PersonRepository",
    "Photo",
    "PhotoArchiverDomainError",
    "PhotoMetadata",
    "PhotoPath",
    "PhotoPathBase",
    "PhotoRepository",
    "RecognitionRepository",
    "RecognitionResult",
    "RepositoryError",
    "ValidationError",
]
