"""Main application window — Batch 3 flow-driven workbench.

Layout: left navigation (overview / photo library / review center /
data tools / settings) beside a QStackedWidget of reusable pages; a
window-level toolbar keeps the five frequent primary actions visible on
every page, and the status bar keeps the task panel (progress, message,
cancel) permanently visible. Maintenance entries (export, duplicate
detection, person deletion) live on the data-tools page; settings is a
navigation entry.

每个页面动作接对应 controller，长耗时走 QtWorkerExecutor，短耗时
（review approve/reject、archive preview）同步调。所有动作经
TaskCoordinator 全局准入（Batch 1）。
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from pathlib import Path
from uuid import UUID
from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QLabel,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QToolButton,
    QListView,
    QVBoxLayout,
    QWidget,
)

from loguru import logger

if TYPE_CHECKING:
    from photo_archiver.app.context import ApplicationContext
from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.application.dtos.plugin_action_result import ActionResult
from photo_archiver.domain import Photo, PhotoSearchCriteria
from photo_archiver.presentation.controllers import (
    ArchiveController,
    ImportPeopleController,
    MatchPersonsController,
    ScanController,
)
from photo_archiver.presentation.controllers.overview_presenter import (
    OverviewPresenter,
)
from photo_archiver.presentation.controllers.workspace_controller import (
    ActionGuidance, WorkspaceController,
)
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.task_coordinator import TaskCoordinator
from photo_archiver.presentation.views.overview_page import OverviewPage
from photo_archiver.presentation.ui_text import (
    STATUS_OPERATION_FAILED,
    STATUS_REFRESH_FAILED,
    STATUS_PROGRESS_UNKNOWN,
    STATUS_TASK_BUSY,
    STATUS_TASK_CANCEL_PROGRESS,
    STATUS_TASK_PREPARING,
    STATUS_TASK_PROGRESS,
    ACTION_ARCHIVE,
    ACTION_CANCEL_TASK,
    ACTION_DELETE_PERSON,
    ACTION_DELETE_PHOTOS,
    ACTION_DETECT_DUPLICATES,
    ACTION_EXPORT_DATA,
    ACTION_IMPORT_PEOPLE,
    ACTION_REVIEW_PENDING,
    ACTION_RUN_FACE_RECOGNITION,
    ACTION_SCAN_FOLDER,
    ACTION_SETTINGS,
    ARCHIVE_DIALOG_TITLE,
    ARCHIVE_NOTHING_TO_ARCHIVE,
    ARCHIVE_ROOT_SETUP_BUTTON,
    ARCHIVE_ROOT_SETUP_CANCEL,
    ARCHIVE_ROOT_SETUP_PROMPT,
    DELETE_FAILED_MESSAGE,
    DELETE_FAILED_TITLE,
    DELETE_PHOTOS_DONE,
    DELETE_PHOTOS_DONE_TITLE,
    DELETE_PHOTOS_NO_SELECTION,
    DELETE_PHOTOS_NO_SELECTION_TITLE,
    DIALOG_SELECT_PEOPLE_FILE,
    DIALOG_SELECT_PHOTO_FOLDER,
    MAIN_WINDOW_TITLE,
    PEOPLE_FILE_FILTER,
    PERSON_DELETE_DONE,
    PERSON_DELETE_DIALOG_TITLE,
    PLUGIN_ACTION_FAILED,
    PLUGIN_ERROR_TITLE,
    PLUGIN_FAILURE_NO_DETAIL,
    PLUGIN_RESULT_TITLE,
    STATUS_ARCHIVING,
    STATUS_CANCELLING,
    STATUS_CANCEL_FAILED,
    STATUS_EXPORTING,
    STATUS_IMPORT_CONFIRMED,
    STATUS_IMPORT_CONFIRM_ERRORS,
    STATUS_IMPORT_CONFIRM_WORKER,
    STATUS_IMPORT_DRAFT_PARSED,
    IMPORT_PREVIEW_TITLE,
    IMPORT_PREVIEW_EMPTY_FILE,
    STATUS_MATCH_SUMMARY,
    STATUS_MATCH_UNAVAILABLE,
    STATUS_MATCH_UNREADABLE,
    STATUS_PENDING_REVIEW_COUNT,
    STATUS_READY,
    STATUS_SCAN_UNAVAILABLE,
    STATUS_SCANNING_FOLDER,
    STATUS_TASK_CANCELLED,
    STATUS_TASK_COMPLETED,
    STATUS_TASK_FAILED,
    STATUS_TASK_STARTED,
    task_label,
)
from photo_archiver.presentation.views.archive_preview_dialog import ArchivePreviewDialog
from photo_archiver.application.commands import (
    ConfirmImportCommand,
    DeletePersonCommand,
    DeletePhotosCommand,
    ParseImportDraftCommand,
)
from photo_archiver.presentation.views.export_dialog import ExportDialog
from photo_archiver.presentation.views.filter_bar import FilterBar
from photo_archiver.presentation.views.import_preview_dialog import (
    CONFIRM_SYNC_LIMIT,
    ImportPreviewDialog,
)
from photo_archiver.presentation.views.person_deletion_dialog import PersonDeletionDialog
from photo_archiver.presentation.views.people_admin_page import PeopleAdminPage
from photo_archiver.presentation.views.photo_deletion_confirm_dialog import (
    PhotoDeletionConfirmDialog,
)
from photo_archiver.presentation.views.photo_list_delegate import PhotoThumbnailDelegate
from photo_archiver.presentation.views.photo_detail_dialog import PhotoDetailDialog
from photo_archiver.presentation.visual_style import (
    ROLE_DANGER,
    ROLE_PRIMARY,
    assign_role,
    style_empty_state_card,
)
from photo_archiver.presentation.views.plugin_report_dialog import PluginReportDialog
from photo_archiver.presentation.views.photo_list_model import (
    PHOTO_ID_ROLE, PhotoListModel, STATUS_BADGE_ROLE, THUMBNAIL_ROLE,
)
from photo_archiver.presentation.views.review_dialog import ReviewDialog
from photo_archiver.presentation.views.settings_dialog import SettingsDialog
from photo_archiver.plugins import PluginRegistry
from photo_archiver.workers import ConfirmImportTask, QtWorkerRunnable
from photo_archiver.workers.events import (
    TaskCancelled,
    TaskCompleted,
    TaskFailed,
    TaskProgress,
    TaskStarted,
)

DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 800
_PROGRESS_RESOLUTION = 100

# 导航行 ↔ 页面映射：0 概览 / 1 照片库 / 2 人员与分组 / 4 数据工具切页；
# 行 3（审核中心）与行 5（设置）是触发式导航项（打开模态对话框，不切页）。
_NAV_ROW_TO_PAGE = {0: 0, 1: 1, 2: 2, 4: 3}
_PAGE_TO_NAV_ROW = {page: row for row, page in _NAV_ROW_TO_PAGE.items()}
_NAV_LABELS = (
    text.NAV_OVERVIEW, text.NAV_PHOTO_LIBRARY, text.NAV_PEOPLE,
    text.NAV_REVIEW_CENTER, text.NAV_DATA_TOOLS, text.NAV_SETTINGS,
)


def _exclusive(label: str) -> Callable:
    """Reserve admission before modal dialogs, queries or nested GUI dispatch."""
    def decorate(method: Callable) -> Callable:
        @wraps(method)
        def guarded(self: "MainWindow", *args: object, **kwargs: object) -> None:
            reservation = self._task_coordinator.reserve(label)
            if reservation is None:
                self._status.showMessage(
                    STATUS_TASK_BUSY.format(label=self._task_coordinator.label)
                )
                return
            try:
                method(self, *args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - GUI boundary
                logger.exception("GUI operation {} failed", label)
                self._status_label.setText(STATUS_OPERATION_FAILED.format(detail=exc))
                QMessageBox.warning(self, label, STATUS_OPERATION_FAILED.format(detail=exc))
            finally:
                self._task_coordinator.release(reservation)
        return guarded
    return decorate


class MainWindow(QMainWindow):
    """Main window for the PhotoArchiver desktop application.

    The window owns no business logic; it delegates button actions to controllers
    and reflects worker task events in widgets. Step 12 expanded the toolbar
    from scan-only to the full闭环 (import / scan / review / archive) and
    replaced the bare progress placeholder with a photo list.
    """

    def __init__(self, context: ApplicationContext) -> None:
        """Initialize the main window with the runtime application context.

        Args:
            context: Assembled runtime context providing services, worker executor,
                and the controllers assembled in :meth:`_build_controllers`.
        """
        super().__init__()
        self.setWindowTitle(MAIN_WINDOW_TITLE)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self._context = context
        self._task_coordinator = TaskCoordinator(self)
        self._current_criteria: PhotoSearchCriteria | None = None
        self._photos_by_id: dict[UUID, Photo] = {}
        self._action_states: dict[QAction, tuple[bool, str]] = {}
        self._workspace_controller = WorkspaceController(context.services.workspace_readiness)
        self._overview_presenter = OverviewPresenter(self._workspace_controller)
        self._build_controllers()
        self._build_actions()
        self._build_toolbar()
        self._load_plugins()
        self._build_central()
        self._build_status()
        self._task_coordinator.changed.connect(self._on_task_state_changed)
        self._task_coordinator.started.connect(self._on_started)
        self._task_coordinator.progress.connect(self._on_progress)
        self._task_coordinator.terminal.connect(self._on_terminal)
        self._refresh_workspace_state()
        self._on_task_state_changed()

    def _build_controllers(self) -> None:
        """Assemble the four controllers from context services + worker executor."""
        self._scan_controller = ScanController(
            self._context.services.scan_and_register_photos,
            self._context.worker_executor,
            parent=self,
        )
        self._import_controller = ImportPeopleController(
            self._context.services.import_people,
            self._context.worker_executor,
            parent=self,
        )
        # review M-3 fix: ArchiveController holds the UseCase only; preview()
        # delegates through the UseCase Protocol so no _planner reflection.
        self._archive_controller = ArchiveController(
            self._context.services.archive_photos,
            self._context.worker_executor,
            parent=self,
        )
        # Phase 4.2 Commit 3: MatchPersonsController is worker-backed and needs
        # the recognition repos + match service + worker executor, so it is
        # built here like Scan/Import/Archive (view-site constructor injection).
        # The model pack is optional at bootstrap — a missing pack surfaces as
        # TaskFailed during execution, never blocking window construction.
        self._match_controller = MatchPersonsController(
            photos=self._context.repositories.photos,
            people=self._context.repositories.people,
            recognition=self._context.repositories.recognition,
            use_case=self._context.services.match_persons,  # type: ignore[arg-type]  # MatchPersonsService satisfies the MatchPersonsUseCase protocol
            executor=self._context.worker_executor,
            parent=self,
        )
        self._review_controller = self._context.review_controller  # set by bootstrap
        self._photo_list_controller = self._context.photo_list_controller  # set by bootstrap
        self._settings_controller = self._context.settings_controller  # set by bootstrap (Step 13)
        self._export_controller = self._context.export_controller  # already assembled in ui_assembly (ISSUE-016 fixed)

    def _build_actions(self) -> None:
        """Create every window action once; placement happens per page.

        Instances stay on ``self`` so tests and pages address stable handles;
        the five primary flow actions land on the window-level ``Main``
        toolbar, maintenance actions on the data-tools page, delete-selection
        on the photo-library page, settings on the navigation, and cancel in
        the status bar (Batch 3 information architecture).
        """
        # 流程序主操作：导入 → 扫描 → 识别 → 审核 → 归档。
        self._import_action = QAction(ACTION_IMPORT_PEOPLE, self)
        self._import_action.triggered.connect(self._on_import_clicked)
        self._scan_action = QAction(ACTION_SCAN_FOLDER, self)
        self._scan_action.triggered.connect(self._on_scan_clicked)
        self._match_action = QAction(ACTION_RUN_FACE_RECOGNITION, self)
        self._match_action.triggered.connect(self._on_match_clicked)
        self._review_action = QAction(ACTION_REVIEW_PENDING, self)
        self._review_action.triggered.connect(self._on_review_clicked)
        self._archive_action = QAction(ACTION_ARCHIVE, self)
        self._archive_action.triggered.connect(self._on_archive_clicked)
        # 维护操作（数据工具页）。
        self._export_action = QAction(ACTION_EXPORT_DATA, self)
        self._export_action.triggered.connect(self._on_export_clicked)
        self._detect_duplicates_action = QAction(ACTION_DETECT_DUPLICATES, self)
        self._detect_duplicates_action.triggered.connect(
            self._on_detect_duplicates_clicked,
        )
        self._delete_person_action = QAction(ACTION_DELETE_PERSON, self)
        self._delete_person_action.triggered.connect(self._on_delete_person_clicked)
        # 照片库选择态操作（照片库页）。
        self._delete_photos_action = QAction(ACTION_DELETE_PHOTOS, self)
        self._delete_photos_action.triggered.connect(self._on_delete_photos_clicked)
        # 设置（导航项触发；保留 Ctrl+, 快捷键，需挂到窗口）。
        self._settings_action = QAction(ACTION_SETTINGS, self)
        self._settings_action.setShortcut(QKeySequence("Ctrl+,"))
        self._settings_action.triggered.connect(self._on_settings_clicked)
        self.addAction(self._settings_action)
        # 取消（状态栏常驻按钮持有）。
        self._cancel_action = QAction(ACTION_CANCEL_TASK, self)
        self._cancel_action.setEnabled(False)
        self._cancel_action.triggered.connect(self._on_cancel_clicked)
        # 任务运行时置灰的冲突入口全集（Batch 1 语义：置灰 + 原因说明）。
        self._plugin_actions: list[QAction] = []
        self._conflicting_actions = [
            self._import_action, self._scan_action, self._review_action,
            self._archive_action, self._match_action, self._export_action,
            self._detect_duplicates_action, self._delete_photos_action,
            self._delete_person_action, self._settings_action,
        ]

    def _build_toolbar(self) -> None:
        """Create the window-level primary toolbar (frequent flow actions).

        The toolbar keeps objectName ``Main`` — the ADR-038 plugin mount
        contract resolves it via ``findChild(QToolBar, "Main")`` and appends
        one QAction per plugin action. The toolbar lives on the QMainWindow,
        so it stays visible on every navigation page.
        """
        toolbar = QToolBar("Main", self)
        # P0-1: the constructor string above is the toolbar's windowTitle, not
        # its objectName — _add_plugin_actions' findChild(QToolBar, "Main")
        # contract only resolves with an explicit objectName. Without this,
        # plugin actions were silently dropped even once discovery worked.
        toolbar.setObjectName("Main")
        self.addToolBar(toolbar)
        for action in (
            self._import_action, self._scan_action, self._match_action,
            self._review_action, self._archive_action,
        ):
            toolbar.addAction(action)

    def _load_plugins(self) -> None:
        """Construct the plugin registry and load the configured plugin directory.

        ADR-038（ISSUE-020 裁决①，恢复对外承诺）：设置 ``PLUGINS_DIRECTORY``
        指向插件目录时，启动即 ``load_from_path → enable_all →
        _add_plugin_actions``，插件动作挂载到主工具栏；未配置（默认）则保持
        零加载——示例插件（``examples/plugins/``）仍不自动加载，它们是
        plugin-guide / ADR-026 / ADR-028 的演示代码。加载/启用失败由
        PluginRegistry 错误隔离兜底（坏插件跳过、宿主续运行，ADR-026），
        本方法自身不抛异常。
        """
        self._plugin_registry = PluginRegistry(self._context.plugin_context)
        plugins_directory = self._context.settings.plugins_directory
        if plugins_directory is None:
            logger.info("No PLUGINS_DIRECTORY configured — plugins not loaded")
            return
        self._plugin_registry.load_from_path(plugins_directory)
        self._plugin_registry.enable_all()
        self._add_plugin_actions()
        enabled = len(self._plugin_registry.enabled_plugins)
        errors = len(self._plugin_registry.errors)
        logger.info(
            "Plugins loaded from {}: {} enabled, {} error(s), {} toolbar action(s)",
            plugins_directory,
            enabled,
            errors,
            len(self._plugin_actions),
        )

    def _add_plugin_actions(self) -> None:
        """Add one QAction per plugin action item to the main toolbar."""
        toolbar = self.findChild(QToolBar, "Main")  # type: ignore[union-attr]
        if toolbar is None:
            return
        for plugin in self._plugin_registry.enabled_plugins.values():
            for action_def in plugin.actions():
                qaction = QAction(action_def.label, self)
                if action_def.tooltip:
                    qaction.setToolTip(action_def.tooltip)
                pid = action_def.id
                qaction.triggered.connect(lambda checked=False, pid=pid: self._on_plugin_action(pid))
                toolbar.addAction(qaction)
                self._plugin_actions.append(qaction)
                self._conflicting_actions.append(qaction)

    @_exclusive(PLUGIN_RESULT_TITLE.format(action_id="…"))
    def _on_plugin_action(self, action_id: str) -> None:
        """Dispatch a plugin action click to the owning plugin and render the result.

        B5 v2 收敛：宿主渲染动作结果——plugin.execute_action 返 ActionResult，
        宿主据 status 渲染：success → information 对话框 + payload、failure → warning、
        noop → 续查下一个插件（不应出现因 _add_plugin_actions 已按 id 路由）。
        """
        for plugin in self._plugin_registry.enabled_plugins.values():
            ids_in_plugin = {a.id for a in plugin.actions()}
            if action_id not in ids_in_plugin:
                continue
            try:
                result: ActionResult = plugin.execute_action(action_id)
            except Exception:
                logger.exception("Plugin action {} failed", action_id)
                QMessageBox.warning(
                    self,
                    PLUGIN_ERROR_TITLE,
                    PLUGIN_ACTION_FAILED.format(action_id=action_id),
                )
                return
            self._render_plugin_action_result(action_id, result)
            return

    def _render_plugin_action_result(self, action_id: str, result: object) -> None:
        """Render a plugin ActionResult to the user via report dialog or QMessageBox.

        阶段 1 加固（ADR-026）：``payload: Any`` 改为 ``report: PluginReport | None``——
        ``success + report`` → PluginReportDialog 通用只读报告对话框；
        ``success 无 report`` → 信息提示；``failure`` → 警告提示；``noop`` → 续查。
        """
        if not isinstance(result, ActionResult):
            return  # unexpected shape — silently ignore (defensive)
        title = PLUGIN_RESULT_TITLE.format(action_id=action_id)
        if result.status == "success":
            if result.report is not None:
                dialog = PluginReportDialog(result.report, self)
                dialog.exec()  # type: ignore[attr-defined]
            else:
                QMessageBox.information(self, title, result.message)
        elif result.status == "failure":
            body = result.message or PLUGIN_FAILURE_NO_DETAIL
            QMessageBox.warning(self, title, body)
        # noop → 不渲染（_add_plugin_actions 已按 id 路由，不应走到）

    def _build_central(self) -> None:
        """Assemble the left navigation and the four stacked pages."""
        self._nav_list = QListWidget(self)
        for label in _NAV_LABELS:
            self._nav_list.addItem(label)
        self._nav_list.setFixedWidth(150)
        self._nav_list.currentRowChanged.connect(self._on_nav_changed)

        self._pages = QStackedWidget(self)
        self._overview_page = OverviewPage(self)
        self._overview_page.primary_clicked.connect(self._on_overview_primary)
        self._pages.addWidget(self._overview_page)  # index 0: 概览
        self._pages.addWidget(self._build_photo_library_page())  # index 1: 照片库
        self._pages.addWidget(self._build_people_page())  # index 2: 人员与分组
        self._pages.addWidget(self._build_data_tools_page())  # index 3: 数据工具

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.addWidget(self._nav_list)
        layout.addWidget(self._pages, 1)
        self.setCentralWidget(central)
        self._nav_list.setCurrentRow(0)

    def _build_photo_library_page(self) -> QWidget:
        """Build the photo-library page (filter bar, photo wall, selection ops).

        The frequent primary flow stays reachable from the window toolbar;
        this page carries the library-specific surface: filter axis, next-step
        guidance row, the photo wall with its empty state, and the
        selection-scoped delete action (Batch 2 semantics preserved).
        """
        page = QWidget(self)
        layout = QVBoxLayout(page)

        # B2 搜索/筛选：FilterBar 在列表上方，发 criteria_changed → 刷新列表。
        # criteria None 时回退 list_all；否则走 PhotoListController.search_photos。
        self._filter_bar = FilterBar(self)
        self._filter_bar.criteria_changed.connect(self._on_filter_changed)
        layout.addWidget(self._filter_bar)
        guidance_row = QHBoxLayout()
        self._match_next_button = QPushButton(self)
        self._archive_next_button = QPushButton(self)
        for button in (self._match_next_button, self._archive_next_button):
            button.setVisible(False)
            button.clicked.connect(lambda checked=False, button=button: self._on_workspace_next(button))
            guidance_row.addWidget(button)
        guidance_row.addStretch()
        layout.addLayout(guidance_row)

        # 选择态批量操作栏（Batch 4）：仅在有选区时出现，数量明确可见；
        # 无选区时不显示任何危险批量操作（蓝图条 3）。Batch 7 视觉层级：
        # 归档为主操作，移除登记为危险操作。
        bulk_row = QHBoxLayout()
        self._bulk_archive_button = QPushButton(self)
        self._bulk_archive_button.clicked.connect(self._on_archive_clicked)
        assign_role(self._bulk_archive_button, ROLE_PRIMARY)
        self._bulk_delete_button = QPushButton(self)
        self._bulk_delete_button.clicked.connect(self._on_delete_photos_clicked)
        assign_role(self._bulk_delete_button, ROLE_DANGER)
        for button in (self._bulk_archive_button, self._bulk_delete_button):
            button.setVisible(False)
            bulk_row.addWidget(button)
        bulk_row.addStretch()
        layout.addLayout(bulk_row)

        self._photo_list_model = PhotoListModel(parent=self)
        self._photo_list = QListView(self)
        self._photo_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._photo_list.setModel(self._photo_list_model)
        self._photo_list.selectionModel().selectionChanged.connect(self._render_workspace_actions)
        self._photo_list_model.modelReset.connect(self._render_workspace_actions)
        # 照片墙网格布局（2026-09-06 桌面感知抽查反馈）：换行流式多列排列，
        # 单元格与委托 sizeHint 匹配（160px 缩略框 + 文件名条）。
        self._photo_list.setViewMode(QListView.ViewMode.IconMode)
        self._photo_list.setFlow(QListView.Flow.LeftToRight)
        self._photo_list.setWrapping(True)
        self._photo_list.setResizeMode(QListView.ResizeMode.Adjust)
        self._photo_list.setUniformItemSizes(True)
        self._photo_list.setGridSize(QSize(184, 202))
        self._photo_list.setSpacing(8)
        # P0-2: install the thumbnail delegate — the THUMBNAIL_ROLE consumer.
        # Without it the default delegate renders filenames only, leaving the
        # entire thumbnail pipeline invisible to the user.
        self._photo_list.setItemDelegate(PhotoThumbnailDelegate(self._photo_list))
        # ADR-036 → Batch 4：空态三态——库中无照片（CTA 扫描）/ 筛选无结果
        # （CTA 清除筛选）/ 任务中（进度说明），绝不混淆两种"没有照片"。
        self._photo_list_stack = QStackedWidget(self)
        self._photo_list_stack.addWidget(self._photo_list)  # index 0: 照片墙
        empty_library = QWidget(self)
        style_empty_state_card(empty_library)
        empty_library_layout = QVBoxLayout(empty_library)
        library_title = QLabel(text.PHOTO_EMPTY_LIBRARY_TITLE, empty_library)
        library_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        library_title.setWordWrap(True)
        self._empty_scan_button = QPushButton(text.PHOTO_EMPTY_LIBRARY_ACTION, empty_library)
        assign_role(self._empty_scan_button, ROLE_PRIMARY)
        self._empty_scan_button.clicked.connect(self._on_scan_clicked)
        empty_library_layout.addStretch(1)
        empty_library_layout.addWidget(library_title)
        empty_library_layout.addWidget(
            self._empty_scan_button, 0, Qt.AlignmentFlag.AlignHCenter,
        )
        empty_library_layout.addStretch(1)
        self._photo_list_stack.addWidget(empty_library)  # index 1: 库中无照片
        empty_filtered = QWidget(self)
        style_empty_state_card(empty_filtered)
        empty_filtered_layout = QVBoxLayout(empty_filtered)
        filtered_title = QLabel(text.PHOTO_EMPTY_FILTERED_TITLE, empty_filtered)
        filtered_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        filtered_title.setWordWrap(True)
        self._empty_clear_button = QPushButton(text.PHOTO_EMPTY_FILTERED_ACTION, empty_filtered)
        self._empty_clear_button.clicked.connect(self._filter_bar.clear)
        empty_filtered_layout.addStretch(1)
        empty_filtered_layout.addWidget(filtered_title)
        empty_filtered_layout.addWidget(
            self._empty_clear_button, 0, Qt.AlignmentFlag.AlignHCenter,
        )
        empty_filtered_layout.addStretch(1)
        self._photo_list_stack.addWidget(empty_filtered)  # index 2: 筛选无结果
        busy_label = QLabel(text.PHOTO_EMPTY_BUSY, self)
        busy_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        busy_label.setWordWrap(True)
        self._photo_list_stack.addWidget(busy_label)  # index 3: 任务中
        layout.addWidget(self._photo_list_stack)

        # Batch 4：双击照片打开只读详情（大预览 + 元数据，无同步原图 IO）。
        self._photo_list.doubleClicked.connect(self._on_photo_double_clicked)

        # Wire thumbnail loads → model now that _photo_list_model exists.
        self._photo_list_controller.thumbnail_loaded.connect(
            self._photo_list_model.set_thumbnail,
        )
        # 空态随模型行数联动（load_photos 走 model reset，删除/导入走行增删）。
        for signal in (
            self._photo_list_model.modelReset,
            self._photo_list_model.rowsInserted,
            self._photo_list_model.rowsRemoved,
        ):
            signal.connect(self._update_photo_empty_state)
        self._update_photo_empty_state()
        # Phase 9 FEAT-P9-2: feed the person axis from the Application layer.
        # Deliberately last: set_persons re-emits criteria, and the photo-list
        # refresh it triggers requires _photo_list_model to exist. Re-populated
        # after each people import completes (see _on_completed).
        self._refresh_filter_persons()
        return page

    def _build_people_page(self) -> QWidget:
        """Build the people-and-grouping page (stage B, D5).

        The roster page owns its edit surface (add/edit/delete via the existing
        danger-confirm dialog, drag reorder) and reports mutations through
        ``people_changed`` so the window refreshes the person filter axis and
        the readiness snapshot. The page only calls Application services
        (DEP-010); business rules stay in ``ManagePeopleService``.
        """
        page = PeopleAdminPage(
            self._context.services.manage_people,
            self._context.services.list_persons,
            self._context.services.delete_person,
            parent=self,
        )
        page.people_changed.connect(self._on_people_changed)
        self._people_admin_page = page
        return page

    def _on_people_changed(self) -> None:
        """Reflect a roster mutation across the window (filter axis, overview)."""
        page = self._pages.widget(2)
        message = page.last_message() if isinstance(page, PeopleAdminPage) else ""
        if message:
            self._status_label.setText(message)
        self._refresh_filter_persons()
        self._refresh_workspace_state()

    def _build_data_tools_page(self) -> QWidget:
        """Build the data-tools page (maintenance entries, Batch 3 IA).

        Decision 4 (owner 2026-09-18): export, duplicate detection and person
        deletion leave the primary toolbar and live here; each keeps its
        existing guarded handler and TaskCoordinator admission.
        """
        page = QWidget(self)
        layout = QVBoxLayout(page)
        bar = QToolBar(self)
        bar.setObjectName("DataTools")
        for action in (
            self._export_action, self._detect_duplicates_action,
            self._delete_person_action,
        ):
            bar.addAction(action)
        layout.addWidget(bar)
        hint = QLabel(text.NAV_DATA_TOOLS_HINT, self)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        return page

    @Slot(int)
    def _on_nav_changed(self, row: int) -> None:
        """Switch pages for page rows; trigger dialogs for action rows.

        Review-center and settings rows are triggers, not destinations: the
        selection snaps back to the current page's row (signals blocked) so
        the nav highlight always mirrors the visible page.
        """
        if row == 3:  # 审核中心 → 模态对话框
            self._snap_nav_to_page()
            self._on_review_clicked()
            return
        if row == 5:  # 设置 → 模态对话框
            self._snap_nav_to_page()
            self._on_settings_clicked()
            return
        page = _NAV_ROW_TO_PAGE.get(row)
        if page is not None:
            self._pages.setCurrentIndex(page)

    def _snap_nav_to_page(self) -> None:
        """Restore the nav selection to the current page row without re-entry."""
        row = _PAGE_TO_NAV_ROW.get(self._pages.currentIndex())
        if row is None:
            return
        with QSignalBlocker(self._nav_list):
            self._nav_list.setCurrentRow(row)

    @Slot(str)
    def _on_overview_primary(self, action_id: str) -> None:
        """Dispatch the overview CTA through the ordinary guarded entries."""
        if self._task_coordinator.is_busy:
            return
        handlers = {
            "import": self._on_import_clicked, "scan": self._on_scan_clicked,
            "review": self._on_review_clicked, "settings": self._on_settings_clicked,
            "model": self._on_model_help_clicked, "match": self._on_match_clicked,
            "archive": self._on_archive_clicked,
        }
        handler = handlers.get(action_id)
        if handler is not None:
            handler()

    def _refresh_workspace_state(self) -> None:
        """Refresh one shared query snapshot after workspace mutations."""
        self._workspace_controller.refresh(self._effective_archive_root())
        self._render_workspace_actions()
        # Batch 4：has_photos 随快照变化时空态页必须跟着重评估（模型行数信号
        # 只反映照片墙，不反映就绪快照）——否则删光照片后仍停留在筛选空态。
        self._update_photo_empty_state()
        self._overview_page.render_model(self._overview_presenter.build())

    def _render_workspace_actions(self) -> None:
        """Selection changes consume cached facts, never re-query the library."""
        controller = self._workspace_controller
        pairs = (
            (self._match_action, controller.match_guidance()),
            (self._archive_action, controller.archive_guidance()),
            (self._review_action, controller.review_guidance()),
            (self._delete_photos_action, ActionGuidance(
                bool(self._collect_selected_photo_ids()), text.DELETE_PHOTOS_NO_SELECTION,
            )),
        )
        busy = self._task_coordinator.is_busy
        for action, guidance in pairs:
            if busy:
                self._action_states[action] = (guidance.enabled, guidance.tooltip)
            else:
                action.setEnabled(guidance.enabled)
                action.setToolTip(guidance.tooltip)
        self._update_bulk_bar()
        labels = {
            "import": text.WORKSPACE_NEXT_IMPORT, "scan": text.WORKSPACE_NEXT_SCAN,
            "review": text.WORKSPACE_NEXT_REVIEW, "settings": text.WORKSPACE_NEXT_SETTINGS,
            "model": text.WORKSPACE_NEXT_MODEL,
        }
        for button, guidance in (
            (self._match_next_button, controller.match_guidance()),
            (self._archive_next_button, controller.archive_guidance()),
        ):
            button.setProperty("next_action", guidance.next_action)
            button.setVisible(guidance.next_action is not None)
            button.setText(labels.get(guidance.next_action or "", ""))
            button.setToolTip(guidance.tooltip)
            button.setEnabled(not busy and guidance.next_action is not None)

    def _on_workspace_next(self, button: QPushButton) -> None:
        """Dispatch a visible next step through the ordinary guarded entry."""
        if self._task_coordinator.is_busy:
            return
        handlers = {
            "import": self._on_import_clicked, "scan": self._on_scan_clicked,
            "review": self._on_review_clicked, "settings": self._on_settings_clicked,
            "model": self._on_model_help_clicked,
        }
        handler = handlers.get(button.property("next_action"))
        if handler is not None:
            handler()

    @_exclusive(text.WORKSPACE_MODEL_HELP_TITLE)
    def _on_model_help_clicked(self) -> None:
        QMessageBox.information(self, text.WORKSPACE_MODEL_HELP_TITLE, text.WORKSPACE_MODEL_HELP)

    def _update_photo_empty_state(self) -> None:
        """Pick the empty-state page — never confuse the two kinds of "none".

        Rows present → the wall. Otherwise: a running task explains the wait,
        a photo-less library invites scanning, and a filtered empty result
        offers the one-click "clear filters" escape (Batch 4 decision).
        """
        if self._photo_list_model.rowCount() > 0:
            self._photo_list_stack.setCurrentIndex(0)
            return
        if self._task_coordinator.is_busy:
            self._photo_list_stack.setCurrentIndex(3)
            return
        status = self._workspace_controller.status
        if status is not None and not status.has_photos:
            self._photo_list_stack.setCurrentIndex(1)
            return
        self._photo_list_stack.setCurrentIndex(2)

    def _update_bulk_bar(self) -> None:
        """Show the context bulk bar only for a non-empty selection.

        Buttons carry the exact selected count; with no selection the bar
        disappears entirely and during a busy task both dangerous actions
        stay disabled (Batch 1 admission + Batch 4 context rule).
        """
        count = len(self._collect_selected_photo_ids())
        busy = self._task_coordinator.is_busy
        for button, template in (
            (self._bulk_archive_button, text.BULK_ARCHIVE_BUTTON),
            (self._bulk_delete_button, text.BULK_DELETE_BUTTON),
        ):
            button.setVisible(count > 0)
            button.setText(template.format(count=count))
            button.setEnabled(count > 0 and not busy)

    @Slot(object)
    def _on_photo_double_clicked(self, index: object) -> None:
        """Open the read-only detail dialog for the double-clicked photo."""
        if not hasattr(index, "data"):
            return
        photo_id = index.data(PHOTO_ID_ROLE)
        photo = self._photos_by_id.get(photo_id) if isinstance(photo_id, UUID) else None
        if photo is None:
            return
        badge = index.data(STATUS_BADGE_ROLE)
        thumbnail = index.data(THUMBNAIL_ROLE)
        PhotoDetailDialog(
            photo,
            badge=str(badge) if badge else None,
            thumbnail_path=thumbnail if isinstance(thumbnail, Path) else None,
            parent=self,
        ).exec()

    def _on_filter_changed(self, criteria: object) -> None:
        """Reload photos filtered by the supplied criteria, or all when None.

        Synchronous on the UI thread: ``search_photos`` is fast SQL push-down
        (<50ms typical), no Worker submission per the dual-strategy decision.
        ``criteria`` is typed ``object`` because Qt Signal carries it opaquely;
        the FilterBar only ever emits ``PhotoSearchCriteria | None``.
        """
        # F2: mirror the criteria into the sole UI holding point (a conditions
        # snapshot, not a result-set copy — the export re-queries via
        # PhotoRepository.search at execution time).
        self._current_criteria = (
            criteria if isinstance(criteria, PhotoSearchCriteria) else None
        )
        self._refresh_photo_list()

    def _build_status(self) -> None:
        """Create the status bar with progress, label and the cancel button.

        The cancel entry lives in the permanent status-bar area so the task
        panel (progress, message, cancel) stays visible on every page.
        """
        self._status = QStatusBar(self)
        self.setStatusBar(self._status)
        self._progress = QProgressBar(self)
        self._progress.setRange(0, _PROGRESS_RESOLUTION)
        self._progress.setValue(0)
        self._status.addPermanentWidget(self._progress)
        self._status_label = QLabel(STATUS_READY, self)
        self._status.addWidget(self._status_label)
        cancel_button = QToolButton(self)
        cancel_button.setObjectName("CancelTask")
        cancel_button.setDefaultAction(self._cancel_action)
        cancel_button.setAccessibleName(ACTION_CANCEL_TASK)
        self._status.addPermanentWidget(cancel_button)

    # ---- Worker task slots ----

    @property
    def _active_runnable(self) -> QtWorkerRunnable | None:
        """Read-only compatibility view of the coordinator's task handle."""
        return self._task_coordinator.active_runnable

    @Slot()
    def _on_task_state_changed(self) -> None:
        coordinator = self._task_coordinator
        if coordinator.is_busy:
            reason = STATUS_TASK_BUSY.format(label=coordinator.label)
            for action in self._conflicting_actions:
                if action not in self._action_states:
                    self._action_states[action] = (action.isEnabled(), action.toolTip())
                action.setEnabled(False)
                action.setToolTip(reason)
        else:
            for action, (enabled, tooltip) in self._action_states.items():
                action.setEnabled(enabled)
                action.setToolTip(tooltip)
            self._action_states.clear()
            self._status.clearMessage()
        self._render_workspace_actions()
        self._overview_page.set_busy(coordinator.is_busy, coordinator.label)
        self._update_photo_empty_state()
        self._cancel_action.setEnabled(coordinator.can_cancel)
        self._cancel_action.setToolTip(
            STATUS_CANCELLING if coordinator.is_cancelling else
            text.WORKSPACE_CANCEL_READY if coordinator.can_cancel else text.WORKSPACE_CANCEL_IDLE
        )
        if coordinator.is_cancelling and STATUS_CANCELLING not in self._status_label.text():
            self._status_label.setText(STATUS_TASK_CANCEL_PROGRESS.format(
                status=self._status_label.text(), cancellation=STATUS_CANCELLING,
            ))

    def _connect_task_signals(
        self, runnable: QtWorkerRunnable, connect: Callable | None = None,
    ) -> None:
        """Initialize UI before any controller's synchronous terminal replay."""
        self._progress.setRange(0, 0)
        self._progress.setValue(0)
        self._status_label.setText(STATUS_TASK_PROGRESS.format(
            label=self._task_coordinator.label, progress=STATUS_PROGRESS_UNKNOWN,
            message=self._status_label.text(),
        ))
        self._task_coordinator.bind(runnable, connect or ImportPeopleController.connect_signals)

    @Slot(object)
    def _on_started(self, event: TaskStarted) -> None:
        """Reflect an identity-checked start without erasing cancellation."""
        self._render_task_progress(STATUS_TASK_STARTED.format(
            label=self._task_coordinator.label,
        ))

    def _render_task_progress(self, message: str) -> None:
        progress = (
            STATUS_PROGRESS_UNKNOWN if self._progress.maximum() == 0
            else f"{self._progress.value()}%"
        )
        text = STATUS_TASK_PROGRESS.format(
            label=self._task_coordinator.label, progress=progress, message=message,
        )
        if self._task_coordinator.is_cancelling:
            text = STATUS_TASK_CANCEL_PROGRESS.format(status=text, cancellation=STATUS_CANCELLING)
        self._status_label.setText(text)

    @Slot(object)
    def _on_progress(self, event: TaskProgress) -> None:
        """Show message and measured progress together; unknown totals stay busy."""
        if event.current is not None and event.total is not None and event.total > 0:
            self._progress.setRange(0, _PROGRESS_RESOLUTION)
            self._progress.setValue(max(0, min(
                _PROGRESS_RESOLUTION, int(event.current * _PROGRESS_RESOLUTION / event.total),
            )))
        else:
            self._progress.setRange(0, 0)
        self._render_task_progress(event.message)

    @Slot(object)
    def _on_terminal(self, event: TaskCompleted | TaskFailed | TaskCancelled) -> None:
        """One accepted terminal, one refresh, still reserved through modal feedback."""
        self._progress.setRange(0, _PROGRESS_RESOLUTION)
        if isinstance(event, TaskCompleted):
            self._on_completed(event)
        elif isinstance(event, TaskFailed):
            self._on_failed(event)
        else:
            self._on_task_cancelled(event)

    def _refresh_task_results(self, task_name: str) -> None:
        # Failed/cancelled tasks may already have persisted a partial batch.
        try:
            if task_name in ("import_people", "import_confirm"):
                # Stage A: the large-roster confirm task reports as
                # ``import_confirm`` (D6) — both names must refill the catalog
                # without set_persons emitting transient criteria.
                with QSignalBlocker(self._filter_bar):
                    self._refresh_filter_persons()
            self._refresh_photo_list()
            if task_name == "match_persons":
                self._refresh_review_pending()
            self._refresh_workspace_state()
        except Exception:  # noqa: BLE001 - terminal feedback must survive read failures
            logger.exception("Unable to refresh task results for {}", task_name)
            self._status_label.setText(
                self._status_label.text() + " · " + STATUS_REFRESH_FAILED
            )

    def _on_task_cancelled(self, event: TaskCancelled) -> None:
        self._progress.setValue(0)
        self._status_label.setText(STATUS_TASK_CANCELLED.format(label=task_label(event.task_name)))
        self._refresh_task_results(event.task_name)

    def _on_completed(self, event: TaskCompleted) -> None:
        """Reflect completion and refresh persisted results under current criteria."""
        self._progress.setValue(_PROGRESS_RESOLUTION)
        self._status_label.setText(STATUS_TASK_COMPLETED.format(label=task_label(event.task_name)))
        self._append_match_summary(event)
        self._refresh_task_results(event.task_name)

    def _append_match_summary(self, event: TaskCompleted) -> None:
        """Append processed/found/unreadable counts after a match batch finishes.

        AUDIT 2026-09-20: 473/473 unreadable photos used to look identical to
        a clean empty run ("识别完成 · 0 条待审核"); the completion status must
        carry the counts so read failures can never hide again.
        """
        results = event.result
        if event.task_name != "match_persons" or not isinstance(results, tuple):
            return
        processed = len(results)
        faces = sum(1 for result in results if getattr(result, "box", None) is not None)
        unreadable = sum(1 for result in results if getattr(result, "read_failed", False))
        summary = STATUS_MATCH_SUMMARY.format(processed=processed, faces=faces)
        if unreadable:
            summary += " · " + STATUS_MATCH_UNREADABLE.format(unreadable=unreadable)
        self._status_label.setText(self._status_label.text() + " · " + summary)

    def _refresh_filter_persons(self) -> None:
        """Load the FilterBar person axis through the Application layer.

        Thin read-only use case (``ListPersonsService`` over
        ``PersonRepository.list_all``) — Presentation never touches the
        repository directly (DEP-003/DEP-004).

        Stage B: the people page shares the same registry, so every refresh of
        the person axis (import confirm, deletion, plugin import, …) reloads
        the roster table too — otherwise the page went stale until restart.
        """
        self._filter_bar.set_persons(self._context.services.list_persons.execute())
        if getattr(self, "_people_admin_page", None) is not None:
            self._people_admin_page.refresh()

    def _on_failed(self, event: TaskFailed) -> None:
        """Refresh partial results before showing the concrete worker failure."""
        self._progress.setValue(0)
        self._status_label.setText(STATUS_TASK_FAILED.format(label=task_label(event.task_name)))
        self._refresh_task_results(event.task_name)
        QMessageBox.warning(
            self, STATUS_TASK_FAILED.format(label=task_label(event.task_name)), event.message,
        )

    def _on_cancel_clicked(self) -> None:
        """Request cooperative cancellation only for the coordinator's task."""
        coordinator = self._task_coordinator
        if coordinator.can_cancel and not coordinator.cancel() and coordinator.can_cancel:
            self._render_task_progress(STATUS_CANCEL_FAILED)

    # ---- Toolbar actions ----

    @_exclusive(task_label("scan_and_register_photos"))
    def _on_scan_clicked(self) -> None:
        """Open a folder picker and start the scan workflow.

        P0-4 single-flight: the controller refuses a second submission while
        a scan is in flight (``runnable is None``) — the refusal reason is
        surfaced in the status bar and the running scan is left untouched.
        """
        folder = QFileDialog.getExistingDirectory(self, DIALOG_SELECT_PHOTO_FOLDER)
        if not folder:
            return
        runnable = self._scan_controller.scan_folder(Path(folder))
        if runnable is None:
            reason = self._scan_controller.last_refusal_reason
            self._status_label.setText(reason or STATUS_SCAN_UNAVAILABLE)
            return
        self._progress.setValue(0)
        self._status_label.setText(STATUS_SCANNING_FOLDER.format(folder=folder))
        self._connect_scan_signals(runnable)

    def _connect_scan_signals(self, runnable: QtWorkerRunnable) -> None:
        """Attach a scan while retaining its controller-local single-flight guard."""
        if not self._task_coordinator.is_busy:
            self._task_coordinator.reserve(task_label("scan_and_register_photos"))
        self._connect_task_signals(runnable, self._scan_controller.connect_signals)

    @_exclusive(task_label("import_people"))
    def _on_import_clicked(self) -> None:
        """Open a file picker, parse a draft, preview, then confirm (stage A).

        两段式：解析为草稿（同步，名单文件小且快）→ 预览对话框编辑/拆分/跳过
        → 确认。确认 ≤500 行同步执行；>500 行提交 ConfirmImportTask 走 Worker
        （D6）。取消（reject）保留草稿，不写正式人员。
        """
        path, _ = QFileDialog.getOpenFileName(
            self, DIALOG_SELECT_PEOPLE_FILE, "", PEOPLE_FILE_FILTER
        )
        if not path:
            return
        draft = self._context.services.parse_import_draft.execute(
            ParseImportDraftCommand(Path(path)),
        )
        if not draft.rows:
            QMessageBox.information(
                self, IMPORT_PREVIEW_TITLE, IMPORT_PREVIEW_EMPTY_FILE,
            )
            return
        dialog = ImportPreviewDialog(draft, self._context.services, Path(path), self)
        if not dialog.exec():
            # 取消：草稿保留（可回看），正式人员名单不变。
            self._status_label.setText(STATUS_IMPORT_DRAFT_PARSED.format(rows=len(draft.rows)))
            return
        self._confirm_import(dialog.batch_id, dialog.row_count)

    def _confirm_import(self, batch_id: UUID, row_count: int) -> None:
        """Confirm a draft batch synchronously or via worker (D6 threshold)."""
        if row_count > CONFIRM_SYNC_LIMIT:
            runnable = self._context.worker_executor.submit(ConfirmImportTask(
                self._context.services.confirm_import,
                ConfirmImportCommand(batch_id),
            ))  # type: ignore[arg-type]  # WorkerTask generics variance
            self._progress.setRange(0, 0)
            self._status_label.setText(STATUS_IMPORT_CONFIRM_WORKER)
            self._connect_task_signals(runnable)
            return
        result = self._context.services.confirm_import.execute(ConfirmImportCommand(batch_id))
        self._status_label.setText(STATUS_IMPORT_CONFIRMED.format(
            imported=result.imported_count,
            merged=result.merged_count,
            skipped=result.skipped_count,
        ) + (
            STATUS_IMPORT_CONFIRM_ERRORS.format(count=len(result.errors))
            if result.errors else ""
        ))
        self._refresh_filter_persons()
        self._refresh_workspace_state()

    @_exclusive(ACTION_REVIEW_PENDING)
    def _on_review_clicked(self) -> None:
        """Open the modal ReviewDialog for inline approve/reject.

        Step 13 fix: review is no longer a dead-end. The dialog lists pending
        recognition results, forwards approve/reject to the controller
        synchronously (<10ms SQLite per Step 12 裁决 A), and refreshes the
        queue after each action. The "Use the CLI" info popup is retired.
        Batch 5: rows render through the shared async thumbnail channel and
        after close the photo wall (badges + counts) re-queries immediately —
        approving here must be reflected in the library without a manual
        refresh.
        """
        dialog = ReviewDialog(
            self._review_controller,
            self,
            thumbnail_source=self._photo_list_controller,
        )
        dialog.exec()
        # Approve/reject inside the dialog changes pending/archivable counts.
        self._refresh_workspace_state()
        self._refresh_photo_list()

    @_exclusive(task_label("archive_photos"))
    def _on_archive_clicked(self) -> None:
        """Open the archive preview dialog; on accept, start the archive task.

        B3 批量归档：读 QListView 选中项的 photo_id 透传 preview/execute——
        用户多选的 photos 直下推 plan 过滤。无选中时 photo_ids=() 走原路径
        （全部 APPROVED 照片），向后兼容。Batch 6：缺根目录不再只是报错——
        询问后可直达「设置」；预览对话框携带范围说明（选中数）。
        """
        archive_root = self._effective_archive_root()
        if archive_root is None:
            box = QMessageBox(
                QMessageBox.Icon.Question,
                ARCHIVE_DIALOG_TITLE,
                ARCHIVE_ROOT_SETUP_PROMPT,
                QMessageBox.StandardButton.NoButton,
                self,
            )
            setup = box.addButton(
                ARCHIVE_ROOT_SETUP_BUTTON, QMessageBox.ButtonRole.YesRole,
            )
            dismiss = box.addButton(
                ARCHIVE_ROOT_SETUP_CANCEL, QMessageBox.ButtonRole.NoRole,
            )
            box.setDefaultButton(dismiss)
            box.exec()
            if box.clickedButton() is setup:
                # 本预约内联打开设置（不再走 @_exclusive 重入），返回后
                # 立即以最新快照恢复各动作可用性。
                self._open_settings_dialog()
            return
        photo_ids = self._collect_selected_photo_ids()
        plan = self._archive_controller.preview(archive_root, (), photo_ids=photo_ids)
        if plan.planned_count == 0:
            QMessageBox.information(
                self,
                ARCHIVE_DIALOG_TITLE,
                ARCHIVE_NOTHING_TO_ARCHIVE.format(skipped=plan.skipped_count),
            )
            return
        dialog = ArchivePreviewDialog(
            plan, archive_root, self, selected_count=len(photo_ids),
        )
        if not dialog.exec():
            return
        self._progress.setValue(0)
        self._status_label.setText(STATUS_ARCHIVING)
        runnable = self._archive_controller.execute(
            archive_root,
            person_ids=(),  # review M-5 fix: symmetric with preview(()) — "all persons with approvals"
            photo_ids=photo_ids,  # B3 批量归档：用户多选透传
            conflict_strategy=dialog.conflict_strategy,
            dry_run=dialog.dry_run,
        )
        self._connect_task_signals(runnable)

    def _effective_archive_root(self) -> Path | None:
        """Resolve the archive root: user preference (设置 UI) overrides .env.

        G-2（FEAT-14 收尾）: the settings dialog can persist an archive root
        via UserPreferences; when unset, AppSettings.ARCHIVE_ROOT (env /
        anchored default) applies — the pre-existing contract. A preference
        set to a path always wins, matching the import/export path fields'
        semantics.
        """
        preferences = self._settings_controller.load()
        if preferences.archive_root is not None:
            return preferences.archive_root
        return self._context.settings.archive_root

    def _collect_selected_photo_ids(self) -> tuple[UUID, ...]:
        """Read the QListView current selection and return their photo ids.

        B3 批量归档辅助：映射每 selectedIndex 的 PHOTO_ID_ROLE → UUID tuple。
        ExtendedSelection 下空选区返回 () 走原"全部 APPROVED"路径，向后兼容。
        """
        ids: list[UUID] = []
        for index in self._photo_list.selectedIndexes():
            pid = self._photo_list_model.data(index, PHOTO_ID_ROLE)
            if isinstance(pid, UUID):
                ids.append(pid)
        return tuple(ids)

    def _refresh_photo_list(self) -> None:
        """Reload photos from the repository into the model.

        Called after any task completes so newly-scanned or archived photos
        surface without a manual refresh. Thumbnails load lazily via the
        PhotoListController when the list view asks for them.
        """
        photos = (
            self._photo_list_controller.search_photos(self._current_criteria)
            if self._current_criteria is not None
            else self._photo_list_controller.list_photos()
        )
        # Batch 4: identity map for the detail dialog + live result count.
        self._photos_by_id = {
            photo.id: photo for photo in photos if photo.id is not None
        }
        self._photo_list_model.load_photos(photos)
        self._photo_list_model.set_status_badges(
            self._photo_list_controller.status_badges(
                [photo.id for photo in photos if photo.id is not None]
            )
        )
        self._filter_bar.set_result_count(len(photos))
        for photo in photos:
            self._photo_list_controller.load_thumbnail(photo.id, photo.path.raw_path)  # type: ignore[arg-type]  # photo.id is UUID | None, guaranteed set by Photo.__post_init__

    @_exclusive(ACTION_SETTINGS)
    def _on_settings_clicked(self) -> None:
        """Open the modal SettingsDialog; the dialog owns its own save/cancel flow.

        Step 13: settings are persisted synchronously through QSettings (sub-ms),
        so no worker is needed here. The dialog rejects on cancel or validation
        failure that the user chose to abandon; accept only happens after a
        successful save. Restart prompts for theme / language changes are
        documented in docs/development/configuration.md §3 (this round ships
        the persistence; hot-reload of theme is a follow-up).
        """
        self._open_settings_dialog()

    def _open_settings_dialog(self) -> None:
        """Open settings and refresh afterwards, without fresh task admission.

        Batch 6: the archive root-missing prompt opens this directly inside
        its own reservation (a nested @_exclusive call would deadlock on the
        coordinator); the refresh on return picks up the new archive root.
        """
        dialog = SettingsDialog(self._settings_controller, self)
        dialog.exec()
        # Archive root preference may have changed — reprobe and re-render.
        self._refresh_workspace_state()

    @_exclusive(ACTION_DETECT_DUPLICATES)
    def _on_detect_duplicates_clicked(self) -> None:
        """Run duplicate detection and pop up the read-only report dialog.

        B1 首版只读：detect_duplicates_controller.detect_and_show() 内已编排
        同步查询 + DuplicateReportDialog 展示，且对空结果/异常均有兜底文案。
        不下沉 Worker——查重是 SQL 下推的快速查询。
        """
        self._context.detect_duplicates_controller.detect_and_show()

    # ---- Library management (Phase E E-4, ADR-034) ----

    @_exclusive(ACTION_DELETE_PHOTOS)
    def _on_delete_photos_clicked(self) -> None:
        """Remove the selected photo registrations after confirmation (E-4).

        Flow: collect multi-selection → preview cascade counts → confirm dialog
        (disk-file disclaimer, D3) → execute → refresh list. Synchronous on the
        UI thread (fast SQLite push-down, same rationale as archive preview).
        """
        selected = self._collect_selected_photo_ids()
        if not selected:
            QMessageBox.information(
                self,
                DELETE_PHOTOS_NO_SELECTION_TITLE,
                DELETE_PHOTOS_NO_SELECTION,
            )
            return
        try:
            preview = self._context.services.delete_photos.preview(selected)
            if preview.is_empty:
                QMessageBox.information(
                    self,
                    DELETE_PHOTOS_NO_SELECTION_TITLE,
                    DELETE_PHOTOS_NO_SELECTION,
                )
                return
            if not PhotoDeletionConfirmDialog(preview, parent=self).exec():
                return
            result = self._context.services.delete_photos.execute(
                DeletePhotosCommand(photo_ids=selected)
            )
        except Exception as exc:  # noqa: BLE001  # UI boundary: show the user, log the detail
            logger.exception("Photo registration deletion failed unexpectedly")
            QMessageBox.critical(self, DELETE_FAILED_TITLE, DELETE_FAILED_MESSAGE.format(detail=exc))
            return
        self._refresh_photo_list()
        QMessageBox.information(
            self,
            DELETE_PHOTOS_DONE_TITLE,
            DELETE_PHOTOS_DONE.format(
                removed=result.removed,
                recognition_cascade=result.recognition_cascade,
                archive_cascade=result.archive_cascade,
            ),
        )

    @_exclusive(ACTION_DELETE_PERSON)
    def _on_delete_person_clicked(self) -> None:
        """Open the person-deletion dialog and run the confirmed removal (E-4).

        The dialog owns selection + live preview (D2: 嵌入删除、识别归属置空、
        照片全保留明示); on accept we execute the confirmed id and refresh the
        filter person axis + photo list (recognition attributions changed).
        """
        dialog = PersonDeletionDialog(
            self._context.services.list_persons,
            self._context.services.delete_person,
            parent=self,
        )
        if not dialog.exec():
            return
        person_id = dialog.selected_person_id()
        person_name = dialog.selected_person_name()
        if person_id is None:
            return
        try:
            result = self._context.services.delete_person.execute(
                DeletePersonCommand(person_ids=(person_id,))
            )
        except Exception as exc:  # noqa: BLE001  # UI boundary: show the user, log the detail
            logger.exception("Person deletion failed unexpectedly")
            QMessageBox.critical(self, DELETE_FAILED_TITLE, DELETE_FAILED_MESSAGE.format(detail=exc))
            return
        self._refresh_filter_persons()
        self._refresh_photo_list()
        QMessageBox.information(
            self,
            PERSON_DELETE_DIALOG_TITLE,
            PERSON_DELETE_DONE.format(
                name=person_name,
                embedding_cascade=result.embedding_cascade,
                recognition_orphaned=result.recognition_orphaned,
            ),
        )

    # ---- Face recognition (match persons) ----

    @_exclusive(task_label("match_persons"))
    def _on_match_clicked(self) -> None:
        """Start the face-recognition (match persons) workflow on click.

        Delegates to MatchPersonsController which owns the single-flight guard
        (AC-014) — the window never re-implements running state. When the
        controller refuses (already running / no persons / no photos / all
        photos already matched) it returns ``None`` with a human-readable
        ``last_refusal_reason`` surfaced in the status bar. A submitted
        runnable disables this action until a terminal signal (completed /
        failed / cancelled) re-enables it and releases the controller guard.

        Batch 2: a cached readiness gate runs first so a missing model or
        empty workspace is refused with guidance before any worker submission;
        the controller's own refusals remain the authoritative second line.
        """
        guidance = self._workspace_controller.match_guidance()
        if not guidance.enabled:
            # Cached read-side guidance; the controller's own refusals remain
            # the authoritative second line (TOCTOU).
            self._status_label.setText(guidance.tooltip)
            return
        runnable = self._match_controller.start_match()
        if runnable is None:
            reason = self._match_controller.last_refusal_reason
            self._status_label.setText(reason or STATUS_MATCH_UNAVAILABLE)
            return
        self._status_label.setText(STATUS_TASK_PREPARING.format(label=task_label("match_persons")))
        self._connect_task_signals(runnable, self._match_controller.connect_signals)

    # ------------------------------------------------------------------
    # Phase 5 Commit 1: Export UI wiring
    # ------------------------------------------------------------------

    @_exclusive(task_label("export"))
    def _on_export_clicked(self) -> None:
        """Open the modal ExportDialog; on accept, dispatch the export task.

        Mirrors the archive flow: the dialog collects scope / format / output
        path, then the runnable is submitted through the worker-backed
        ExportController (two-phase progress off the UI thread). The action is
        disabled while a run is in flight and re-enabled by every terminal
        signal (completed / failed / cancelled). ADR-036 D7: exports are
        cancellable cooperatively at task boundaries (LIMIT-002 granularity) —
        the Cancel toolbar action is enabled for the run and the cancelled
        terminal resets the UI and re-enables the export action.
        """
        dialog = ExportDialog(
            parent=self,
            active_criteria=self._current_criteria,
            filtered_count=(
                self._filter_bar.result_count
                if self._current_criteria is not None
                else None
            ),
            criteria_summary=self._filter_bar.summary_text,
        )
        if not dialog.exec():
            return
        output_path = dialog.output_path
        if output_path is None:
            # Defensive: _on_accept validates a non-empty path before
            # accepting, so this branch is unreachable in practice.
            return
        self._progress.setValue(0)
        self._status_label.setText(STATUS_EXPORTING)
        scope = dialog.scope
        # F5: the criteria snapshot rides only the FILTERED scope; ALL ignores
        # it. Still, UI-side disable is just the first UX layer — the Service
        # independently rejects FILTERED + None (Commit-2 invariant).
        criteria = self._current_criteria if scope is ExportScope.FILTERED else None
        runnable = self._export_controller.export(
            output_path,
            scope=scope,
            format_name=dialog.format_name,
            criteria=criteria,
        )
        self._connect_task_signals(runnable, self._export_controller.connect_signals)

    def _refresh_review_pending(self) -> None:
        """Re-query recognition results so newly created PENDING entries surface.

        Called after face recognition completes so the next ReviewDialog open
        shows fresh pending results. Uses only the existing read API
        (ReviewController.list_pending) and reflects the count in the status
        bar as lightweight feedback — Review business rules are untouched.
        """
        pending = self._review_controller.list_pending()
        self._status_label.setText(
            self._status_label.text() + " · " + STATUS_PENDING_REVIEW_COUNT.format(count=len(pending))
        )
