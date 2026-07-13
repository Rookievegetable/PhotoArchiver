"""Infrastructure adapters for PhotoArchiver."""

from photo_archiver.infrastructure.database import (
    SQLiteConnectionProvider,
    SQLiteFolderRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteUnitOfWork,
)
from photo_archiver.infrastructure.filesystem import (
    LocalPhotoFileScanner,
    PillowPhotoMetadataReader,
)
from photo_archiver.infrastructure.importers import ExcelPersonImportReader, TxtPersonImportReader
from photo_archiver.infrastructure.repositories import (
    InMemoryFolderRepository,
    InMemoryPersonRepository,
    InMemoryPhotoRepository,
)

__all__ = [
    "ExcelPersonImportReader",
    "InMemoryFolderRepository",
    "InMemoryPersonRepository",
    "InMemoryPhotoRepository",
    "LocalPhotoFileScanner",
    "PillowPhotoMetadataReader",
    "SQLiteConnectionProvider",
    "SQLiteFolderRepository",
    "SQLitePersonRepository",
    "SQLitePhotoRepository",
    "TxtPersonImportReader",
]
