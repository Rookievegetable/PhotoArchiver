"""Worker task wrappers for application use cases."""

from photo_archiver.application.commands import ImportPeopleCommand, ScanAndRegisterPhotosCommand
from photo_archiver.application.dtos import ImportPeopleResult, ScanAndRegisterPhotosResult
from photo_archiver.application.services import ScanAndRegisterPhotosService
from photo_archiver.application.use_cases import ImportPeopleUseCase, ScanAndRegisterPhotosUseCase
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
        """Execute the scan use case with per-item progress streamed through the task."""
        self.raise_if_cancelled()
        self.report_progress("Scanning photos")
        if isinstance(self._use_case, ScanAndRegisterPhotosService):
            with self._use_case.bind_progress_reporter(self):
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