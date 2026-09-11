"""Port for discovering photo files on disk."""

from pathlib import Path
from typing import Protocol

from typing import Final

from photo_archiver.application.dtos import PhotoScanItem

# ADR-036 D5：递归深度上限（环检测之外的第二道保险）。
DEFAULT_SCAN_MAX_DEPTH: Final = 32


class PhotoFileScanner(Protocol):
    """Discover photo candidates under a folder."""

    def scan(
        self,
        folder_path: Path,
        *,
        recursive: bool,
        supported_extensions: tuple[str, ...],
        max_depth: int = DEFAULT_SCAN_MAX_DEPTH,
    ) -> list[PhotoScanItem]:
        """Return discovered photo candidates.

        ``max_depth`` bounds recursion depth below the root (ADR-036 D5 belt
        besides loop detection); implementations must never follow directory
        symlinks/junctions.
        """