"""Use case boundary for scanning and registering photos."""

from typing import Protocol

from photo_archiver.application.commands import ScanAndRegisterPhotosCommand
from photo_archiver.application.dtos import PhotoScanItem, ScanAndRegisterPhotosResult


class ScanAndRegisterPhotosUseCase(Protocol):
    """Scan a folder and persist discovered photos."""

    def execute(self, command: ScanAndRegisterPhotosCommand) -> ScanAndRegisterPhotosResult:
        """Run the scan-and-register workflow."""

    def enumerate_files(self, command: ScanAndRegisterPhotosCommand) -> list[PhotoScanItem]:
        """Enumerate candidate files on the caller's thread (ADR-041, LIMIT-006).

        Called on the main thread before ``execute`` so background workers
        never perform directory enumeration; implementers raise ``OSError``
        on unreadable roots for the caller to surface.
        """
