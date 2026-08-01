"""Application runtime context."""

from dataclasses import dataclass

from photo_archiver.app.repositories import ApplicationRepositories
from photo_archiver.app.services import ApplicationServices
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.controllers import (
    DetectDuplicatesController,
    ExportController,
    PhotoListController,
    ReviewController,
    SettingsController,
)
from photo_archiver.workers import QtWorkerExecutor


@dataclass(frozen=True, slots=True)
class ApplicationContext:
    """Container for objects assembled during application startup."""

    settings: AppSettings
    repositories: ApplicationRepositories
    services: ApplicationServices
    worker_executor: QtWorkerExecutor
    review_controller: ReviewController
    photo_list_controller: PhotoListController
    settings_controller: SettingsController
    export_controller: ExportController
    detect_duplicates_controller: DetectDuplicatesController
