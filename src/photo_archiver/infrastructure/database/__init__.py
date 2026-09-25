"""SQLite database infrastructure for PhotoArchiver."""

from photo_archiver.infrastructure.database.sqlite_archive_record_repository import (
    SQLiteArchiveRecordRepository,
)
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_face_cluster_repository import (
    SQLiteFaceClusterRepository,
)
from photo_archiver.infrastructure.database.sqlite_face_embedding_repository import (
    SQLiteFaceEmbeddingRepository,
)
from photo_archiver.infrastructure.database.sqlite_folder_repository import SQLiteFolderRepository
from photo_archiver.infrastructure.database.sqlite_import_batch_repository import SQLiteImportBatchRepository
from photo_archiver.infrastructure.database.sqlite_person_repository import SQLitePersonRepository
from photo_archiver.infrastructure.database.sqlite_photo_repository import SQLitePhotoRepository
from photo_archiver.infrastructure.database.sqlite_recognition_repository import (
    SQLiteRecognitionRepository,
)
from photo_archiver.infrastructure.database.sqlite_recognition_run_repository import (
    SQLiteRecognitionRunRepository,
)
from photo_archiver.infrastructure.database.sqlite_face_observation_repository import (
    SQLiteFaceObservationRepository,
)
from photo_archiver.infrastructure.database.sqlite_unit_of_work import SQLiteUnitOfWork

__all__ = [
    "SQLiteArchiveRecordRepository",
    "SQLiteConnectionProvider",
    "SQLiteFaceClusterRepository",
    "SQLiteFaceEmbeddingRepository",
    "SQLiteFolderRepository",
    "SQLiteImportBatchRepository",
    "SQLitePersonRepository",
    "SQLitePhotoRepository",
    "SQLiteRecognitionRepository",
    "SQLiteRecognitionRunRepository",
    "SQLiteFaceObservationRepository",
    "SQLiteUnitOfWork",
]
