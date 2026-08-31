"""MainWindow UI wiring tests for the Export Data action (Phase 5 Commit 1).

Covers the dialog-gated trigger (rejected dialog → no submit), scope/format
forwarding to the controller, running-state action disable, real started /
two-phase progress signals, terminal-state re-enable + feedback, and the
defensive missing-output-path guard. ``ExportController.export`` is stubbed
to return a controllable fake runnable (real Qt signals) so the window wiring
is exercised deterministically without Qt threads or real file writes; the
REAL ``connect_signals`` staticmethod stays in the loop (wiring under test).
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from pathlib import Path

from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.app import bootstrap_application  # noqa: F401
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.views import main_window as main_window_module
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.workers.events import (
    TaskCompleted,
    TaskFailed,
    TaskProgress,
    TaskStarted,
)


def _make_runnable():
    """Build a controllable runnable with real Qt signals (smoke-test pattern)."""
    from PySide6.QtCore import QObject, Signal

    class Signals(QObject):
        started = Signal(object)
        progress = Signal(object)
        completed = Signal(object)
        failed = Signal(object)
        cancelled = Signal(object)

    class FakeRunnable:
        def __init__(self) -> None:
            self.signals = Signals()
            self.cancel_calls: list[str] = []

        def cancel(self, reason: str = "") -> None:
            """Record cooperative-cancellation requests for later assertions."""
            self.cancel_calls.append(reason)

    return FakeRunnable()


class _FakeExportDialog:
    """Dialog stub accepted by ``_on_export_clicked`` — properties, no Qt modal.

    Mirrors the real ``ExportDialog`` read surface used by the window:
    ``exec()``, ``output_path``, ``scope``, ``format_name``.
    """

    def __init__(
        self,
        parent=None,
        *,
        accepted: bool = True,
        output_path: Path | None = None,
        scope: ExportScope | None = None,
        format_name: str = "csv",
    ) -> None:
        self.parent = parent
        self._accepted = accepted
        self._output_path = output_path
        self._scope = scope if scope is not None else ExportScope.FILTERED
        self._format_name = format_name

    def exec(self) -> int:
        """Return 1 (accepted) or 0 (rejected) like QDialog.DialogCode."""
        return 1 if self._accepted else 0

    @property
    def output_path(self) -> Path | None:
        """Return the (validated) output path the user chose."""
        return self._output_path

    @property
    def scope(self) -> ExportScope:
        """Return the selected export scope."""
        return self._scope

    @property
    def format_name(self) -> str:
        """Return the canonical format name for the exporter lookup."""
        return self._format_name


def _make_window(qtbot, tmp_path) -> MainWindow:
    """Build a real MainWindow over a tmp SQLite context (smoke-test pattern)."""
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'export_ui.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    window = MainWindow(context)
    qtbot.addWidget(window)
    return window


def _stub_export(
    window: MainWindow,
    monkeypatch,
    *,
    accepted: bool = True,
    output_path: Path | None = Path("export.csv"),
    scope: ExportScope | None = None,
    format_name: str = "csv",
):
    """Replace the dialog + controller.export with recorders; keep real wiring.

    The real ``ExportController.connect_signals`` staticmethod is left intact
    so the fake runnable's real Qt signals flow through the production wiring
    into the window slots.
    """
    calls: list[dict] = []
    runnable = _make_runnable()
    created: list[_FakeExportDialog] = []

    def _dialog_factory(parent=None) -> _FakeExportDialog:
        """Build the fake dialog at call time so the parent wiring is captured."""
        dialog = _FakeExportDialog(
            parent=parent,
            accepted=accepted,
            output_path=output_path,
            scope=scope,
            format_name=format_name,
        )
        created.append(dialog)
        return dialog

    monkeypatch.setattr(main_window_module, "ExportDialog", _dialog_factory)
    monkeypatch.setattr(
        window._export_controller,
        "export",
        lambda output_path, scope=ExportScope.ALL, format_name=None: (
            calls.append({"path": output_path, "scope": scope, "format": format_name}) or runnable
        ),
    )
    return calls, runnable, created


def test_export_action_exists_and_enabled_by_default(qtbot, tmp_path) -> None:
    """The Export Data toolbar action exists and starts enabled."""
    window = _make_window(qtbot, tmp_path)
    assert window._export_action.text() == "Export Data"
    assert window._export_action.isEnabled() is True


def test_rejected_dialog_does_not_submit_and_keeps_action_enabled(qtbot, tmp_path, monkeypatch) -> None:
    """A rejected ExportDialog aborts the flow: no submit, action stays enabled."""
    window = _make_window(qtbot, tmp_path)
    calls, _, _ = _stub_export(window, monkeypatch, accepted=False)

    window._export_action.trigger()

    assert calls == []
    assert window._export_action.isEnabled() is True
    assert window._status_label.text() == "Ready"  # flow never started


def test_accepted_dialog_submits_scope_format_and_disables_action(qtbot, tmp_path, monkeypatch) -> None:
    """An accepted dialog forwards scope/format and locks the action for the run."""
    window = _make_window(qtbot, tmp_path)
    calls, _, created = _stub_export(window, monkeypatch)

    window._export_action.trigger()

    dialog = created[0]
    assert calls == [
        {
            "path": dialog.output_path,
            "scope": ExportScope.FILTERED,
            "format": "csv",
        }
    ]
    assert dialog.parent is window  # dialog is parented to the MainWindow
    assert window._export_action.isEnabled() is False  # in-flight lock
    assert window._progress.value() == 0
    assert window._status_label.text() == "Exporting ..."
    # The shared Cancel action stays untouched for export runs: the controller
    # exposes no cancelled channel, so no cancellation surface is fabricated.
    assert window._cancel_action.isEnabled() is False


def test_started_signal_keeps_action_disabled_and_updates_status(qtbot, tmp_path, monkeypatch) -> None:
    """started updates the status bar and does not unlock the action."""
    window = _make_window(qtbot, tmp_path)
    _, runnable, _ = _stub_export(window, monkeypatch)
    window._export_action.trigger()

    runnable.signals.started.emit(TaskStarted("export", "task_1"))

    assert window._export_action.isEnabled() is False
    assert "started" in window._status_label.text()


def test_progress_two_phase_renders_bar_and_message(qtbot, tmp_path, monkeypatch) -> None:
    """Two-phase export progress: message-only phase → status; (1,1) → full bar."""
    window = _make_window(qtbot, tmp_path)
    _, runnable, _ = _stub_export(window, monkeypatch)
    window._export_action.trigger()

    # Phase 1 (real ExportTask): message-only, no current/total.
    runnable.signals.progress.emit(TaskProgress("export", "task_1", message="Gathering export data"))
    assert window._progress.value() == 0
    assert window._status_label.text() == "Gathering export data"

    # Phase 2 (real ExportTask): "Export finished" with current=1, total=1.
    runnable.signals.progress.emit(
        TaskProgress("export", "task_1", message="Export finished", current=1, total=1)
    )
    assert window._progress.value() == 100  # 1 * 100 / 1


def test_completed_reenables_action_and_refreshes_photo_list(qtbot, tmp_path, monkeypatch) -> None:
    """completed re-enables the action and runs the shared post-task refresh."""
    window = _make_window(qtbot, tmp_path)
    _, runnable, _ = _stub_export(window, monkeypatch)
    window._export_action.trigger()
    photo_refreshed: list[str] = []
    monkeypatch.setattr(window, "_refresh_photo_list", lambda: photo_refreshed.append("photos"))

    runnable.signals.completed.emit(TaskCompleted("export", "task_1"))

    assert window._export_action.isEnabled() is True
    assert window._progress.value() == 100
    assert photo_refreshed == ["photos"]
    assert "complete" in window._status_label.text()


def test_failed_reenables_action_and_surfaces_error(qtbot, tmp_path, monkeypatch) -> None:
    """failed re-enables the action, resets progress, and surfaces the error."""
    window = _make_window(qtbot, tmp_path)
    _, runnable, _ = _stub_export(window, monkeypatch)
    window._export_action.trigger()
    dialogs: list[tuple[str, str]] = []
    from PySide6.QtWidgets import QMessageBox

    def _warning(parent, title: str, message: str) -> int:
        dialogs.append((title, message))
        return 0

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(_warning))

    runnable.signals.failed.emit(TaskFailed("export", RuntimeError("disk full"), "task_1"))

    assert window._export_action.isEnabled() is True
    assert window._progress.value() == 0
    assert "failed" in window._status_label.text()
    assert dialogs and "disk full" in dialogs[0][1]


def test_running_action_disabled_prevents_duplicate_submission(qtbot, tmp_path, monkeypatch) -> None:
    """While in flight the disabled action cannot re-submit through the UI."""
    window = _make_window(qtbot, tmp_path)
    calls, _, _ = _stub_export(window, monkeypatch)
    window._export_action.trigger()
    assert calls == [
        {"path": calls[0]["path"], "scope": ExportScope.FILTERED, "format": "csv"}
    ]

    assert window._export_action.isEnabled() is False  # no double-click surface

    window._export_action.trigger()  # disabled actions emit nothing
    assert len(calls) == 1  # still exactly one submission


def test_missing_output_path_guard_aborts_submission(qtbot, tmp_path, monkeypatch) -> None:
    """An accepted dialog with a None path aborts; the action stays enabled."""
    window = _make_window(qtbot, tmp_path)
    calls, _, _ = _stub_export(window, monkeypatch, output_path=None)

    window._export_action.trigger()

    assert calls == []  # defensive guard: no controller call without a path
    assert window._export_action.isEnabled() is True
