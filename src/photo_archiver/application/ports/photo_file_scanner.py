"""Port for discovering photo files on disk."""

from pathlib import Path
from typing import Protocol

from photo_archiver.application.dtos import PhotoScanItem


class PhotoFileScanner(Protocol):
    """Discover photo candidates under a folder."""

    def scan(
        self,
        folder_path: Path,
        *,
        recursive: bool,
        supported_extensions: tuple[str, ...],
    ) -> list[PhotoScanItem]:
        """Return discovered photo candidates."""