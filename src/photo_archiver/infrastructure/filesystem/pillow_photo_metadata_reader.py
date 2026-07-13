"""Pillow-based implementation of the photo metadata reader port."""

from datetime import datetime
from pathlib import Path

from photo_archiver.application.ports import PhotoMetadataReader
from photo_archiver.domain import PhotoMetadata


class PillowPhotoMetadataReader(PhotoMetadataReader):
    """Read basic image metadata using Pillow."""

    def read(self, path: Path) -> PhotoMetadata:
        """Return image dimensions and filesystem metadata for a photo."""
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:
            raise RuntimeError("Pillow is required to read photo metadata") from exc

        image_path = Path(path)
        if not image_path.exists():
            raise FileNotFoundError(f"Photo file does not exist: {image_path}")
        if not image_path.is_file():
            raise IsADirectoryError(f"Photo path is not a file: {image_path}")

        try:
            with Image.open(image_path) as image:
                width, height = image.size
        except UnidentifiedImageError as exc:
            raise ValueError(f"Unsupported or invalid image file: {image_path}") from exc
        except OSError as exc:
            raise ValueError(f"Failed to read image metadata: {image_path}") from exc

        stat = image_path.stat()
        return PhotoMetadata(
            width=width,
            height=height,
            file_size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime),
        )