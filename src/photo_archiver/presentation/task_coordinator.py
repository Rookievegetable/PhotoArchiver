"""Window-local admission and identity-safe worker event routing.

This is Presentation state, not executor serialization or a plugin sandbox.
Reservations cover modal/nested dispatch as well as worker submission. Only
QObject-bound slots consume worker signals, on the coordinator's GUI thread.
"""

from collections.abc import Callable
from dataclasses import dataclass
from weakref import ref

from loguru import logger
from PySide6.QtCore import QObject, Signal, Slot

from photo_archiver.workers import QtWorkerRunnable
from photo_archiver.workers.events import (
    TaskCancelled,
    TaskCompleted,
    TaskEvent,
    TaskFailed,
    TaskProgress,
    TaskStarted,
)


@dataclass(eq=False)
class _Reservation:
    label: str
    runnable: QtWorkerRunnable | None = None
    task_id: str = ""
    cancelling: bool = False
    terminal: bool = False


class _TaskRoute(QObject):
    """Bind a signal receiver to one admission, including legacy empty-ID events."""

    def __init__(self, owner: "TaskCoordinator", reservation: _Reservation) -> None:
        super().__init__(owner)
        self._owner = ref(owner)
        self._reservation = reservation

    @Slot(object)
    def receive(self, event: TaskEvent) -> None:
        owner = self._owner()
        if owner is not None:
            owner.receive(self._reservation, event)


class TaskCoordinator(QObject):
    """Track the sole window operation and forward only its accepted events.

    Reserve before opening a dialog or invoking a controller. Bind the returned
    runnable before wiring/replay; release an unbound reservation in a finally
    block. Terminal delivery stays busy through synchronous refresh/error UI.
    """

    changed = Signal()
    started = Signal(object)
    progress = Signal(object)
    terminal = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        """Create an idle coordinator on the calling (GUI) thread."""
        super().__init__(parent)
        self._reservation: _Reservation | None = None

    @property
    def is_busy(self) -> bool:
        """Include preparation, modal operations and cancellation acknowledgement."""
        return self._reservation is not None

    @property
    def label(self) -> str:
        """Return the admitted operation's display name."""
        return self._reservation.label if self._reservation else ""

    @property
    def active_runnable(self) -> QtWorkerRunnable | None:
        """Return the tracked worker, never an independently writable UI handle."""
        return self._reservation.runnable if self._reservation else None

    @property
    def can_cancel(self) -> bool:
        """Only an attached, non-terminal worker can receive one cancel request."""
        active = self._reservation
        return bool(active and active.runnable and not active.cancelling and not active.terminal)

    @property
    def is_cancelling(self) -> bool:
        """Whether cancellation was requested but no terminal was handled yet."""
        return bool(self._reservation and self._reservation.cancelling)

    def reserve(self, label: str) -> _Reservation | None:
        """Admit an operation, or refuse without touching the current operation."""
        if self.is_busy:
            return None
        self._reservation = _Reservation(label)
        self.changed.emit()
        return self._reservation

    def release(self, reservation: _Reservation) -> None:
        """Release only this unsubmitted reservation (cancel/refusal/exception)."""
        if self._reservation is reservation and reservation.runnable is None:
            self._reservation = None
            self.changed.emit()

    def bind(
        self,
        runnable: QtWorkerRunnable,
        connect: Callable[..., None],
    ) -> None:
        """Attach a submitted worker, initialize state, then connect and replay.

        ``connect`` is an existing controller's connect_signals method. Some
        controllers replay themselves; the final replay is harmless because
        terminal acceptance is deduplicated before any UI side effect.
        """
        active = self._reservation
        if active is None or active.runnable is not None:
            raise RuntimeError("Task binding requires an unbound reservation")
        active.runnable = runnable
        active.task_id = getattr(getattr(runnable, "task", None), "task_id", "")
        route = _TaskRoute(self, active)
        self.changed.emit()
        try:
            connect(
                runnable, route.receive, route.receive, route.receive, route.receive,
                cancelled=route.receive,
            )
        except Exception:
            # Submission already happened. Keep ownership and a terminal path
            # even if a controller fails partway through its signal wiring.
            runnable.signals.completed.connect(route.receive)
            runnable.signals.failed.connect(route.receive)
            runnable.signals.cancelled.connect(route.receive)
            runnable.replay_pending_terminal()
            raise
        runnable.replay_pending_terminal()

    def cancel(self) -> bool:
        """Request cancellation once; retain admission until a terminal arrives."""
        active = self._reservation
        if not self.can_cancel or active is None or active.runnable is None:
            return False
        active.cancelling = True
        self.changed.emit()
        try:
            active.runnable.cancel("User requested cancel")
        except Exception:
            active.cancelling = False
            self.changed.emit()
            logger.exception("Unable to request task cancellation")
            return False
        return True

    def receive(self, reservation: _Reservation, event: TaskEvent) -> None:
        """Accept only the current route and matching non-empty execution ID."""
        if self._reservation is not reservation or reservation.terminal:
            return
        if event.task_id and reservation.task_id and event.task_id != reservation.task_id:
            return
        if isinstance(event, (TaskCompleted, TaskFailed, TaskCancelled)):
            # Deduplicate *before* refresh or modal error UI can pump events.
            reservation.terminal = True
            self.changed.emit()
            try:
                self.terminal.emit(event)
            finally:
                # Retire only this route before availability observers can
                # admit a new operation. Late queued deliveries are discarded.
                for route in self.children():
                    if isinstance(route, _TaskRoute) and route._reservation is reservation:
                        route.deleteLater()
                self._reservation = None
                self.changed.emit()
        elif isinstance(event, TaskStarted):
            self.started.emit(event)
        elif isinstance(event, TaskProgress):
            self.progress.emit(event)
