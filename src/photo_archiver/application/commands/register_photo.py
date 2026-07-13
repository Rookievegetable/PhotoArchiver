"""Command for registering a discovered photo."""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RegisterPhotoCommand:
    """Request persisting a photo discovered during scanning."""

    path: Path
    folder_id: UUID | None = None
    original_name: str | None = None