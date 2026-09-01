"""ExportController criteria-threading tests (Phase 7 Commit 1).

Pins the controller half of the scope-contract signature threading (contract:
docs/health-check/PHASE_7_SCOPE_CONTRACT_REVISION.md §3/F5/§6):
``ExportController.export`` accepts an optional ``criteria`` and forwards it
verbatim into the submitted ``ExportTask``.

Test-double boundary: the executor is a recording fake (captures the submitted
task instead of running it on a real QThreadPool) so the test is deterministic
without Qt threads; the service uses the same recording-stub pattern as
tests/unit/workers/test_export_task.py. What remains real: ExportController
(a real QObject), the real ExportTask it constructs, and the domain objects
(ExportScope / PhotoSearchCriteria).
"""

from pathlib import Path
from uuid import uuid4

import pytest

pytest.importorskip("PySide6")

from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.domain import PhotoSearchCriteria
from photo_archiver.presentation.controllers.export_controller import ExportController
from photo_archiver.workers.export_task import ExportTask

_QAPP: object | None = None


@pytest.fixture(autouse=True)
def _ensure_core_application():
    """Create a QCoreApplication once if the suite did not (QObject headroom)."""
    global _QAPP
    from PySide6.QtCore import QCoreApplication

    if QCoreApplication.instance() is None:
        _QAPP = QCoreApplication([])
    yield


class RecordingExecutor:
    """Fake QtWorkerExecutor — records the submitted task instead of running it."""

    def __init__(self) -> None:
        self.submitted: list[object] = []

    def submit(self, task):  # noqa: ANN001
        self.submitted.append(task)
        return task


class RecordingExportServiceStub:
    """Record the export() call surface without gathering any data."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, str, ExportScope, PhotoSearchCriteria | None]] = []

    def export(self, exporter, output_path, scope=ExportScope.ALL, criteria=None):  # noqa: ANN001
        self.calls.append((exporter, output_path, scope, criteria))
        return "Exported 0 rows"


class _FakeExporter:
    """Sentinel exporter registered in the format map."""


def test_export_controller_forwards_criteria_into_submitted_task() -> None:
    """export(criteria=...) reaches the ExportTask and then the service verbatim."""
    service = RecordingExportServiceStub()
    exporter = _FakeExporter()
    executor = RecordingExecutor()
    controller = ExportController(
        service=service,  # type: ignore[arg-type]
        exporter=exporter,  # type: ignore[arg-type]
        executor=executor,  # type: ignore[arg-type]
        exporters={"csv": exporter},  # type: ignore[dict-item]
    )
    criteria = PhotoSearchCriteria(person_id=uuid4())

    runnable = controller.export(
        Path("out/export.csv"),
        scope=ExportScope.FILTERED,
        format_name="csv",
        criteria=criteria,
    )

    assert runnable is executor.submitted[0]
    assert isinstance(runnable, ExportTask)
    # Run the captured task against the recording service: full threading.
    runnable.run()
    assert service.calls == [
        (exporter, str(Path("out/export.csv")), ExportScope.FILTERED, criteria),
    ]


def test_export_controller_defaults_thread_none_criteria() -> None:
    """Default export() threads scope=ALL and criteria=None (compat surface)."""
    service = RecordingExportServiceStub()
    exporter = _FakeExporter()
    executor = RecordingExecutor()
    controller = ExportController(
        service=service,  # type: ignore[arg-type]
        exporter=exporter,  # type: ignore[arg-type]
        executor=executor,  # type: ignore[arg-type]
    )

    runnable = controller.export(Path("out/export.csv"))

    assert isinstance(runnable, ExportTask)
    runnable.run()
    assert service.calls == [
        (exporter, str(Path("out/export.csv")), ExportScope.ALL, None),
    ]
