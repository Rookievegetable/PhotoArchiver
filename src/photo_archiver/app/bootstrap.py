"""Application startup and dependency assembly."""

from importlib.metadata import PackageNotFoundError, version

from loguru import logger

from photo_archiver.app.context import ApplicationContext
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.app.services import build_application_services
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.infrastructure.logging import configure_logging, log_application_startup
from photo_archiver.workers import QtWorkerExecutor

PACKAGE_NAME = "photo-archiver"
DEVELOPMENT_VERSION = "0.0.0.dev"


def resolve_app_version(settings: AppSettings) -> str:
    """Resolve the runtime application version.

    Args:
        settings: Loaded application settings.

    Returns:
        Installed package version when available; otherwise configured fallback.
    """
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return settings.app_version or DEVELOPMENT_VERSION


def bootstrap_application(settings: AppSettings | None = None) -> ApplicationContext:
    """Load settings, initialize logging, and build the application context.

    Args:
        settings: Optional pre-loaded settings, mainly for tests.

    Returns:
        Application context used to construct the desktop application.
    """
    resolved_settings = settings or AppSettings()
    resolved_settings.ensure_runtime_directories()
    configure_logging(resolved_settings.to_logging_config())
    log_application_startup(
        name=resolved_settings.app_name,
        version=resolve_app_version(resolved_settings),
        environment=resolved_settings.env,
    )
    try:
        repositories = build_sqlite_repositories(resolved_settings.database_path)
        services = build_application_services(repositories)
    except Exception:
        logger.exception(
            "Failed to initialize application dependencies at {}",
            resolved_settings.database_path,
        )
        raise
    worker_executor = QtWorkerExecutor()
    return ApplicationContext(
        settings=resolved_settings,
        repositories=repositories,
        services=services,
        worker_executor=worker_executor,
    )
