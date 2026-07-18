"""Use case boundary for the archive workflow."""

from uuid import UUID

from photo_archiver.application.commands import ArchivePhotosCommand
from photo_archiver.application.dtos import ArchivePlan, ArchiveResult


class ArchivePhotosUseCase:
    """Define the archive photos use case contract.

    Implementations orchestrate ArchivePlanner → ArchiveExecutor with a
    UnitOfWork boundary so failed runs roll back in-progress ArchiveRecord
    persistence. CLI, UI (Step 12), and tests share this same boundary.

    review M-3 fix: ``preview`` is exposed here so the presentation layer
    (ArchiveController) depends on the UseCase Protocol only, not on the
    concrete ArchivePlanner service class — keeping presentation → application
    dependencies at the Protocol boundary per DEP-010.
    """

    def preview(
        self,
        archive_root: str,
        person_ids: tuple[UUID, ...] = (),
    ) -> ArchivePlan:  # type: ignore[empty-body]
        """Synchronously plan the archive and return the plan for UI preview.

        No filesystem mutation — the returned ArchivePlan is side-effect free
        so callers (CLI dry-run, UI preview dialog) can inspect it safely.
        """
        raise NotImplementedError

    def execute(self, command: ArchivePhotosCommand) -> ArchiveResult:  # type: ignore[empty-body]
        """Plan and execute archiving for the command's persons."""
        raise NotImplementedError
