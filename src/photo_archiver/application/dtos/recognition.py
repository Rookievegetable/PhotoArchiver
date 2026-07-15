"""DTOs for the face recognition pipeline (detection, recognition, matching).

Step 8 defines these as the in/out shapes for Application-layer orchestration
between the three recognition ports (:class:`FaceDetector`,
:class:`FaceRecognizer`, :class:`PersonMatcher`). They are deliberately pure
data holders — no business rules live here.
"""

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from photo_archiver.domain.value_objects import FaceBox, FaceEmbedding


@dataclass(frozen=True, slots=True)
class FaceDetectionItem:
    """One detected face plus its source image reference."""

    photo_id: UUID
    image: Path
    box: FaceBox


@dataclass(frozen=True, slots=True)
class FaceDetectionResult:
    """Outcome of running detection across a batch of photos."""

    detected_count: int = 0
    items: tuple[FaceDetectionItem, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        """Return whether detection completed without errors."""
        return not self.errors


@dataclass(frozen=True, slots=True)
class FaceRecognitionItem:
    """One extracted embedding plus its source photo and box."""

    photo_id: UUID
    box: FaceBox
    embedding: FaceEmbedding


@dataclass(frozen=True, slots=True)
class FaceRecognitionResult:
    """Outcome of running recognition across detected faces."""

    recognized_count: int = 0
    items: tuple[FaceRecognitionItem, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        """Return whether recognition completed without errors."""
        return not self.errors


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    """A single scored candidate for a face embedding."""

    person_id: UUID
    confidence: float


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Outcome of matching one face embedding against known persons."""

    photo_id: UUID
    box: FaceBox | None = None
    best: MatchCandidate | None = None
    candidates: tuple[MatchCandidate, ...] = field(default_factory=tuple)
