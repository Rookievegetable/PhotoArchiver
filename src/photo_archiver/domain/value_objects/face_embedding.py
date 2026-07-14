"""Face embedding value object."""

from collections.abc import Sequence
from dataclasses import dataclass

from photo_archiver.domain.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class FaceEmbedding:
    """Represent a face embedding as an immutable sequence of floats.

    The embedding holds a ``tuple[float, ...]`` rather than a numpy array so
    the Domain layer stays free of third-party framework dependencies. The
    embedding dimension is fixed at construction and exposed via ``dimension``
    for downstream validation.
    """

    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        """Validate the embedding vector shape."""
        if not isinstance(self.vector, tuple):
            raise ValidationError("FaceEmbedding vector must be a tuple")
        if len(self.vector) == 0:
            raise ValidationError("FaceEmbedding vector must not be empty")

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        return len(self.vector)

    @classmethod
    def from_sequence(cls, values: Sequence[float]) -> "FaceEmbedding":
        """Build a FaceEmbedding from any sequence of floats."""
        return cls(tuple(values))
