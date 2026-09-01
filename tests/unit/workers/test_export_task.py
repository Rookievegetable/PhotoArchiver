"""ExportTask threading tests (Phase 7 Commit 1 — scope contract signatures).

Commit 1 of FEATURE-004 only threads the ``criteria`` parameter through the
export chain (contract: docs/health-check/PHASE_7_SCOPE_CONTRACT_REVISION.md
§3/F5/§6). These tests pin the ExportTask → ExportService call surface:

- a supplied ``criteria`` reaches ``service.export`` verbatim, next to scope;
- the defaults (scope=ALL, criteria=None) keep the pre-Commit-1 call surface
  working for existing callers.

Test-double boundary: the service is a recording stub because the unit under
test is the task's *threading* behavior, not data gathering (the real
ExportService + real exporters are exercised by
tests/integration/export/test_export_e2e.py). What remains real: ExportTask,
the WorkerTask lifecycle (run() → started/progress/completed events), and the
domain objects (ExportScope / PhotoSearchCriteria).
"""

from uuid import uuid4

from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.domain import PhotoSearchCriteria
from photo_archiver.workers.export_task import ExportTask


class RecordingExportServiceStub:
    """Record the export() call surface without gathering any data."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, str, ExportScope, PhotoSearchCriteria | None]] = []

    def export(self, exporter, output_path, scope=ExportScope.ALL, criteria=None):  # noqa: ANN001
        self.calls.append((exporter, output_path, scope, criteria))
        return "Exported 0 rows"


class _FakeExporter:
    """Sentinel exporter — the recording service never invokes it."""


def test_export_task_threads_criteria_to_service() -> None:
    """A supplied criteria reaches service.export verbatim, next to scope."""
    service = RecordingExportServiceStub()
    exporter = _FakeExporter()
    criteria = PhotoSearchCriteria(person_id=uuid4())

    task = ExportTask(
        service=service,  # type: ignore[arg-type]
        exporter=exporter,  # type: ignore[arg-type]
        output_path="out/export.csv",
        scope=ExportScope.FILTERED,
        criteria=criteria,
    )
    result = task.run()

    assert result == "Exported 0 rows"
    assert service.calls == [(exporter, "out/export.csv", ExportScope.FILTERED, criteria)]


def test_export_task_defaults_keep_legacy_call_surface() -> None:
    """Default construction threads scope=ALL and criteria=None (compat)."""
    service = RecordingExportServiceStub()
    exporter = _FakeExporter()

    task = ExportTask(
        service=service,  # type: ignore[arg-type]
        exporter=exporter,  # type: ignore[arg-type]
        output_path="out/export.csv",
    )
    task.run()

    assert service.calls == [(exporter, "out/export.csv", ExportScope.ALL, None)]
