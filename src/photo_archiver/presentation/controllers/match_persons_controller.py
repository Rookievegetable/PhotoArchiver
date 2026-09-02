"""Controller coordinating the face-recognition (match persons) workflow."""

from PySide6.QtCore import QObject, Slot

from photo_archiver.application import MatchPersonsUseCase
from photo_archiver.application.commands import MatchPersonsCommand
from photo_archiver.domain import PersonRepository, PhotoRepository, RecognitionRepository
from photo_archiver.workers import MatchPersonsTask, QtWorkerExecutor, QtWorkerRunnable


class MatchPersonsController(QObject):
    """Bridge match-persons use case requests to worker execution.

    Mirrors :class:`ScanController`: owns no domain logic, constructs the
    command and submits a worker task; views connect their own slots to the
    returned runnable via :meth:`connect_signals` so the controller never
    touches widget state.

    Unlike scan it gates submission on data preconditions (persons imported,
    photos registered, at least one photo without a recognition result) and
    enforces single-flight semantics: while a match task is in flight
    ``start_match()`` refuses further submissions. The guard auto-releases
    when the connected runnable reaches a terminal state (completed / failed /
    cancelled), so a crashed or cancelled run never deadlocks the action.

    A missing model pack is not special-cased here: the assembled service
    raises ``ModelPackMissing`` during execution, which propagates as the
    task's ``failed`` event and is surfaced to the user through the ``failed``
    slot (AC-009 via the existing error mechanism).
    """

    def __init__(
        self,
        photos: PhotoRepository,
        people: PersonRepository,
        recognition: RecognitionRepository,
        use_case: MatchPersonsUseCase,
        executor: QtWorkerExecutor,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with its query ports and worker executor."""
        super().__init__(parent)
        self._photos = photos
        self._people = people
        self._recognition = recognition
        self._use_case = use_case
        self._executor = executor
        self._active_runnable: QtWorkerRunnable | None = None
        self.last_refusal_reason: str | None = None

    @property
    def is_running(self) -> bool:
        """Whether a match task is currently in flight.

        Phase C (F-002): a finished runnable releases the guard even if its
        terminal signal has not been delivered yet — the queued terminal slot
        and this read race across threads, so the runnable's own finished
        state is the authoritative source.
        """
        return self._active_runnable is not None and not self._active_runnable.is_finished

    def start_match(self) -> QtWorkerRunnable | None:
        """Start a match-persons task and return its runnable handle.

        Returns ``None`` — with :attr:`last_refusal_reason` recording why —
        when a task is already running or a precondition fails. Only photos
        without an existing recognition result are submitted, so re-running
        recognition after an interrupted batch resumes the remainder instead
        of duplicating PENDING results.
        """
        self.last_refusal_reason = None
        if self.is_running:
            self.last_refusal_reason = "A recognition task is already running."
            return None
        if not self._people.list_all():
            self.last_refusal_reason = "No persons imported. Import people first."
            return None
        photos = self._photos.list_all()
        if not photos:
            self.last_refusal_reason = "No photos registered. Scan a folder first."
            return None
        photo_ids = tuple(photo.id for photo in photos if photo.id is not None)
        already_matched = self._recognition.list_first_by_photo_ids(photo_ids)
        pending_ids = tuple(pid for pid in photo_ids if pid not in already_matched)
        if not pending_ids:
            self.last_refusal_reason = (
                "All registered photos already have recognition results."
            )
            return None
        pending_set = set(pending_ids)
        command = MatchPersonsCommand(
            photo_ids=pending_ids,
            images=tuple(photo.path.raw_path for photo in photos if photo.id in pending_set),
        )
        task = MatchPersonsTask(self._use_case, command)
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
        the single-flight guard so the next ``start_match()`` can submit a
        follow-up batch. Safe to call once per submitted runnable.
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

    def _make_releaser(self, runnable: QtWorkerRunnable):
        """Build an arity-agnostic slot that clears the guard for ``runnable``."""

        def _release_on_terminal(*_args: object) -> None:
            if self._active_runnable is runnable:
                self._active_runnable = None

        return _release_on_terminal
