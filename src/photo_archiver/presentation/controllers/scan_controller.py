"""Controller coordinating the scan-and-register photos workflow with the UI."""

from pathlib import Path

from PySide6.QtCore import QObject, Slot

from photo_archiver.application import ScanAndRegisterPhotosCommand, ScanAndRegisterPhotosUseCase
from photo_archiver.workers import QtWorkerExecutor, QtWorkerRunnable, ScanAndRegisterPhotosTask


class ScanController(QObject):
    """Bridge scan-and-register photos workflow requests to worker execution.

    Mirrors :class:`MatchPersonsController`: owns no domain logic, constructs
    the command and submits a worker task; views connect their own slots to
    the returned runnable via the instance :meth:`connect_signals` so the
    controller never touches widget state.

    P0-4: enforces single-flight semantics — while a scan task is in flight
    ``scan_folder()`` refuses further submissions (concurrent scans would
    interleave the shared progress reporter and contend on the write lock).
    The guard auto-releases when the connected runnable reaches a terminal
    state (completed / failed / cancelled), so a cancelled or crashed run
    never deadlocks the action.
    """

    def __init__(
        self,
        use_case: ScanAndRegisterPhotosUseCase,
        executor: QtWorkerExecutor,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with its use case and worker executor."""
        super().__init__(parent)
        self._use_case = use_case
        self._executor = executor
        self._active_runnable: QtWorkerRunnable | None = None
        self.last_refusal_reason: str | None = None

    @property
    def is_running(self) -> bool:
        """Whether a scan task is currently in flight."""
        return self._active_runnable is not None

    def scan_folder(self, folder_path: Path, recursive: bool = True, display_name: str | None = None):
        """Start a scan-and-register task and return its runnable handle.

        Returns ``None`` — with :attr:`last_refusal_reason` recording why —
        when a scan task is already running (P0-4 single-flight).
        """
        self.last_refusal_reason = None
        if self._active_runnable is not None:
            self.last_refusal_reason = "A scan task is already running."
            return None
        command = ScanAndRegisterPhotosCommand(
            folder_path=folder_path,
            recursive=recursive,
            folder_display_name=display_name,
        )
        task = ScanAndRegisterPhotosTask(self._use_case, command)
        runnable = self._executor.submit(task)  # type: ignore[arg-type]  # generics variance
        self._active_runnable = runnable
        return runnable

    def connect_signals(
        self,
        runnable: QtWorkerRunnable,
        started: Slot,
        progress: Slot,
        completed: Slot,
        failed: Slot,
        cancelled: Slot | None = None,
    ) -> None:
        """Connect the runnable's task signals to the provided UI slots.

        Terminal events (completed / failed / cancelled) additionally release
        the single-flight guard so the next ``scan_folder()`` can submit a
        follow-up scan. Safe to call once per submitted runnable.
        """
        signals = runnable.signals
        signals.started.connect(started)
        signals.progress.connect(progress)
        signals.completed.connect(completed)
        signals.failed.connect(failed)
        if cancelled is not None:
            signals.cancelled.connect(cancelled)
        releaser = self._make_releaser(runnable)
        signals.completed.connect(releaser)
        signals.failed.connect(releaser)
        signals.cancelled.connect(releaser)
        # macOS CI race: replay a terminal that fired before this wiring.
        runnable.replay_pending_terminal()
        runnable.replay_pending_terminal()

    def _make_releaser(self, runnable: QtWorkerRunnable):
        """Build an arity-agnostic slot that clears the guard for ``runnable``."""

        def _release_on_terminal(*_args: object) -> None:
            if self._active_runnable is runnable:
                self._active_runnable = None

        return _release_on_terminal
