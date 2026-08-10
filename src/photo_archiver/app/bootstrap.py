"""Application startup and dependency assembly."""

from importlib.metadata import PackageNotFoundError, version

from loguru import logger

from photo_archiver.app.context import ApplicationContext
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.app.services import build_application_services
from photo_archiver.app.ui_assembly import build_ui_controllers
from photo_archiver.application.dtos import DuplicateReport
from photo_archiver.application.ports import PluginContext
from photo_archiver.application.services import (
    DetectDuplicatesService,
    SearchPhotosService,
)
from photo_archiver.domain import Photo, PhotoSearchCriteria
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.infrastructure.database.alembic_runner import run_alembic_migrations
from photo_archiver.infrastructure.logging import configure_logging, log_application_startup
from photo_archiver.workers import QtWorkerExecutor

PACKAGE_NAME = "photo-archiver"
DEVELOPMENT_VERSION = "0.0.0.dev"


class _ReadOnlyPluginContext:
    """Concrete PluginContext impl wiring two read-only Application services.

    Module-level private class (review Major-1/Minor-4 fix):补完整类型注解让
    mypy 真核 PluginContext Protocol 呑约（删 type:ignore[assignment]），提为
    模块级免每次 bootstrap 重定义 + 难测 + 不可复用。
    """

    def __init__(
        self,
        search_service: SearchPhotosService,
        duplicates_service: DetectDuplicatesService,
    ) -> None:
        """Wire the two read-only Application services exposed to plugins."""
        self._search = search_service
        self._duplicates = duplicates_service

    def search_photos(self, criteria: PhotoSearchCriteria) -> list[Photo]:
        """Delegate to SearchPhotosService.execute — read-only photo query."""
        return self._search.execute(criteria)

    def detect_duplicates(self) -> DuplicateReport:
        """Delegate to DetectDuplicatesService.execute — read-only duplicate report."""
        return self._duplicates.execute()


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
        run_alembic_migrations(resolved_settings.database_path)
        services = build_application_services(repositories, resolved_settings)
    except Exception:
        logger.exception(
            "Failed to initialize application dependencies at {}",
            resolved_settings.database_path,
        )
        raise
    worker_executor = QtWorkerExecutor()
    ui_controllers = build_ui_controllers(services, repositories, resolved_settings, worker_executor)
    # B5 v2 收敛：构造只读 PluginContext（search_photos + detect_duplicates），
    # 注入 ApplicationContext 供 MainWindow PluginRegistry 装配时透传给 plugin.enable()。
    # 模块级 _ReadOnlyPluginContext 类补完整类型注解——mypy 真核 Protocol 呑约无需 type:ignore。
    plugin_context: PluginContext = _ReadOnlyPluginContext(
        services.search_photos,
        services.detect_duplicates,
    )
    return ApplicationContext(
        settings=resolved_settings,
        repositories=repositories,
        services=services,
        worker_executor=worker_executor,
        review_controller=ui_controllers.review,
        photo_list_controller=ui_controllers.photo_list,
        settings_controller=ui_controllers.settings,
        export_controller=ui_controllers.export,
        detect_duplicates_controller=ui_controllers.detect_duplicates,
        plugin_context=plugin_context,
    )
