"""Service implementation for scanning photo folders."""

from photo_archiver.application.commands import ScanPhotoFolderCommand
from photo_archiver.application.dtos import ScanPhotoFolderResult
from photo_archiver.application.ports import PhotoFileScanner
from photo_archiver.application.use_cases import ScanPhotoFolderUseCase


class ScanPhotoFolderService(ScanPhotoFolderUseCase):
    """Scan folders using a file scanner port."""

    def __init__(self, scanner: PhotoFileScanner) -> None:
        """Initialize the service with a scanner port."""
        self._scanner = scanner

    def execute(self, command: ScanPhotoFolderCommand) -> ScanPhotoFolderResult:
        """Return photo candidates discovered under the requested folder."""
        try:
            photos = self._scanner.scan(
                command.folder_path,
                recursive=command.recursive,
                supported_extensions=command.supported_extensions,
            )
            return ScanPhotoFolderResult(
                folder_path=command.folder_path,
                discovered_count=len(photos),
                photos=tuple(photos),
            )
        except OSError as exc:
            return ScanPhotoFolderResult(
                folder_path=command.folder_path,
                errors=(str(exc),),
            )