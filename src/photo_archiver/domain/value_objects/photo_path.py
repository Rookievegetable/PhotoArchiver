"""Photo path value object."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photo_archiver.domain.exceptions import ValidationError


class PhotoPathBase(StrEnum):
    """Supported bases used by infrastructure to resolve photo paths."""

    ABSOLUTE = "absolute"
    PHOTO_ROOT = "photo_root"
    PROJECT_ROOT = "project_root"


@dataclass(frozen=True, slots=True)
class PhotoPath:
    """Represent a photo path without performing filesystem operations."""

    raw_path: Path
    base: PhotoPathBase = PhotoPathBase.PHOTO_ROOT

    def __post_init__(self) -> None:
        """Validate path shape and keep resolution outside the domain layer."""
        if isinstance(self.raw_path, str) and not self.raw_path.strip():
            raise ValidationError("Photo path must not be empty")
        path = Path(self.raw_path)
        if not str(path).strip() or str(path) == ".":
            raise ValidationError("Photo path must not be empty")
        if path.is_absolute() and self.base is not PhotoPathBase.ABSOLUTE:
            raise ValidationError("Absolute photo paths must use PhotoPathBase.ABSOLUTE")
        if not path.is_absolute() and self.base is PhotoPathBase.ABSOLUTE:
            raise ValidationError("Relative photo paths must not use PhotoPathBase.ABSOLUTE")
        object.__setattr__(self, "raw_path", path)

    @property
    def is_absolute(self) -> bool:
        """Return whether the raw path is absolute."""
        return self.raw_path.is_absolute()

    @property
    def is_relative(self) -> bool:
        """Return whether the raw path requires base-directory resolution."""
        return not self.is_absolute