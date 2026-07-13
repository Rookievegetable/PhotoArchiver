"""Application runtime context."""

from dataclasses import dataclass

from photo_archiver.app.repositories import ApplicationRepositories
from photo_archiver.app.services import ApplicationServices
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.workers import QtWorkerExecutor


@dataclass(frozen=True, slots=True)
class ApplicationContext:
    """Container for objects assembled during application startup."""

    settings: AppSettings
    repositories: ApplicationRepositories
    services: ApplicationServices
    worker_executor: QtWorkerExecutor
