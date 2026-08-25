"""Application data transfer objects."""

from photo_archiver.application.dtos.archive import (
    ArchiveOutcome,
    ArchivePlan,
    ArchivePlanItem,
    ArchiveResult,
)
from photo_archiver.application.dtos.duplicates import DuplicateGroup, DuplicateReport
from photo_archiver.application.dtos.export import ExportData, ExportScope
from photo_archiver.application.dtos.import_people import ImportPeopleResult, PersonImportRow
from photo_archiver.application.dtos.photo_scan import PhotoScanItem, ScanPhotoFolderResult
from photo_archiver.application.dtos.plugin_action_result import ActionResult, PluginReport
from photo_archiver.application.dtos.plugin_context import (
    PluginDuplicateGroup,
    PluginDuplicateReport,
    PluginImportPeopleCommand,
    PluginImportPersonRow,
    PluginImportResult,
    PluginPhotoQuery,
    PluginPhotoSummary,
)
from photo_archiver.application.dtos.recognition import (
    FaceDetectionItem,
    FaceDetectionResult,
    FaceRecognitionItem,
    FaceRecognitionResult,
    MatchCandidate,
    MatchResult,
)
from photo_archiver.application.dtos.register_photo import RegisterPhotoResult
from photo_archiver.application.dtos.scan_and_register_photos import ScanAndRegisterPhotosResult
from photo_archiver.application.dtos.settings import (
    DEFAULT_LANGUAGE,
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_MAX_WORKERS,
    DEFAULT_THEME,
    InvalidPreferencesError,
    MAX_MATCH_THRESHOLD,
    MAX_MAX_WORKERS,
    MIN_MATCH_THRESHOLD,
    MIN_MAX_WORKERS,
    UserPreferences,
    VALID_LANGUAGES,
    VALID_THEMES,
    validate_preferences,
)

__all__ = [
    "ArchiveOutcome",
    "ArchivePlan",
    "ArchivePlanItem",
    "ArchiveResult",
    "DEFAULT_LANGUAGE",
    "DEFAULT_MATCH_THRESHOLD",
    "DEFAULT_MAX_WORKERS",
    "DEFAULT_THEME",
    "DuplicateGroup",
    "DuplicateReport",
    "ExportData",
    "ActionResult",
    "ExportScope",
    "FaceDetectionItem",
    "FaceDetectionResult",
    "FaceRecognitionItem",
    "FaceRecognitionResult",
    "ImportPeopleResult",
    "InvalidPreferencesError",
    "MAX_MATCH_THRESHOLD",
    "MAX_MAX_WORKERS",
    "MIN_MATCH_THRESHOLD",
    "MIN_MAX_WORKERS",
    "MatchCandidate",
    "MatchResult",
    "PersonImportRow",
    "PhotoScanItem",
    "PluginDuplicateGroup",
    "PluginDuplicateReport",
    "PluginImportPeopleCommand",
    "PluginImportPersonRow",
    "PluginImportResult",
    "PluginPhotoQuery",
    "PluginPhotoSummary",
    "PluginReport",
    "RegisterPhotoResult",
    "ScanAndRegisterPhotosResult",
    "ScanPhotoFolderResult",
    "UserPreferences",
    "VALID_LANGUAGES",
    "VALID_THEMES",
    "validate_preferences",
]