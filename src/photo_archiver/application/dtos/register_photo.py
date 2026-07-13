"""DTOs for photo registration workflows."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RegisterPhotoResult:
    """Outcome of registering a single photo."""

    photo_id: UUID
    created: bool