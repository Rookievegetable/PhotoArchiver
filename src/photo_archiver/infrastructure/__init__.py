"""Infrastructure adapters for PhotoArchiver."""

from photo_archiver.infrastructure.ai import (
    InsightFaceLoader,
    ModelPackMissing,
)
from photo_archiver.infrastructure.cosine_kernel import (
    NumpyCosineSimilarityFactory,
    NumpyCosineSimilarityLookup,
)
from photo_archiver.infrastructure.database import (
    SQLiteArchiveRecordRepository,
    SQLiteClusterPersonAssignmentRepository,
    SQLiteConnectionProvider,
    SQLiteFaceClusterRepository,
    SQLiteFaceEmbeddingRepository,
    SQLiteFaceObservationRepository,
    SQLiteFolderRepository,
    SQLiteImportBatchRepository,
    SQLitePersonFaceSampleRepository,
    SQLitePersonRepository,
    SQLitePhotoIgnoreStateRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRepository,
    SQLiteRecognitionRunRepository,
    SQLiteUnitOfWork,
)
from photo_archiver.infrastructure.exporters import CsvExporter, ExcelExporter
from photo_archiver.infrastructure.filesystem import (
    LocalPhotoFileScanner,
    PillowPhotoMetadataReader,
)
from photo_archiver.infrastructure.image import (
    ContentHashCalculator,
    PillowThumbnailGenerator,
    ThumbnailCache,
)
from photo_archiver.infrastructure.importers import (
    DispatchingPersonImportReader,
    ExcelPersonImportReader,
    FileRosterTableReader,
    TxtPersonImportReader,
)
from photo_archiver.infrastructure.persistence import (
    InMemoryUserSettingsStore,
)
from photo_archiver.infrastructure.repositories import (
    InMemoryClusterPersonAssignmentRepository,
    InMemoryFaceClusterRepository,
    InMemoryFaceObservationRepository,
    InMemoryFolderRepository,
    InMemoryPersonFaceSampleRepository,
    InMemoryPersonRepository,
    InMemoryPhotoIgnoreStateRepository,
    InMemoryPhotoRepository,
    InMemoryRecognitionRunRepository,
)

__all__ = [
    "ContentHashCalculator",
    "CsvExporter",
    "DispatchingPersonImportReader",
    "FileRosterTableReader",
    "FileRosterTableReader",
    "ExcelExporter",
    "ExcelPersonImportReader",
    "InMemoryClusterPersonAssignmentRepository",
    "InMemoryFaceClusterRepository",
    "InMemoryPersonFaceSampleRepository",
    "InMemoryFaceObservationRepository",
    "NumpyCosineSimilarityFactory",
    "NumpyCosineSimilarityLookup",
    "InMemoryFolderRepository",
    "InMemoryRecognitionRunRepository",
    "InMemoryPersonRepository",
    "InMemoryPhotoIgnoreStateRepository",
    "InMemoryPhotoRepository",
    "InMemoryUserSettingsStore",
    "InsightFaceLoader",
    "LocalPhotoFileScanner",
    "ModelPackMissing",
    "PillowPhotoMetadataReader",
    "PillowThumbnailGenerator",
    "SQLiteArchiveRecordRepository",
    "SQLiteConnectionProvider",
    "SQLiteClusterPersonAssignmentRepository",
    "SQLiteFaceClusterRepository",
    "SQLitePersonFaceSampleRepository",
    "SQLiteFaceEmbeddingRepository",
    "SQLiteFaceObservationRepository",
    "SQLiteFolderRepository",
    "SQLiteImportBatchRepository",
    "SQLitePersonRepository",
    "SQLitePhotoIgnoreStateRepository",
    "SQLitePhotoRepository",
    "SQLiteRecognitionRepository",
    "SQLiteRecognitionRunRepository",
    "SQLiteUnitOfWork",
    "TxtPersonImportReader",
    "ThumbnailCache",
]
