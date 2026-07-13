"""Use case boundary for scanning and registering photos."""

from typing import Protocol

from photo_archiver.application.commands import ScanAndRegisterPhotosCommand
from photo_archiver.application.dtos import ScanAndRegisterPhotosResult


class ScanAndRegisterPhotosUseCase(Protocol):
    """Scan a folder and persist discovered photos."""

    def execute(self, command: ScanAndRegisterPhotosCommand) -> ScanAndRegisterPhotosResult:
        """Run the scan-and-register workflow."""
