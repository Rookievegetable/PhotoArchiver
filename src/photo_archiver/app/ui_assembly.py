"""UI controller assembly for PhotoArchiver presentation layer.

Centralizes ReviewController + PhotoListController + SettingsController wiring
(thumbnail cache, generator, repositories, QSettings-backed user preferences
store) in one module so app/bootstrap.py stays focused on the startup sequence
rather than Qt controller construction details.

Step 13: SettingsController is built here (not in MainWindow) so the QSettings
adapter is constructed once per application lifetime and the controller can be
passed down to any UI surface that wants to open the SettingsDialog. The
SettingsService assembled in ``app/services.py`` is REBOUND to a
QSettings-backed store here — the InMemory store from the bootstrap path keeps
CLI / CI / unit tests working without a Qt runtime.
"""

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings

from photo_archiver.app.repositories import ApplicationRepositories
from photo_archiver.app.services import ApplicationServices
from photo_archiver.application import SettingsService
from photo_archiver.application.ports.system_settings import SystemSettings
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.infrastructure.config.settings import DEFAULT_APP_NAME
from photo_archiver.infrastructure.exporters import (
    CsvExporter,
    ExcelExporter,
    HtmlExporter,
)
from photo_archiver.infrastructure.image import PillowThumbnailGenerator, ThumbnailCache
from photo_archiver.infrastructure.persistence.qsettings_user_settings_store import (
    QSettingsUserSettingsStore,
)
from photo_archiver.presentation.controllers import (
    DetectDuplicatesController,
    ExportController,
    PhotoListController,
    ReviewController,
    SettingsController,
)
from photo_archiver.workers import QtWorkerExecutor

# QSettings organization / application names mirror AppSettings.app_name SSOT
# (review m-5: avoid hard-coded duplicates of DEFAULT_APP_NAME).


@dataclass(frozen=True, slots=True)
class UIControllers:
    """UI-facing controllers assembled for runtime."""

    review: ReviewController
    photo_list: PhotoListController
    settings: SettingsController
    export: ExportController
    detect_duplicates: DetectDuplicatesController


class _AppSettingsSystemSettings(SystemSettings):
    """Adapter exposing ``AppSettings`` runtime values through the SystemSettings port.

    ``AppSettings`` is the SSOT for system-level configuration (env / .env).
    Application services that need to fall back to system defaults when a user
    preference has never been set receive this adapter rather than the full
    ``AppSettings`` concrete class, keeping the Application → Infrastructure
    dependency at the Protocol boundary per DEP-012/DEP-013.

    The adapter is a thin forwarding layer (review m-12 flagged it as candidate
    for removal). It is retained because ``AppSettings`` is a pydantic-settings
    model with many fields the SystemSettings port must NOT expose (database_url,
    debug, etc.) — direct implementation would leak the whole surface to
    Application. The 2-property cost is the price of that isolation.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Initialize the adapter with the loaded application settings."""
        self._settings = settings

    @property
    def match_threshold(self) -> float:
        """Return the system-level match threshold fallback."""
        return self._settings.match_threshold

    @property
    def max_workers(self) -> int:
        """Return the system-level worker concurrency fallback."""
        return self._settings.max_workers


def build_ui_controllers(
    services: ApplicationServices,
    repositories: ApplicationRepositories,
    settings: AppSettings,
    worker_executor: QtWorkerExecutor | None = None,
) -> UIControllers:
    """Build ReviewController, PhotoListController, and SettingsController from runtime parts.

    ThumbnailCache root is settings.output_root / "thumbnails" — falls back
    to a system temp dir when output_root is None so the UI still works in
    minimal test contexts without a configured output root.

    Step 13: the SettingsService assembled in ``app/services.py`` with an
    InMemoryUserSettingsStore is rebound here to a QSettings-backed store so
    the desktop runtime persists user overrides in the platform-native
    location. The service instance identity is preserved so any caller that
    already captured ``services.settings`` sees the rebound store.
    """
    thumbnail_root = (
        settings.output_root / "thumbnails"
        if settings.output_root is not None
        else Path.home() / ".photo_archiver" / "thumbnails"
    )
    thumbnail_cache = ThumbnailCache(thumbnail_root)
    thumbnail_generator = PillowThumbnailGenerator(thumbnail_cache)

    _rebind_settings_service_to_qsettings(services.settings, settings)

    return UIControllers(
        review=ReviewController(
            services.review_recognition,  # type: ignore[arg-type]
            repositories.recognition,
        ),
        photo_list=PhotoListController(
            repositories.photos,
            thumbnail_cache,
            thumbnail_generator,
            search_service=services.search_photos,
        ),
        settings=SettingsController(services.settings),
        export=ExportController(
            service=services.export,
            exporter=ExcelExporter(),
            executor=worker_executor,  # type: ignore[arg-type]  # QtWorkerExecutor | None resolved by runtime caller
            # 阶段 1b 修复（ISSUE-016）：format→Exporter 注册表迁 app 装配层
            # （ui_assembly 持具体 Exporter 实例化——装配层职责合理），
            # ExportController 仅依赖 Exporter Protocol + format_name（DEP-002 守护）。
            exporters={
                "xlsx": ExcelExporter(),
                "csv": CsvExporter(),
                "html": HtmlExporter(),
            },
        ),
        detect_duplicates=DetectDuplicatesController(
            service=services.detect_duplicates,
        ),
    )


def _rebind_settings_service_to_qsettings(
    settings_service: SettingsService,
    app_settings: AppSettings,
) -> None:
    """Swap the bootstrap InMemoryUserSettingsStore for a QSettings-backed one.

    Called only from ``build_ui_controllers`` so the QSettings dependency stays
    inside the UI assembly module (Presentation / app layer). The service's
    system fallback is also wired to ``AppSettings`` here so unset user
    preferences inherit the system-level bounds at runtime.

    Implementation note: ``SettingsService`` does not expose a public setter for
    the store; reaching into ``_user_settings_store`` is deliberate — the
    bootstrap path always constructs the service with an InMemory placeholder
    so this rebind happens exactly once per process, before any UI surface can
    observe the store.
    """
    qsettings = QSettings(DEFAULT_APP_NAME, app_settings.app_name)
    settings_service.rebind_store(
        QSettingsUserSettingsStore(qsettings),
        _AppSettingsSystemSettings(app_settings),
    )
