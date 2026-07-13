"""Local filesystem implementation of the photo file scanner port."""

from pathlib import Path

from photo_archiver.application.dtos import PhotoScanItem
from photo_archiver.application.ports import PhotoFileScanner


class LocalPhotoFileScanner(PhotoFileScanner):
    """Discover photo files under a local directory."""

    def scan(
        self,
        folder_path: Path,
        *,
        recursive: bool,
        supported_extensions: tuple[str, ...],
    ) -> list[PhotoScanItem]:
        """Return photo candidates matching the supported extensions."""
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Photo folder does not exist: {folder}")
        if not folder.is_dir():
            raise NotADirectoryError(f"Photo folder is not a directory: {folder}")

        normalized_extensions = self._normalize_extensions(supported_extensions)
        pattern = "**/*" if recursive else "*"
        photos = [
            PhotoScanItem(path=path, original_name=path.name)
            for path in folder.glob(pattern)
            if path.is_file() and path.suffix.lower() in normalized_extensions
        ]
        return sorted(photos, key=lambda item: str(item.path).lower())

    @staticmethod
    def _normalize_extensions(extensions: tuple[str, ...]) -> set[str]:
        """Normalize extensions to lowercase values prefixed with a dot."""
        normalized = set()
        for extension in extensions:
            value = extension.strip().lower()
            if not value:
                continue
            normalized.add(value if value.startswith(".") else f".{value}")
        return normalized