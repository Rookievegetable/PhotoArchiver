"""Infrastructure adapters for PhotoArchiver."""

from photo_archiver.infrastructure.ai import (
    InsightFaceLoader,
    ModelPackMissing,
)
from photo_archiver.infrastructure.database import (
    SQLiteConnectionProvider,
    SQLiteFaceEmbeddingRepository,
    SQLiteFolderRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRepository,
    SQLiteUnitOfWork,
)
from photo_archiver.infrastructure.filesystem import (
    LocalPhotoFileScanner,
    PillowPhotoMetadataReader,
)
from photo_archiver.infrastructure.image import (
    ContentHashCalculator,
    PillowThumbnailGenerator,
    ThumbnailCache,
)
from photo_archiver.infrastructure.importers import ExcelPersonImportReader, TxtPersonImportReader
from photo_archiver.infrastructure.repositories import (
    InMemoryFolderRepository,
    InMemoryPersonRepository,
    InMemoryPhotoRepository,
)

__all__ = [
    "ContentHashCalculator",
    "ExcelPersonImportReader",
    "InMemoryFolderRepository",
    "InMemoryPersonRepository",
    "InMemoryPhotoRepository",
    "InsightFaceLoader",
    "LocalPhotoFileScanner",
    "ModelPackMissing",
    "PillowPhotoMetadataReader",
    "PillowThumbnailGenerator",
    "SQLiteConnectionProvider",
    "SQLiteFaceEmbeddingRepository",
    "SQLiteFolderRepository",
    "SQLitePersonRepository",
    "SQLitePhotoRepository",
    "SQLiteRecognitionRepository",
    "SQLiteUnitOfWork",
    "TxtPersonImportReader",
    "ThumbnailCache",
]
