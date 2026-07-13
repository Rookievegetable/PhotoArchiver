"""Use case boundary for scanning photo folders."""

from typing import Protocol

from photo_archiver.application.commands import ScanPhotoFolderCommand
from photo_archiver.application.dtos import ScanPhotoFolderResult


class ScanPhotoFolderUseCase(Protocol):
    """Scan a folder and return discovered photo candidates."""

    def execute(self, command: ScanPhotoFolderCommand) -> ScanPhotoFolderResult:
        """Run the photo folder scanning workflow."""