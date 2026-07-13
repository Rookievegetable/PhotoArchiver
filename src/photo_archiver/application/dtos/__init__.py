"""Application data transfer objects."""

from photo_archiver.application.dtos.import_people import ImportPeopleResult, PersonImportRow
from photo_archiver.application.dtos.photo_scan import PhotoScanItem, ScanPhotoFolderResult
from photo_archiver.application.dtos.register_photo import RegisterPhotoResult
from photo_archiver.application.dtos.scan_and_register_photos import ScanAndRegisterPhotosResult

__all__ = [
    "ImportPeopleResult",
    "PersonImportRow",
    "PhotoScanItem",
    "RegisterPhotoResult",
    "ScanAndRegisterPhotosResult",
    "ScanPhotoFolderResult",
]