"""Main application window — Step 12 complete workbench.

Toolbar: [Import People] [Scan Folder] [Review Pending] [Archive]
Central: QListView of photos with thumbnails (PhotoListModel)
Status:  progress bar + status label

每个 toolbar action 接对应 controller，长耗时走 QtWorkerExecutor，
短耗时（review approve/reject、archive preview）同步调。
"""

from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
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

from photo_archiver.app.context import ApplicationContext
from photo_archiver.presentation.controllers import (
    ArchiveController,
    ImportPeopleController,
    ScanController,
)
from photo_archiver.presentation.views.archive_preview_dialog import ArchivePreviewDialog
from photo_archiver.presentation.views.photo_list_model import PhotoListModel
from photo_archiver.presentation.views.review_dialog import ReviewDialog
from photo_archiver.presentation.views.settings_dialog import SettingsDialog
from photo_archiver.plugins import PluginRegistry
from photo_archiver.workers.events import TaskCompleted, TaskFailed, TaskProgress, TaskStarted

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
        self._active_runnable = None  # tracks the currently running worker

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
        self._review_controller = self._context.review_controller  # set by bootstrap
        self._photo_list_controller = self._context.photo_list_controller  # set by bootstrap
        self._settings_controller = self._context.settings_controller  # set by bootstrap (Step 13)

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
        self._plugin_registry = PluginRegistry()
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
        """Dispatch a plugin action click to the owning plugin."""
        for plugin in self._plugin_registry.enabled_plugins.values():
            ids_in_plugin = {a.id for a in plugin.actions()}
            if action_id in ids_in_plugin:
                try:
                    plugin.execute_action(action_id)
                except Exception:
                    from loguru import logger
                    logger.exception("Plugin action {} failed", action_id)
                    QMessageBox.warning(
                        self,
                        "Plugin Error",
                        f"Plugin action '{action_id}' failed. See logs for details.",
                    )
                break

    def _build_central(self) -> None:
        """Create the central photo list view."""
        central = QWidget(self)
        layout = QVBoxLayout(central)

        self._photo_list_model = PhotoListModel(parent=self)
        self._photo_list = QListView(self)
        self._photo_list.setModel(self._photo_list_model)
        layout.addWidget(self._photo_list)

        self.setCentralWidget(central)
        # Wire thumbnail loads → model now that _photo_list_model exists.
        self._photo_list_controller.thumbnail_loaded.connect(
            self._photo_list_model.set_thumbnail,
        )

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
        """Open the archive preview dialog; on accept, start the archive task."""
        archive_root = self._context.settings.archive_root
        if archive_root is None:
            QMessageBox.warning(
                self,
                "Archive",
                "ARCHIVE_ROOT is not configured. Set it in .env or use the CLI --archive-root flag.",
            )
            return
        plan = self._archive_controller.preview(archive_root, ())
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
            conflict_strategy=dialog.conflict_strategy,
            dry_run=dialog.dry_run,
        )
        self._connect_task_signals(runnable)

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
