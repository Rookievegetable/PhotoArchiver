"""SQLite database infrastructure for PhotoArchiver."""

from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_face_embedding_repository import (
    SQLiteFaceEmbeddingRepository,
)
from photo_archiver.infrastructure.database.sqlite_folder_repository import SQLiteFolderRepository
from photo_archiver.infrastructure.database.sqlite_person_repository import SQLitePersonRepository
from photo_archiver.infrastructure.database.sqlite_photo_repository import SQLitePhotoRepository
from photo_archiver.infrastructure.database.sqlite_recognition_repository import (
    SQLiteRecognitionRepository,
)
from photo_archiver.infrastructure.database.sqlite_unit_of_work import SQLiteUnitOfWork

__all__ = [
    "SQLiteConnectionProvider",
    "SQLiteFaceEmbeddingRepository",
    "SQLiteFolderRepository",
    "SQLitePersonRepository",
    "SQLitePhotoRepository",
    "SQLiteRecognitionRepository",
    "SQLiteUnitOfWork",
]
