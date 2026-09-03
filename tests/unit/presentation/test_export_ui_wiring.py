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
from photo_archiver.application.services.export_service import ExportService
from photo_archiver.app import bootstrap_application  # noqa: F401
from photo_archiver.domain import MatchStatus, PhotoSearchCriteria
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.controllers.export_controller import ExportController
from photo_archiver.presentation.views import main_window as main_window_module
from photo_archiver.presentation.views.export_dialog import ExportDialog
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

        def replay_pending_terminal(self) -> None:
            """Interface parity with QtWorkerRunnable (no-op: no terminal retained)."""

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
        active_criteria: PhotoSearchCriteria | None = None,
    ) -> None:
        self.parent = parent
        self._accepted = accepted
        self._output_path = output_path
        self._scope = scope if scope is not None else ExportScope.FILTERED
        self._format_name = format_name
        self.active_criteria = active_criteria

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
    active_criteria: PhotoSearchCriteria | None = None,
):
    """Replace the dialog + controller.export with recorders; keep real wiring.

    The real ``ExportController.connect_signals`` staticmethod is left intact
    so the fake runnable's real Qt signals flow through the production wiring
    into the window slots.
    """
    calls: list[dict] = []
    runnable = _make_runnable()
    created: list[_FakeExportDialog] = []

    def _dialog_factory(parent=None, active_criteria=None) -> _FakeExportDialog:
        """Build the fake dialog at call time so the parent wiring is captured."""
        dialog = _FakeExportDialog(
            parent=parent,
            accepted=accepted,
            output_path=output_path,
            scope=scope,
            format_name=format_name,
            active_criteria=active_criteria,
        )
        created.append(dialog)
        return dialog

    monkeypatch.setattr(main_window_module, "ExportDialog", _dialog_factory)
    monkeypatch.setattr(
        window._export_controller,
        "export",
        lambda output_path, scope=ExportScope.ALL, format_name=None, criteria=None: (
            calls.append(
                {
                    "path": output_path,
                    "scope": scope,
                    "format": format_name,
                    "criteria": criteria,
                }
            )
            or runnable
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
            "criteria": None,
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
        {
            "path": calls[0]["path"],
            "scope": ExportScope.FILTERED,
            "format": "csv",
            "criteria": None,
        }
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


# ── Final Audit evidence tests (Phase 5 Commit 3) ────────────────────────────
# The baseline audit's §13 unit-test plan lists two behaviors Commit 1 did not
# deliver tests for: the REAL dialog's control→property mapping + empty-path
# refusal (AC-003/AC-010) and a second successful export after re-enable
# (AC-014). Added during the Phase 5 Final Audit to close the evidence gap —
# no production code is touched.


def test_real_dialog_collects_scope_format_and_refuses_empty_path(qtbot, tmp_path, monkeypatch) -> None:
    """AC-003/AC-010: the real ExportDialog maps controls to properties.

    Defaults are ALL/xlsx/no-path; switching the radio + combo updates the
    properties; OK without a path is refused (recorded QMessageBox.warning,
    dialog not accepted); with a path the dialog accepts and exposes it.
    """
    from PySide6.QtWidgets import QMessageBox

    window = _make_window(qtbot, tmp_path)
    warnings: list[tuple[str, str]] = []

    def _record_warning(parent, title: str, message: str) -> int:
        warnings.append((title, message))
        return 0

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(_record_warning))

    dialog = ExportDialog(parent=window)
    qtbot.addWidget(dialog)

    # Defaults (AC-003): ALL scope, xlsx format, no path chosen yet.
    assert dialog.scope is ExportScope.ALL
    assert dialog.format_name == "xlsx"
    assert dialog.output_path is None

    # Control → property mapping on the REAL widget surface.
    dialog._scope_radios[ExportScope.FILTERED].setChecked(True)
    dialog._format_combo.setCurrentText("CSV (.csv)")
    assert dialog.scope is ExportScope.FILTERED
    assert dialog.format_name == "csv"

    # AC-010: OK without a path is refused — warning recorded, no accept.
    dialog._on_accept()
    assert warnings and warnings[0][0] == "No output path"
    assert "export file destination" in warnings[0][1]
    assert dialog.result() != 1  # not QDialog.DialogCode.Accepted

    # With a path the dialog accepts and exposes the chosen value.
    chosen = tmp_path / "report.csv"
    dialog._path_edit.setText(str(chosen))
    dialog._on_accept()
    assert dialog.result() == 1
    assert dialog.output_path == chosen


def test_reenabled_action_permits_second_export(qtbot, tmp_path, monkeypatch) -> None:
    """AC-014: after completed re-enables the action, a second export submits.

    Each submit gets its own runnable (fresh signal wiring, no reuse), the
    first run's completed signal re-enables the action, and the second
    trigger reaches the controller again.
    """
    window = _make_window(qtbot, tmp_path)
    calls: list = []
    runnables: list = []
    dialog = _FakeExportDialog(output_path=tmp_path / "second.csv")
    monkeypatch.setattr(
        main_window_module, "ExportDialog",
        lambda parent=None, active_criteria=None: dialog,
    )
    monkeypatch.setattr(
        window._export_controller,
        "export",
        lambda output_path, scope, format_name, criteria=None: (
            calls.append((output_path, scope, format_name, criteria))
            or runnables.append(_make_runnable())
            or runnables[-1]
        ),
    )

    window._export_action.trigger()
    assert len(calls) == 1
    assert window._export_action.isEnabled() is False  # first run in flight

    runnables[0].signals.completed.emit(TaskCompleted("export", "task_1"))
    assert window._export_action.isEnabled() is True  # re-enabled for re-export

    window._export_action.trigger()
    assert len(calls) == 2  # second export actually dispatched
    assert runnables[0] is not runnables[1]  # fresh runnable per submission


# ── Phase 7 Commit 3: scope selection wiring (FEATURE-004 F2/F3/D3/F5) ──


def test_filter_criteria_is_held_updated_and_cleared(qtbot, tmp_path) -> None:
    """F2: _current_criteria mirrors the FilterBar criteria — set/update/clear.

    Holds ONLY the criteria snapshot, never a copied photo list: the list refresh
    stays the existing ``_on_filter_changed`` path (unchanged protocol), and the
    export re-queries via PhotoRepository.search at execution time.
 A cleared
    filter (None) empties the holding point so FILTERED becomes unselectable.
.
    """
    window = _make_window(qtbot, tmp_path)
    criteria_a = PhotoSearchCriteria(match_status=MatchStatus.PENDING)
    window._on_filter_changed(criteria_a)
    assert window._current_criteria is criteria_a

    criteria_b = PhotoSearchCriteria(match_status=MatchStatus.APPROVED)
    window._on_filter_changed(criteria_b)
    assert window._current_criteria is criteria_b  # updated, not accumulated

    window._on_filter_changed(None)
    assert window._current_criteria is None  # cleared — no active filter


def test_export_dialog_filtered_requires_active_criteria(qtbot, tmp_path) -> None:
    """F3: real dialog — FILTERED radio enabled with a criteria, disabled without."""

    window = _make_window(qtbot, tmp_path)
    with_criteria = ExportDialog(parent=window, active_criteria=PhotoSearchCriteria(match_status=MatchStatus.PENDING))
    qtbot.addWidget(with_criteria)
    assert with_criteria._scope_radios[ExportScope.FILTERED].isEnabled() is True

    without_criteria = ExportDialog(parent=window, active_criteria=None)
    qtbot.addWidget(without_criteria)
    assert without_criteria._scope_radios[ExportScope.FILTERED].isEnabled() is False
    assert (
        without_criteria._scope_radios[ExportScope.FILTERED].toolTip()
        == "Set a filter in the filter bar to enable this scope."
    )


def test_export_dialog_current_batch_always_disabled_and_has_tooltip(qtbot, tmp_path) -> None:
    """D3: real dialog — CURRENT_BATCH radio stays visible but never selectable."""

    window = _make_window(qtbot, tmp_path)
    dialog = ExportDialog(parent=window)
    qtbot.addWidget(dialog)
    radio = dialog._scope_radios[ExportScope.CURRENT_BATCH]
    assert radio.isEnabled() is False
    assert "not implemented" in radio.toolTip()


def test_export_dialog_all_always_enabled(qtbot, tmp_path) -> None:
    """ALL scope radio stays always enabled (unchanged behavior)."""

    window = _make_window(qtbot, tmp_path)
    dialog = ExportDialog(parent=window)
    qtbot.addWidget(dialog)
    assert dialog._scope_radios[ExportScope.ALL].isEnabled() is True
    assert dialog.scope is ExportScope.ALL  # still the default


def test_export_forwards_criteria_by_scope(qtbot, tmp_path, monkeypatch) -> None:
    """F5: ALL → criteria=None; FILTERED → the held _current_criteria snapshot.â†©

    The held criteria is forwarded verbatim into controller.export — proving the wiring
    passes the criteria snapshot (not a copied photo list).
    """
    window = _make_window(qtbot, tmp_path)
    held = PhotoSearchCriteria(match_status=MatchStatus.PENDING)
    window._current_criteria = held

    calls, _, _ = _stub_export(window, monkeypatch, scope=ExportScope.FILTERED)
    window._export_action.trigger()
    assert calls == [{
        "path": Path("export.csv"),
        "scope": ExportScope.FILTERED,
        "format": "csv",
        "criteria": held,
    }]

    calls2, _, _ = _stub_export(window, monkeypatch, scope=ExportScope.ALL)
    window._export_action.setEnabled(True)  # re-enable between the two runs
    window._export_action.trigger()
    assert calls2 == [{
        "path": Path("export.csv"),
        "scope": ExportScope.ALL,
        "format": "csv",
        "criteria": None,
    }]


class _SentinelExporter:
    """Sentinel Exporter — guard fires before any exporter interaction."""


class _DummyRepo:
    """Minimal repo that proves the dispatch guard fires before any repository call."""

    def __getattr__(self, name) -> object:
        raise AssertionError(f"FILTERED+None guard must reject before contacting {name}")


class _RecordingExecutor:
    """Fake QtWorkerExecutor — records the submitted task instead of running it."""

    def __init__(self) -> None:
        self.submitted: list[object] = []

    def submit(self, task) -> object:
        self.submitted.append(task)
        return task


def test_service_guard_still_rejects_filtered_without_criteria_through_real_chain(qtbot, tmp_path) -> None:
    """Guard: bypassing the UI — controller→task→service still raises ValueError.

	The UI disable is the first UX layer; the Commit-2 Service invariant is the
	second: FILTERED + criteria=None is rejected even when a caller drives the
	real ExportController → ExportTask → ExportService chain without a criteria.
	"""
    import pytest

    service = ExportService(
        person_repository=_DummyRepo(),
        photo_repository=_DummyRepo(),
        recognition_repository=_DummyRepo(),
        archive_record_repository=_DummyRepo(),
    )
    controller = ExportController(
        service=service,
        exporter=_SentinelExporter(),  # type: ignore[arg-type]
        executor=_RecordingExecutor(),  # type: ignore[arg-type]
    )

    runnable = controller.export(
        Path("export.csv"), scope=ExportScope.FILTERED, criteria=None,
    )

    with pytest.raises(ValueError, match="FILTERED requires a PhotoSearchCriteria"):
        runnable.run()

