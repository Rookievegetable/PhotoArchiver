"""Presentation controllers for PhotoArchiver UI."""

from photo_archiver.presentation.controllers.archive_controller import ArchiveController
from photo_archiver.presentation.controllers.detect_duplicates_controller import (
    DetectDuplicatesController,
)
from photo_archiver.presentation.controllers.export_controller import ExportController
from photo_archiver.presentation.controllers.import_people_controller import ImportPeopleController
from photo_archiver.presentation.controllers.match_persons_controller import MatchPersonsController
from photo_archiver.presentation.controllers.photo_list_controller import PhotoListController
from photo_archiver.presentation.controllers.review_controller import ReviewController
from photo_archiver.presentation.controllers.scan_controller import ScanController
from photo_archiver.presentation.controllers.settings_controller import SettingsController

__all__ = [
    "ArchiveController",
    "DetectDuplicatesController",
    "ExportController",
    "ImportPeopleController",
    "MatchPersonsController",
    "PhotoListController",
    "ReviewController",
    "ScanController",
    "SettingsController",
]
