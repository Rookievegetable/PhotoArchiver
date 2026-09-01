"""Main application window — Step 12 complete workbench.

Toolbar: [Import People] [Scan Folder] [Review Pending] [Archive]
Central: QListView of photos with thumbnails (PhotoListModel)
Status:  progress bar + status label

每个 toolbar action 接对应 controller，长耗时走 QtWorkerExecutor，
短耗时（review approve/reject、archive preview）同步调。
"""

from pathlib import Path
from uuid import UUID

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QStatusBar,
    QToolBar,
    QListView,
    QVBoxLayout,
    QWidget,
)

from loguru import logger

from photo_archiver.app.context import ApplicationContext
from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.application.dtos.plugin_action_result import ActionResult
from photo_archiver.domain import PhotoSearchCriteria
from photo_archiver.presentation.controllers import (
    ArchiveController,
    ImportPeopleController,
    MatchPersonsController,
    ScanController,
)
from photo_archiver.presentation.views.archive_preview_dialog import ArchivePreviewDialog
from photo_archiver.presentation.views.export_dialog import ExportDialog
from photo_archiver.presentation.views.filter_bar import FilterBar
from photo_archiver.presentation.views.plugin_report_dialog import PluginReportDialog
from photo_archiver.presentation.views.photo_list_model import PHOTO_ID_ROLE, PhotoListModel
from photo_archiver.presentation.views.review_dialog import ReviewDialog
from photo_archiver.presentation.views.settings_dialog import SettingsDialog
from photo_archiver.plugins import PluginRegistry
from photo_archiver.workers import QtWorkerRunnable
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
        self.setWindowTitle("PhotoArchiver")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self._context = context
        self._build_controllers()
        self._build_toolbar()
        self._load_plugins()
        self._build_central()
        self._build_status()
        self._active_runnable: QtWorkerRunnable | None = None  # tracks the currently running worker
        self._current_criteria: PhotoSearchCriteria | None = None  # FEATURE-004 F2: sole UI holding point

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

    def _build_toolbar(self) -> None:
        """Create the primary action toolbar covering the full闭环."""
        toolbar = QToolBar("Main", self)
        self.addToolBar(toolbar)

        import_action = QAction("Import People", self)
        import_action.triggered.connect(self._on_import_clicked)
        toolbar.addAction(import_action)

        scan_action = QAction("Scan Folder", self)
        scan_action.triggered.connect(self._on_scan_clicked)
        toolbar.addAction(scan_action)

        review_action = QAction("Review Pending", self)
        review_action.triggered.connect(self._on_review_clicked)
        toolbar.addAction(review_action)

        archive_action = QAction("Archive", self)
        archive_action.triggered.connect(self._on_archive_clicked)
        toolbar.addAction(archive_action)

        # Phase 4.2 Commit 3: face-recognition trigger. Disabled while a match
        # task is in flight; re-enabled by every terminal signal (completed /
        # failed / cancelled). The controller's _active_runnable remains the
        # authoritative running state (AC-014), so no second UI busy flag.
        self._match_action = QAction("Run Face Recognition", self)
        self._match_action.triggered.connect(self._on_match_clicked)
        toolbar.addAction(self._match_action)

        # Phase 5 Commit 1: export trigger. Disabled while an export task runs;
        # re-enabled by every terminal signal (completed / failed) — ExportController
        # exposes 4 channels (no cancelled), matching the connect_signals contract.
        # UI-side enablement is the only single-flight state for export: unlike
        # the match controller, ExportController carries no guard of its own.
        self._export_action = QAction("Export Data", self)
        self._export_action.triggered.connect(self._on_export_clicked)
        toolbar.addAction(self._export_action)

        detect_duplicates_action = QAction("Detect Duplicates", self)
        detect_duplicates_action.triggered.connect(self._on_detect_duplicates_clicked)
        toolbar.addAction(detect_duplicates_action)

        settings_action = QAction("Settings", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._on_settings_clicked)
        toolbar.addAction(settings_action)

        self._cancel_action = QAction("Cancel Task", self)
        self._cancel_action.setEnabled(False)
        self._cancel_action.triggered.connect(self._on_cancel_clicked)
        toolbar.addAction(self._cancel_action)

        toolbar.addSeparator()
        self._plugin_actions: list[QAction] = []

    def _load_plugins(self) -> None:
        """Discover, load, and register plugin menu actions.

        Plugins are loaded from ``examples/plugins/``. Each plugin's
        ``actions()`` are turned into QAction entries appended to the toolbar.
        Malformed plugins never crash the window — the loader logs and skips.
        """
        self._plugin_registry = PluginRegistry(self._context.plugin_context)
        examples_plugins = Path(__file__).resolve().parent.parent.parent.parent / "examples" / "plugins"
        if examples_plugins.is_dir():
            self._plugin_registry.load_from_path(examples_plugins)
            self._plugin_registry.enable_all()
            self._add_plugin_actions()

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
                    "Plugin Error",
                    f"Plugin action '{action_id}' failed. See logs for details.",
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
        title = f"Plugin: {action_id}"
        if result.status == "success":
            if result.report is not None:
                dialog = PluginReportDialog(result.report, self)
                dialog.exec()  # type: ignore[attr-defined]
            else:
                QMessageBox.information(self, title, result.message)
        elif result.status == "failure":
            body = result.message or "Action failed (no detail provided)."
            QMessageBox.warning(self, title, body)
        # noop → 不渲染（_add_plugin_actions 已按 id 路由，不应走到）

    def _build_central(self) -> None:
        """Create the central photo list view with a filter bar above it."""
        central = QWidget(self)
        layout = QVBoxLayout(central)

        # B2 搜索/筛选：FilterBar 在列表上方，发 criteria_changed → 刷新列表。
        # criteria None 时回退 list_all；否则走 PhotoListController.search_photos。
        self._filter_bar = FilterBar(self)
        self._filter_bar.criteria_changed.connect(self._on_filter_changed)
        layout.addWidget(self._filter_bar)

        self._photo_list_model = PhotoListModel(parent=self)
        self._photo_list = QListView(self)
        self._photo_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._photo_list.setModel(self._photo_list_model)
        layout.addWidget(self._photo_list)

        self.setCentralWidget(central)
        # Wire thumbnail loads → model now that _photo_list_model exists.
        self._photo_list_controller.thumbnail_loaded.connect(
            self._photo_list_model.set_thumbnail,
        )

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
        if not isinstance(criteria, PhotoSearchCriteria):
            # None or unexpected type → fall back to unfiltered list.
            self._refresh_photo_list()
            return
        photos = self._photo_list_controller.search_photos(criteria)
        self._photo_list_model.load_photos(photos)
        for photo in photos:
            self._photo_list_controller.load_thumbnail(photo.id, photo.path.raw_path)  # type: ignore[arg-type]  # photo.id is UUID | None, guaranteed set by Photo.__post_init__

    def _build_status(self) -> None:
        """Create the status bar with a progress bar and persistent label."""
        self._status = QStatusBar(self)
        self.setStatusBar(self._status)
        self._progress = QProgressBar(self)
        self._progress.setRange(0, _PROGRESS_RESOLUTION)
        self._progress.setValue(0)
        self._status.addPermanentWidget(self._progress)
        self._status_label = QLabel("Ready", self)
        self._status.addWidget(self._status_label)

    # ---- Worker task slots ----

    def _connect_task_signals(self, runnable) -> None:
        """Wire the runnable's signals to the shared task slots and track it."""
        self._active_runnable = runnable
        ImportPeopleController.connect_signals(
            runnable,
            self._on_started,  # type: ignore[arg-type]  # Qt Slot vs Callable variance, existing convention
            self._on_progress,  # type: ignore[arg-type]
            self._on_completed,  # type: ignore[arg-type]
            self._on_failed,  # type: ignore[arg-type]
        )
        self._cancel_action.setEnabled(True)

    def _on_started(self, event: TaskStarted) -> None:
        """Reflect task start in the status bar."""
        self._status_label.setText(f"{event.task_name} started ...")

    def _on_progress(self, event: TaskProgress) -> None:
        """Update the progress bar from task progress events."""
        if event.current is not None and event.total and event.total > 0:
            self._progress.setValue(int(event.current * _PROGRESS_RESOLUTION / event.total))
        elif event.message:
            self._status_label.setText(event.message)

    def _on_completed(self, event: TaskCompleted) -> None:
        """Reflect task completion and refresh the photo list."""
        self._cancel_action.setEnabled(False)
        self._progress.setValue(_PROGRESS_RESOLUTION)
        self._status_label.setText(f"{event.task_name} complete")
        self._refresh_photo_list()

    def _on_failed(self, event: TaskFailed) -> None:
        """Surface task failure with the concrete error message and reset progress."""
        self._cancel_action.setEnabled(False)
        self._progress.setValue(0)
        self._status_label.setText(f"{event.task_name} failed.")
        QMessageBox.warning(self, f"{event.task_name.title()} Failed", event.message)

    def _on_cancel_clicked(self) -> None:
        """Request cooperative cancellation for the active task."""
        runnable = getattr(self, "_active_runnable", None)
        if runnable is not None:
            runnable.cancel("User requested cancel")
            self._cancel_action.setEnabled(False)
            self._status_label.setText("Cancelling ...")

    # ---- Toolbar actions ----

    def _on_scan_clicked(self) -> None:
        """Open a folder picker and start the scan workflow."""
        folder = QFileDialog.getExistingDirectory(self, "Select Photo Folder")
        if not folder:
            return
        self._progress.setValue(0)
        self._status_label.setText(f"Scanning {folder} ...")
        runnable = self._scan_controller.scan_folder(Path(folder))
        self._connect_task_signals(runnable)

    def _on_import_clicked(self) -> None:
        """Open a file picker and start the people-import workflow."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select People File", "", "People files (*.txt *.xlsx *.xls)"
        )
        if not path:
            return
        self._progress.setValue(0)
        self._status_label.setText(f"Importing {path} ...")
        runnable = self._import_controller.import_from(Path(path))
        self._connect_task_signals(runnable)

    def _on_review_clicked(self) -> None:
        """Open the modal ReviewDialog for inline approve/reject.

        Step 13 fix: review is no longer a dead-end. The dialog lists pending
        recognition results, forwards approve/reject to the controller
        synchronously (<10ms SQLite per Step 12 裁决 A), and refreshes the
        queue after each action. The "Use the CLI" info popup is retired.
        """
        dialog = ReviewDialog(self._review_controller, self)
        dialog.exec()

    def _on_archive_clicked(self) -> None:
        """Open the archive preview dialog; on accept, start the archive task.

        B3 批量归档：读 QListView 选中项的 photo_id 透传 preview/execute——
        用户多选的 photos 直下推 plan 过滤。无选中时 photo_ids=() 走原路径
        （全部 APPROVED 照片），向后兼容。
        """
        archive_root = self._context.settings.archive_root
        if archive_root is None:
            QMessageBox.warning(
                self,
                "Archive",
                "ARCHIVE_ROOT is not configured. Set it in .env or use the CLI --archive-root flag.",
            )
            return
        photo_ids = self._collect_selected_photo_ids()
        plan = self._archive_controller.preview(archive_root, (), photo_ids=photo_ids)
        if plan.planned_count == 0:
            QMessageBox.information(
                self,
                "Archive",
                f"Nothing to archive (skipped={plan.skipped_count}). "
                "Approve recognition results first via the Review button.",
            )
            return
        dialog = ArchivePreviewDialog(plan, archive_root, self)
        if not dialog.exec():
            return
        self._progress.setValue(0)
        self._status_label.setText("Archiving ...")
        runnable = self._archive_controller.execute(
            archive_root,
            person_ids=(),  # review M-5 fix: symmetric with preview(()) — "all persons with approvals"
            photo_ids=photo_ids,  # B3 批量归档：用户多选透传
            conflict_strategy=dialog.conflict_strategy,
            dry_run=dialog.dry_run,
        )
        self._connect_task_signals(runnable)

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
        photos = self._photo_list_controller.list_photos()
        self._photo_list_model.load_photos(photos)
        for photo in photos:
            self._photo_list_controller.load_thumbnail(photo.id, photo.path.raw_path)  # type: ignore[arg-type]  # photo.id is UUID | None, guaranteed set by Photo.__post_init__

    def _on_settings_clicked(self) -> None:
        """Open the modal SettingsDialog; the dialog owns its own save/cancel flow.

        Step 13: settings are persisted synchronously through QSettings (sub-ms),
        so no worker is needed here. The dialog rejects on cancel or validation
        failure that the user chose to abandon; accept only happens after a
        successful save. Restart prompts for theme / language changes are
        documented in docs/development/configuration.md §3 (this round ships
        the persistence; hot-reload of theme is a follow-up).
        """
        dialog = SettingsDialog(self._settings_controller, self)
        dialog.exec()

    def _on_detect_duplicates_clicked(self) -> None:
        """Run duplicate detection and pop up the read-only report dialog.

        B1 首版只读：detect_duplicates_controller.detect_and_show() 内已编排
        同步查询 + DuplicateReportDialog 展示，且对空结果/异常均有兜底文案。
        不下沉 Worker——查重是 SQL 下推的快速查询。
        """
        self._context.detect_duplicates_controller.detect_and_show()

    # ---- Face recognition (match persons) ----

    def _on_match_clicked(self) -> None:
        """Start the face-recognition (match persons) workflow on click.

        Delegates to MatchPersonsController which owns the single-flight guard
        (AC-014) — the window never re-implements running state. When the
        controller refuses (already running / no persons / no photos / all
        photos already matched) it returns ``None`` with a human-readable
        ``last_refusal_reason`` surfaced in the status bar. A submitted
        runnable disables this action until a terminal signal (completed /
        failed / cancelled) re-enables it and releases the controller guard.
        """
        runnable = self._match_controller.start_match()
        if runnable is None:
            reason = self._match_controller.last_refusal_reason
            self._status_label.setText(reason or "Face recognition unavailable.")
            return
        self._match_action.setEnabled(False)
        self._active_runnable = runnable
        self._cancel_action.setEnabled(True)
        self._match_controller.connect_signals(
            runnable,
            self._on_started,  # type: ignore[arg-type]  # Qt Slot vs Callable variance, existing convention
            self._on_progress,  # type: ignore[arg-type]
            self._on_match_completed,  # type: ignore[arg-type]
            self._on_match_failed,  # type: ignore[arg-type]
            cancelled=self._on_match_cancelled,  # type: ignore[arg-type]
        )

    def _on_match_completed(self, event: TaskCompleted) -> None:
        """Handle match completion: shared finish, re-enable, review refresh.

        ``_on_completed`` resets progress/status and refreshes the photo list;
        the match action is re-enabled and the pending-review queue re-queried
        so freshly created PENDING results surface when the user opens Review.
        """
        self._on_completed(event)
        self._match_action.setEnabled(True)
        self._refresh_review_pending()

    def _on_match_failed(self, event: TaskFailed) -> None:
        """Handle match failure: shared error surface + re-enable the action.

        The concrete error is already surfaced by ``_on_failed`` (status label +
        QMessageBox); re-enabling lets the user retry after correcting the cause
        (e.g. installing the model pack or importing persons).
        """
        self._on_failed(event)
        self._match_action.setEnabled(True)

    def _on_match_cancelled(self, event: TaskCancelled) -> None:
        """Handle cooperative cancellation: reset progress and re-enable."""
        self._cancel_action.setEnabled(False)
        self._progress.setValue(0)
        self._status_label.setText(f"{event.task_name} cancelled.")
        self._match_action.setEnabled(True)

    # ------------------------------------------------------------------
    # Phase 5 Commit 1: Export UI wiring
    # ------------------------------------------------------------------

    def _on_export_clicked(self) -> None:
        """Open the modal ExportDialog; on accept, dispatch the export task.

        Mirrors the archive flow: the dialog collects scope / format / output
        path, then the runnable is submitted through the worker-backed
        ExportController (two-phase progress off the UI thread). The action is
        disabled while a run is in flight and re-enabled by every terminal
        signal (completed / failed). ``connect_signals`` exposes exactly four
        channels — there is no cancelled signal on ExportController (Phase 5
        baseline contract), so no cancellation slot is fabricated; the Cancel
        toolbar action stays untouched for export runs.
        """
        dialog = ExportDialog(parent=self, active_criteria=self._current_criteria)
        if not dialog.exec():
            return
        output_path = dialog.output_path
        if output_path is None:
            # Defensive: _on_accept validates a non-empty path before
            # accepting, so this branch is unreachable in practice.
            return
        self._export_action.setEnabled(False)
        self._progress.setValue(0)
        self._status_label.setText("Exporting ...")
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
        self._export_controller.connect_signals(
            runnable,
            self._on_export_started,  # type: ignore[arg-type]  # Qt Slot vs Callable variance, existing convention
            self._on_export_progress,  # type: ignore[arg-type]
            self._on_export_completed,  # type: ignore[arg-type]
            self._on_export_failed,  # type: ignore[arg-type]
        )

    def _on_export_started(self, event: TaskStarted) -> None:
        """Reflect export start in the status bar (delegates to shared slot)."""
        self._on_started(event)

    def _on_export_progress(self, event: TaskProgress) -> None:
        """Update the progress bar from the two-phase export progress events."""
        self._on_progress(event)

    def _on_export_completed(self, event: TaskCompleted) -> None:
        """Reflect completion via the shared slot and re-enable the action."""
        self._on_completed(event)
        self._export_action.setEnabled(True)

    def _on_export_failed(self, event: TaskFailed) -> None:
        """Surface the failure via the shared slot and re-enable the action."""
        self._on_failed(event)
        self._export_action.setEnabled(True)

    def _refresh_review_pending(self) -> None:
        """Re-query recognition results so newly created PENDING entries surface.

        Called after face recognition completes so the next ReviewDialog open
        shows fresh pending results. Uses only the existing read API
        (ReviewController.list_pending) and reflects the count in the status
        bar as lightweight feedback — Review business rules are untouched.
        """
        pending = self._review_controller.list_pending()
        self._status_label.setText(
            f"{len(pending)} recognition result(s) awaiting review"
        )
