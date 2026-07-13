"""Person entity."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.value_objects import PersonIdentity


@dataclass(slots=True)
class Person:
    """Represent a person whose photos can be archived."""

    name: str
    id: UUID | None = None
    identity: PersonIdentity | None = None
    department: str | None = None
    note: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate person fields and initialize generated values."""
        normalized_name = self.name.strip()
        if not normalized_name:
            raise ValidationError("Person name must not be empty")
        self.name = normalized_name
        self.department = self._normalize_optional_text(self.department)
        self.note = self._normalize_optional_text(self.note)
        if self.id is None:
            self.id = uuid4()
        if self.created_at is None:
            self.created_at = datetime.now()

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        """Normalize optional free-text values."""
        if value is None:
            return None
        normalized_value = value.strip()
        return normalized_value or None