"""Command for scanning a photo folder."""

from dataclasses import dataclass
from pathlib import Path

DEFAULT_SUPPORTED_PHOTO_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
)


@dataclass(frozen=True, slots=True)
class ScanPhotoFolderCommand:
    """Request discovering photos under a folder."""

    folder_path: Path
    recursive: bool = True
    supported_extensions: tuple[str, ...] = DEFAULT_SUPPORTED_PHOTO_EXTENSIONS