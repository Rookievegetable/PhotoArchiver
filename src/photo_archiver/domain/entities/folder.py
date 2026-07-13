"""Folder entity."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.value_objects import PhotoPath


@dataclass(slots=True)
class Folder:
    """Represent a photo folder selected for scanning."""

    path: PhotoPath
    id: UUID | None = None
    display_name: str | None = None
    total_photos: int = 0
    scanned_photos: int = 0
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate folder counters and initialize generated fields."""
        if not isinstance(self.path, PhotoPath):
            raise ValidationError("Folder path must be a PhotoPath")
        if self.id is None:
            self.id = uuid4()
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.total_photos < 0:
            raise ValidationError("Folder total_photos must not be negative")
        if self.scanned_photos < 0:
            raise ValidationError("Folder scanned_photos must not be negative")
        if self.scanned_photos > self.total_photos:
            raise ValidationError("Folder scanned_photos must not exceed total_photos")
        if self.display_name is not None:
            normalized_name = self.display_name.strip()
            self.display_name = normalized_name or None