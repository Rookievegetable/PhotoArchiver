"""Face bounding box value object."""

from dataclasses import dataclass

from photo_archiver.domain.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class FaceBox:
    """Represent a detected face's bounding box in pixel coordinates.

    Coordinates use the top-left origin convention: (x1, y1) is the top-left
    corner and (x2, y2) is the bottom-right corner. The box is inclusive on
    both ends, so ``x2`` must be strictly greater than ``x1`` (same for y).
    """

    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float | None = None

    def __post_init__(self) -> None:
        """Validate bounding box geometry and confidence range."""
        self._validate_non_negative("x1", self.x1)
        self._validate_non_negative("y1", self.y1)
        self._validate_non_negative("x2", self.x2)
        self._validate_non_negative("y2", self.y2)
        if self.x2 <= self.x1:
            raise ValidationError("FaceBox x2 must be greater than x1")
        if self.y2 <= self.y1:
            raise ValidationError("FaceBox y2 must be greater than y1")
        if self.confidence is not None:
            if not 0.0 <= self.confidence <= 1.0:
                raise ValidationError("FaceBox confidence must be in [0.0, 1.0]")

    @property
    def width(self) -> int:
        """Return the box width in pixels."""
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        """Return the box height in pixels."""
        return self.y2 - self.y1

    @property
    def area(self) -> int:
        """Return the box area in square pixels."""
        return self.width * self.height

    @staticmethod
    def _validate_non_negative(name: str, value: int) -> None:
        """Validate that an integer coordinate is non-negative."""
        if value < 0:
            raise ValidationError(f"FaceBox {name} must be non-negative")
