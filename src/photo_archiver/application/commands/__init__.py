"""Application command objects."""

from photo_archiver.application.commands.archive import ArchivePhotosCommand
from photo_archiver.application.commands.backfill_capture_time import BackfillCaptureTimeCommand
from photo_archiver.application.commands.deletion import (
    DeletePersonCommand,
    DeletePhotosCommand,
    DisposeDuplicatesCommand,
    PruneMissingCommand,
)
from photo_archiver.application.commands.import_draft import (
    ConfirmImportCommand,
    ParseImportDraftCommand,
    ReparseImportDraftCommand,
)
from photo_archiver.application.commands.import_people import ImportPeopleCommand
from photo_archiver.application.commands.match_persons import MatchPersonsCommand
from photo_archiver.application.commands.people_admin import (
    AddPersonCommand,
    EditPersonCommand,
    ReorderPeopleCommand,
)
from photo_archiver.application.commands.register_photo import RegisterPhotoCommand
from photo_archiver.application.commands.scan_and_register_photos import ScanAndRegisterPhotosCommand
from photo_archiver.application.commands.scan_photo_folder import ScanPhotoFolderCommand
from photo_archiver.application.commands.start_recognition_run import StartRecognitionRunCommand

__all__ = [
    "AddPersonCommand",
    "ArchivePhotosCommand",
    "BackfillCaptureTimeCommand",
    "DeletePersonCommand",
    "DeletePhotosCommand",
    "DisposeDuplicatesCommand",
    "EditPersonCommand",
    "ConfirmImportCommand",
    "ImportPeopleCommand",
    "ParseImportDraftCommand",
    "ReparseImportDraftCommand",
    "MatchPersonsCommand",
    "PruneMissingCommand",
    "RegisterPhotoCommand",
    "ReorderPeopleCommand",
    "ScanAndRegisterPhotosCommand",
    "ScanPhotoFolderCommand",
    "StartRecognitionRunCommand",
]