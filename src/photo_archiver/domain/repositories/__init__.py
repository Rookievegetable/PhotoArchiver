"""Domain repository interfaces."""

from photo_archiver.domain.repositories.archive_record_repository import ArchiveRecordRepository
from photo_archiver.domain.repositories.face_embedding_repository import FaceEmbeddingRepository
from photo_archiver.domain.repositories.folder_repository import FolderRepository
from photo_archiver.domain.repositories.person_repository import PersonRepository
from photo_archiver.domain.repositories.photo_repository import PhotoRepository
from photo_archiver.domain.repositories.recognition_repository import RecognitionRepository

__all__ = [
    "ArchiveRecordRepository",
    "FaceEmbeddingRepository",
    "FolderRepository",
    "PersonRepository",
    "PhotoRepository",
    "RecognitionRepository",
]