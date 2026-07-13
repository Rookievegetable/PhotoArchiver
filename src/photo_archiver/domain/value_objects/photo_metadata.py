"""Photo metadata value object."""

from dataclasses import dataclass
from datetime import datetime

from photo_archiver.domain.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class PhotoMetadata:
    """Represent metadata extracted from an image file."""

    width: int | None = None
    height: int | None = None
    file_size_bytes: int | None = None
    modified_at: datetime | None = None
    content_hash: str | None = None

    def __post_init__(self) -> None:
        """Validate metadata values without touching the filesystem."""
        self._validate_positive_optional_int("width", self.width)
        self._validate_positive_optional_int("height", self.height)
        self._validate_positive_optional_int("file_size_bytes", self.file_size_bytes)
        if self.content_hash is not None:
            normalized_hash = self.content_hash.strip()
            object.__setattr__(self, "content_hash", normalized_hash or None)

    @staticmethod
    def _validate_positive_optional_int(name: str, value: int | None) -> None:
        """Validate that an optional integer is positive when provided."""
        if value is not None and value <= 0:
            raise ValidationError(f"Photo metadata {name} must be positive")