"""Use case boundary for the archive workflow."""

from photo_archiver.application.commands import ArchivePhotosCommand
from photo_archiver.application.dtos import ArchiveResult


class ArchivePhotosUseCase:
    """Define the archive photos use case contract.

    Implementations orchestrate ArchivePlanner → ArchiveExecutor with a
    UnitOfWork boundary so failed runs roll back in-progress ArchiveRecord
    persistence. CLI, UI (Step 12), and tests share this same boundary.
    """

    def execute(self, command: ArchivePhotosCommand) -> ArchiveResult:  # type: ignore[empty-body]
        """Plan and execute archiving for the command's persons."""
        raise NotImplementedError
