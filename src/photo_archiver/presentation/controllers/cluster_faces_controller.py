"""Controller coordinating the face-clustering workflow (D-4).

Mirrors :class:`RecognitionRunController`: single-flight guard, worker
submission through :class:`ClusterFacesTask`, guard release on the
runnable's terminal event. The clustering use case is always assembled
(聚类只读既有观测，不依赖模型包) — refusals cover in-flight submissions
and defensive ``None`` use cases.
"""

from uuid import UUID

from PySide6.QtCore import QObject, Slot

from photo_archiver.application import ClusterFacesUseCase
from photo_archiver.application.commands import StartClusteringRunCommand
from photo_archiver.workers import ClusterFacesTask, QtWorkerExecutor, QtWorkerRunnable
from photo_archiver.presentation.ui_text import CLUSTER_UNAVAILABLE, REFUSAL_CLUSTER_IN_FLIGHT


class ClusterFacesController(QObject):
    """Bridge clustering requests to worker execution."""

    def __init__(
        self,
        use_case: ClusterFacesUseCase | None,
        executor: QtWorkerExecutor,
        parent: QObject | None = None,
    ) -> None:
        """Initialize with the clustering use case and worker executor."""
        super().__init__(parent)
        self._use_case = use_case
        self._executor = executor
        self._active_runnable: QtWorkerRunnable | None = None
        self.last_refusal_reason: str | None = None

    @property
    def is_running(self) -> bool:
        """Whether a clustering run is currently in flight."""
        return self._active_runnable is not None

    def start_cluster(self, recognition_run_id: UUID) -> QtWorkerRunnable | None:
        """Start one clustering execution and return its runnable handle.

        Returns ``None`` — with :attr:`last_refusal_reason` recording why —
        when a clustering task is already in flight or the use case is absent.
        Reruns are never blocked by existing cluster runs (Core semantics).
        """
        self.last_refusal_reason = None
        if self._active_runnable is not None:
            self.last_refusal_reason = REFUSAL_CLUSTER_IN_FLIGHT
            return None
        if self._use_case is None:
            self.last_refusal_reason = CLUSTER_UNAVAILABLE
            return None
        task = ClusterFacesTask(self._use_case, StartClusteringRunCommand(recognition_run_id))
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
        """Connect the runnable's task signals; terminal events release the guard."""
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

    def _make_releaser(self, runnable: QtWorkerRunnable):
        """Build an arity-agnostic slot that clears the guard for ``runnable``."""

        def _release_on_terminal(*_args: object) -> None:
            if self._active_runnable is runnable:
                self._active_runnable = None

        return _release_on_terminal
