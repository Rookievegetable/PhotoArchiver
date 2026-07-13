"""DTOs for photo folder scanning workflows."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PhotoScanItem:
    """Photo candidate discovered by a scanner port."""

    path: Path
    original_name: str | None = None


@dataclass(frozen=True, slots=True)
class ScanPhotoFolderResult:
    """Outcome of scanning a photo folder."""

    folder_path: Path
    discovered_count: int = 0
    photos: tuple[PhotoScanItem, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        """Return whether scanning completed without errors."""
        return not self.errors