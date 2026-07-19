"""Application-level repository assembly."""

from dataclasses import dataclass
from pathlib import Path

from photo_archiver.domain import (
    ArchiveRecordRepository,
    FaceEmbeddingRepository,
    FolderRepository,
    PersonRepository,
    PhotoRepository,
    RecognitionRepository,
)
from photo_archiver.infrastructure import (
    SQLiteArchiveRecordRepository,
    SQLiteConnectionProvider,
    SQLiteFaceEmbeddingRepository,
    SQLiteFolderRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRepository,
)


@dataclass(frozen=True, slots=True)
class ApplicationRepositories:
    """Repository dependencies assembled for application runtime."""

    _connection_provider: SQLiteConnectionProvider
    folders: FolderRepository
    people: PersonRepository
    photos: PhotoRepository
    archive_records: ArchiveRecordRepository
    recognition: RecognitionRepository
    face_embeddings: FaceEmbeddingRepository


def build_sqlite_repositories(database_path: Path) -> ApplicationRepositories:
    """Build SQLite-backed repository implementations for runtime use.

    The connection provider initializes the repository schema before the
    container is returned. For file-backed databases, schema initialization also
    ensures that the database parent directory exists.
    """
    connection_provider = SQLiteConnectionProvider(database_path)
    connection_provider.initialize_schema()
    return ApplicationRepositories(
        _connection_provider=connection_provider,
        folders=SQLiteFolderRepository(connection_provider),
        people=SQLitePersonRepository(connection_provider),
        photos=SQLitePhotoRepository(connection_provider),
        archive_records=SQLiteArchiveRecordRepository(connection_provider),
        recognition=SQLiteRecognitionRepository(connection_provider),
        face_embeddings=SQLiteFaceEmbeddingRepository(connection_provider),
    )
