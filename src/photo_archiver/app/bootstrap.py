"""Application startup and dependency assembly."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sqlite3

from loguru import logger

from photo_archiver.app.context import ApplicationContext
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.app.services import build_application_services
from photo_archiver.app.ui_assembly import build_ui_controllers
from photo_archiver.application.ports import PluginContext
from photo_archiver.application.services import PluginContextService
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.infrastructure.database.alembic_runner import run_alembic_migrations
from photo_archiver.infrastructure.database.integrity import (
    CorruptedDatabaseError,
    verify_database_integrity,
)
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


def cwd_dependent_path_warnings(settings: AppSettings) -> list[str]:
    """Return warnings for configured paths that depend on the launch directory.

    P0-9 (D-B5): full path anchoring was deferred to P1 — this round only
    makes the risk visible. A relative configured path resolves against the
    *current working directory*, so launching from a different directory
    silently switches databases, outputs, models, and logs.

    Returns:
        One human-readable Chinese warning per CWD-relative configured path.
    """
    warnings: list[str] = []
    database_path = settings.database_path
    if str(database_path) != ":memory:" and not database_path.is_absolute():
        warnings.append(
            f"数据库路径随启动目录变化：{database_path}"
            f"（本次解析为 {database_path.resolve()}）。"
            "从不同目录启动将创建/使用另一个数据库；"
            "建议在 .env 中将 DATABASE_URL 配置为绝对路径。"
        )
    for label, value in (
        ("模型目录", settings.model_path),
        ("输出目录", settings.output_root),
        ("照片根目录", settings.photo_root),
        ("归档根目录", settings.archive_root),
        ("日志目录", settings.log_directory),
        ("插件目录", settings.plugins_directory),
    ):
        if value is not None and not value.is_absolute():
            warnings.append(
                f"{label}随启动目录变化：{value}（本次解析为 {value.resolve()}）。"
            )
    return warnings


def legacy_database_migration_hints(settings: AppSettings) -> list[str]:
    """Detect a legacy CWD database when the anchored default takes over.

    Phase F F-2（ADR-035）：默认数据库已锚定用户数据目录。仅在 ``database_url``
    未被显式配置（init/env/.env 均未提供，经 ``model_fields_set`` 判定）时
    检查：若启动目录下存在旧默认位置的库而锚定位置还没有库 → 打印迁移引导。
    **绝不自动搬库**（数据安全原则——搬迁由用户手动完成或后续 migrate 子命令）。

    Returns:
        One human-readable Chinese hint when a legacy database is detected.
    """
    if "database_url" in settings.model_fields_set:
        return []
    anchored = settings.database_path
    if str(anchored) == ":memory:" or anchored.is_file():
        return []
    legacy = Path.cwd() / "data" / "photo_archiver.db"
    if not legacy.is_file():
        return []
    return [
        f"检测到旧版启动目录下的数据库：{legacy}。"
        f"自 v2.4.0 起默认数据库已锚定到用户数据目录：{anchored}。"
        "如需沿用旧数据，请关闭程序后将上述旧库文件移动到锚定位置，"
        "或在 .env 中将 DATABASE_URL 配置为指向旧库的绝对路径。"
    ]


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
    # P0-9（D-B5）：完整路径锚定降级为 P1——本轮仅启动警告，使"CWD 相对路径"
    # 的数据位置风险可见（尤其是数据库：换目录启动会静默换库）。
    for path_warning in cwd_dependent_path_warnings(resolved_settings):
        logger.warning(path_warning)
    # Phase F F-2（ADR-035）：默认路径已锚定用户数据目录——检测旧 CWD 库并
    # 打印迁移引导（不自动搬库，数据安全原则）。
    for migration_hint in legacy_database_migration_hints(resolved_settings):
        logger.warning(migration_hint)
    try:
        # P0-6（D-B4）：损坏库在任何写入/迁移路径之前快速失败——只读
        # quick_check，绝不重建/换库；分类见 infrastructure.database.integrity。
        verify_database_integrity(resolved_settings.database_path)
        repositories = build_sqlite_repositories(resolved_settings.database_path)
        run_alembic_migrations(resolved_settings.database_path)
        services = build_application_services(repositories, resolved_settings)
    except sqlite3.DatabaseError as error:
        # 防御纵深：quick_check 漏过的 SQLite 层失败（user_version PRAGMA /
        # 迁移中的 file is not a database 等）归一为同一友好失败类型。
        logger.exception(
            "Database access failed during startup at {}",
            resolved_settings.database_path,
        )
        raise CorruptedDatabaseError(
            resolved_settings.database_path, [str(error)]
        ) from error
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
