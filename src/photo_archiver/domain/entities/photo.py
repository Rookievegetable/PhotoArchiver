"""Photo entity."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.value_objects import PhotoMetadata, PhotoPath


@dataclass(slots=True)
class Photo:
    """Represent a photo discovered by the archive workflow."""

    path: PhotoPath
    id: UUID | None = None
    folder_id: UUID | None = None
    metadata: PhotoMetadata | None = None
    original_name: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        """Initialize generated fields and normalize optional text."""
        if not isinstance(self.path, PhotoPath):
            raise ValidationError("Photo path must be a PhotoPath")
        if self.id is None:
            self.id = uuid4()
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.original_name is not None:
            normalized_name = self.original_name.strip()
            self.original_name = normalized_name or None