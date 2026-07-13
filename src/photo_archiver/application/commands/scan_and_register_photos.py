"""Command for scanning a folder and registering discovered photos."""

from dataclasses import dataclass
from pathlib import Path

from photo_archiver.application.commands.scan_photo_folder import DEFAULT_SUPPORTED_PHOTO_EXTENSIONS


@dataclass(frozen=True, slots=True)
class ScanAndRegisterPhotosCommand:
    """Request scanning a folder and persisting discovered photos."""

    folder_path: Path
    recursive: bool = True
    supported_extensions: tuple[str, ...] = DEFAULT_SUPPORTED_PHOTO_EXTENSIONS
    folder_display_name: str | None = None
