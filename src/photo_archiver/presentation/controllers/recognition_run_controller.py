"""Controller coordinating the traceable recognition-run workflow (阶段 C Commit 3).

Replaces :class:`MatchPersonsController` as the production recognition entry:
every submission builds a fresh ``StartRecognitionRunCommand`` and runs
``RunRecognitionUseCase`` on the worker thread, so reruns always create a new
``RecognitionRun``. Unlike the old path there is **no already-matched
filtering and no recognition-repository read** — existing ``RecognitionResult``
rows only drive the compatibility dedup inside the service and never prevent a
new detection run.

The controller owns no domain logic: it resolves the photo snapshot, records
the chosen scope in the command's immutable ``parameters``, and mirrors the
MatchPersons single-flight semantics (refuse while in flight; the guard
auto-releases on the runnable's terminal event).
"""

from uuid import UUID

from PySide6.QtCore import QObject, Slot

from photo_archiver.application import RunRecognitionUseCase
from photo_archiver.application.commands import StartRecognitionRunCommand
from photo_archiver.domain import FaceCountRange, PhotoRepository
from photo_archiver.workers import QtWorkerExecutor, QtWorkerRunnable, RunRecognitionTask
from photo_archiver.presentation.ui_text import (
    REFUSAL_MATCH_IN_FLIGHT,
    REFUSAL_NO_PHOTOS,
    STATUS_MATCH_UNAVAILABLE,
)


class RecognitionRunController(QObject):
    """Bridge recognition-run requests to worker execution."""

    def __init__(
        self,
        photos: PhotoRepository,
        use_case: RunRecognitionUseCase | None,
        executor: QtWorkerExecutor,
        parent: QObject | None = None,
    ) -> None:
        """Initialize with the photo query port, use case and worker executor.

        ``use_case`` is ``None`` when the model pack is absent at assembly —
        submission is then refused with the unavailable reason instead of
        raising deep inside the worker.
        """
        super().__init__(parent)
        self._photos = photos
        self._use_case = use_case
        self._executor = executor
        self._active_runnable: QtWorkerRunnable | None = None
        self.last_refusal_reason: str | None = None

    @property
    def is_running(self) -> bool:
        """Whether a recognition run is currently in flight."""
        return self._active_runnable is not None

    def start_run(
        self,
        selected_ranges: tuple[FaceCountRange, ...],
        photo_ids: tuple[UUID, ...] | None = None,
        scope_label: str | None = None,
    ) -> QtWorkerRunnable | None:
        """Start one recognition run and return its runnable handle.

        ``photo_ids=None`` means the whole library; an explicit id tuple runs
        the "re-analyze selection" path. Returns ``None`` — with
        :attr:`last_refusal_reason` recording why — when a run is already in
        flight, the model pack is missing, or the resolved photo snapshot is
        empty. Every accepted submission carries the full snapshot (no
        already-matched filtering): reruns re-detect everything.
        """
        self.last_refusal_reason = None
        if self._active_runnable is not None:
            self.last_refusal_reason = REFUSAL_MATCH_IN_FLIGHT
            return None
        if self._use_case is None:
            self.last_refusal_reason = STATUS_MATCH_UNAVAILABLE
            return None
        photos = self._photos.list_all()
        if photo_ids is None:
            scope, chosen = "all", photos
        else:
            selected = set(photo_ids)
            chosen = [photo for photo in photos if photo.id in selected]
            scope = "selected"
        if not chosen:
            self.last_refusal_reason = REFUSAL_NO_PHOTOS
            return None
        snapshot = [
            (photo.id, photo.path.raw_path) for photo in chosen if photo.id is not None
        ]
        command = StartRecognitionRunCommand(
            photo_ids=tuple(photo_id for photo_id, _ in snapshot),
            images=tuple(raw_path for _, raw_path in snapshot),
            selected_ranges=tuple(selected_ranges),
            parameters={
                # Stage F：scope_label（retry/selected/all）进参数快照，重试运行可追溯。
                "photo_scope": scope_label or scope,
                "photo_count": len(snapshot),
                "face_count_ranges": [str(face_range) for face_range in selected_ranges],
            },
        )
        task = RunRecognitionTask(self._use_case, command)
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
        the single-flight guard so the next run can be submitted. Safe to call
        once per submitted runnable.
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

    def _make_releaser(self, runnable: QtWorkerRunnable):
        """Build an arity-agnostic slot that clears the guard for ``runnable``."""

        def _release_on_terminal(*_args: object) -> None:
            if self._active_runnable is runnable:
                self._active_runnable = None

        return _release_on_terminal
