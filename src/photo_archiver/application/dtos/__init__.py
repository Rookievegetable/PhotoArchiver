"""Application data transfer objects."""

from photo_archiver.application.dtos.archive import (
    ArchiveOutcome,
    ArchivePlan,
    ArchivePlanItem,
    ArchiveResult,
)
from photo_archiver.application.dtos.import_people import ImportPeopleResult, PersonImportRow
from photo_archiver.application.dtos.photo_scan import PhotoScanItem, ScanPhotoFolderResult
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

__all__ = [
    "ArchiveOutcome",
    "ArchivePlan",
    "ArchivePlanItem",
    "ArchiveResult",
    "FaceDetectionItem",
    "FaceDetectionResult",
    "FaceRecognitionItem",
    "FaceRecognitionResult",
    "ImportPeopleResult",
    "MatchCandidate",
    "MatchResult",
    "PersonImportRow",
    "PhotoScanItem",
    "RegisterPhotoResult",
    "ScanAndRegisterPhotosResult",
    "ScanPhotoFolderResult",
]