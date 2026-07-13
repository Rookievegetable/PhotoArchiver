"""Person identity value object."""

from dataclasses import dataclass

from photo_archiver.domain.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class PersonIdentity:
    """Represent an optional external person identifier."""

    value: str

    def __post_init__(self) -> None:
        """Validate and normalize the identity value."""
        normalized_value = self.value.strip()
        if not normalized_value:
            raise ValidationError("Person identity must not be empty")
        object.__setattr__(self, "value", normalized_value)

    def __str__(self) -> str:
        """Return the normalized identity value."""
        return self.value