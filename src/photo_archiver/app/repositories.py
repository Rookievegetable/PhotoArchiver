"""Application-level repository assembly."""

from dataclasses import dataclass
from pathlib import Path

from photo_archiver.domain import (
    ArchiveRecordRepository,
    ClusterPersonAssignmentRepository,
    FaceClusterRepository,
    PersonFaceSampleRepository,
    FaceEmbeddingRepository,
    FolderRepository,
    ImportBatchRepository,
    PersonRepository,
    PhotoRepository,
    RecognitionRepository,
    RecognitionRunRepository,
    FaceObservationRepository,
)
from photo_archiver.domain.repositories.calibration_annotation_repository import (
    CalibrationAnnotationRepository,
)
from photo_archiver.infrastructure.database.sqlite_calibration_annotation_repository import (
    SQLiteCalibrationAnnotationRepository,
)
from photo_archiver.infrastructure import (
    SQLiteArchiveRecordRepository,
    SQLiteClusterPersonAssignmentRepository,
    SQLiteConnectionProvider,
    SQLiteFaceClusterRepository,
    SQLiteFaceEmbeddingRepository,
    SQLiteFolderRepository,
    SQLiteImportBatchRepository,
    SQLitePersonFaceSampleRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRepository,
    SQLiteRecognitionRunRepository,
    SQLiteFaceObservationRepository,
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
    recognition_runs: RecognitionRunRepository
    face_observations: FaceObservationRepository
    face_clusters: FaceClusterRepository
    face_embeddings: FaceEmbeddingRepository
    cluster_assignments: ClusterPersonAssignmentRepository
    person_face_samples: PersonFaceSampleRepository
    import_batches: ImportBatchRepository
    calibration_annotations: CalibrationAnnotationRepository


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
        recognition_runs=SQLiteRecognitionRunRepository(connection_provider),
        face_observations=SQLiteFaceObservationRepository(connection_provider),
        face_clusters=SQLiteFaceClusterRepository(connection_provider),
        cluster_assignments=SQLiteClusterPersonAssignmentRepository(connection_provider),
        person_face_samples=SQLitePersonFaceSampleRepository(connection_provider),
        face_embeddings=SQLiteFaceEmbeddingRepository(connection_provider),
        import_batches=SQLiteImportBatchRepository(connection_provider),
        calibration_annotations=SQLiteCalibrationAnnotationRepository(
            connection_provider
        ),
    )
