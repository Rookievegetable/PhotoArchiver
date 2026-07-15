"""Application command objects."""

from photo_archiver.application.commands.import_people import ImportPeopleCommand
from photo_archiver.application.commands.match_persons import MatchPersonsCommand
from photo_archiver.application.commands.register_photo import RegisterPhotoCommand
from photo_archiver.application.commands.scan_and_register_photos import ScanAndRegisterPhotosCommand
from photo_archiver.application.commands.scan_photo_folder import ScanPhotoFolderCommand

__all__ = [
    "ImportPeopleCommand",
    "MatchPersonsCommand",
    "RegisterPhotoCommand",
    "ScanAndRegisterPhotosCommand",
    "ScanPhotoFolderCommand",
]