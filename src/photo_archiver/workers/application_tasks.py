"""Worker task wrappers for application use cases."""

from photo_archiver.application.commands import (
    ArchivePhotosCommand,
    ImportPeopleCommand,
    ScanAndRegisterPhotosCommand,
)
from photo_archiver.application.dtos import (
    ArchiveResult,
    ImportPeopleResult,
    ScanAndRegisterPhotosResult,
)
from photo_archiver.application.use_cases import (
    ArchivePhotosUseCase,
    ImportPeopleUseCase,
    ScanAndRegisterPhotosUseCase,
)
from photo_archiver.workers.task import WorkerTask


class ImportPeopleTask(WorkerTask[ImportPeopleResult]):
    """Run the people import use case as a worker task."""

    def __init__(self, use_case: ImportPeopleUseCase, command: ImportPeopleCommand) -> None:
        """Initialize the task with its application use case and command."""
        super().__init__("import_people")
        self._use_case = use_case
        self._command = command

    def execute(self) -> ImportPeopleResult:
        """Execute the import use case and emit coarse progress updates."""
        self.raise_if_cancelled()
        self.report_progress("Importing people")
        result = self._use_case.execute(self._command)
        self.raise_if_cancelled()
        self.report_progress(
            "People import finished",
            current=result.imported_count + result.skipped_count,
            total=result.imported_count + result.skipped_count + len(result.errors),
        )
        return result


class ScanAndRegisterPhotosTask(WorkerTask[ScanAndRegisterPhotosResult]):
    """Run the scan-and-register photos use case as a worker task."""

    def __init__(
        self,
        use_case: ScanAndRegisterPhotosUseCase,
        command: ScanAndRegisterPhotosCommand,
    ) -> None:
        """Initialize the task with its application use case and command."""
        super().__init__("scan_and_register_photos")
        self._use_case = use_case
        self._command = command

    def execute(self) -> ScanAndRegisterPhotosResult:
        """Execute the scan use case with per-item progress streamed through the task.

        Capability-sniffs for ``bind_progress_reporter`` via ``getattr`` so the
        worker layer depends only on the ``ScanAndRegisterPhotosUseCase`` Protocol
        and the ``ProgressReporter`` port, never on a concrete service class.
        """
        self.raise_if_cancelled()
        self.report_progress("Scanning photos")
        binder = getattr(self._use_case, "bind_progress_reporter", None)
        if binder is not None:
            with binder(self):
                result = self._use_case.execute(self._command)
        else:
            result = self._use_case.execute(self._command)
        self.raise_if_cancelled()
        self.report_progress(
            "Photo scan finished",
            current=result.registered_count + result.skipped_count + result.failed_count,
            total=result.discovered_count,
        )
        return result


class ArchivePhotosTask(WorkerTask[ArchiveResult]):
    """Run the archive photos use case as a worker task.

    Streams coarse two-phase progress: planning (unknown total) then executing
    (per-photo via the result's outcomes). Archive is a batch operation without
    a natural per-item event hook in Step 11's Planner/Executor split — the
    planner is side-effect free and the executor runs synchronously inside the
    service. This task therefore emits two coarse progress updates rather than
    streaming per-item, matching the ImportPeopleTask precedent.
    """

    def __init__(self, use_case: ArchivePhotosUseCase, command: ArchivePhotosCommand) -> None:
        """Initialize the task with its application use case and command."""
        super().__init__("archive_photos")
        self._use_case = use_case
        self._command = command

    def execute(self) -> ArchiveResult:
        """Execute the archive use case with coarse planning/executing progress."""
        self.raise_if_cancelled()
        self.report_progress("Planning archive")
        result = self._use_case.execute(self._command)
        self.raise_if_cancelled()
        archived_total = result.archived_count + result.skipped_count + result.dry_run_count
        self.report_progress(
            "Archive finished",
            current=archived_total,
            total=result.planned_count,
        )
        return result