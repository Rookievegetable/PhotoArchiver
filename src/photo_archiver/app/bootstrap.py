"""Application startup and dependency assembly."""

from importlib.metadata import PackageNotFoundError, version

from loguru import logger

from photo_archiver.app.context import ApplicationContext
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.app.services import build_application_services
from photo_archiver.app.ui_assembly import build_ui_controllers
from photo_archiver.application.ports import PluginContext
from photo_archiver.application.services import PluginContextService
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.infrastructure.database.alembic_runner import run_alembic_migrations
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
    # 阶段 1 加固（ADR-026）：PluginContextService 替旧 _ReadOnlyPluginContext——
    # Domain ↔ Plugin DTO 映射编排 + 联查 RecognitionRepository 取 match_status
    # （4 态含 none）。bootstrap 不含业务 DTO 转换逻辑（属 Application Service 职责）。
    # 阶段 3 写能力（ADR-028）：注入 ImportPeopleService——插件经
    # PluginContext.import_people 导入人员实体（唯一写路径，export 续暂缓）。
    plugin_context: PluginContext = PluginContextService(
        services.search_photos,
        services.detect_duplicates,
        repositories.recognition,
        services.import_people,
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
