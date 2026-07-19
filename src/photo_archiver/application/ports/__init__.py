"""Application ports implemented by infrastructure adapters."""

from photo_archiver.application.ports.archive_path_builder import ArchivePathBuilder
from photo_archiver.application.ports.face_detector import FaceDetector
from photo_archiver.application.ports.face_recognizer import FaceRecognizer
from photo_archiver.application.ports.person_import_reader import PersonImportReader
from photo_archiver.application.ports.person_matcher import PersonMatcher
from photo_archiver.application.ports.photo_file_scanner import PhotoFileScanner
from photo_archiver.application.ports.photo_metadata_reader import PhotoMetadataReader
from photo_archiver.application.ports.progress_reporter import ProgressReporter
from photo_archiver.application.ports.system_settings import SystemSettings
from photo_archiver.application.ports.thumbnail_cache import ThumbnailCache
from photo_archiver.application.ports.thumbnail_generator import ThumbnailGenerator
from photo_archiver.application.ports.unit_of_work import UnitOfWork
from photo_archiver.application.ports.user_settings_store import UserSettingsStore

__all__ = [
    "ArchivePathBuilder",
    "FaceDetector",
    "FaceRecognizer",
    "PersonImportReader",
    "PersonMatcher",
    "PhotoFileScanner",
    "PhotoMetadataReader",
    "ProgressReporter",
    "SystemSettings",
    "ThumbnailCache",
    "ThumbnailGenerator",
    "UnitOfWork",
    "UserSettingsStore",
]