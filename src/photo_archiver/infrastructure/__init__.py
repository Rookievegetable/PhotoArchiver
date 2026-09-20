"""Infrastructure adapters for PhotoArchiver."""

from photo_archiver.infrastructure.ai import (
    InsightFaceLoader,
    ModelPackMissing,
)
from photo_archiver.infrastructure.database import (
    SQLiteArchiveRecordRepository,
    SQLiteConnectionProvider,
    SQLiteFaceEmbeddingRepository,
    SQLiteFolderRepository,
    SQLiteImportBatchRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRepository,
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
    InMemoryFolderRepository,
    InMemoryPersonRepository,
    InMemoryPhotoRepository,
)

__all__ = [
    "ContentHashCalculator",
    "CsvExporter",
    "DispatchingPersonImportReader",
    "FileRosterTableReader",
    "FileRosterTableReader",
    "ExcelExporter",
    "ExcelPersonImportReader",
    "InMemoryFolderRepository",
    "InMemoryPersonRepository",
    "InMemoryPhotoRepository",
    "InMemoryUserSettingsStore",
    "InsightFaceLoader",
    "LocalPhotoFileScanner",
    "ModelPackMissing",
    "PillowPhotoMetadataReader",
    "PillowThumbnailGenerator",
    "SQLiteArchiveRecordRepository",
    "SQLiteConnectionProvider",
    "SQLiteFaceEmbeddingRepository",
    "SQLiteFolderRepository",
    "SQLiteImportBatchRepository",
    "SQLitePersonRepository",
    "SQLitePhotoRepository",
    "SQLiteRecognitionRepository",
    "SQLiteUnitOfWork",
    "TxtPersonImportReader",
    "ThumbnailCache",
]
