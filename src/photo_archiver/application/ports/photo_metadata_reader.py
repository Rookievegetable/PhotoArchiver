"""Port for reading photo metadata from image files."""

from pathlib import Path
from typing import Protocol

from photo_archiver.domain import PhotoMetadata


class PhotoMetadataReader(Protocol):
    """Read image metadata needed by the archive domain."""

    def read(self, path: Path) -> PhotoMetadata:
        """Return metadata for the given image path."""