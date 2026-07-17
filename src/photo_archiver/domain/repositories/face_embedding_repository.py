"""Face embedding repository interface.

Step 10 Major fix M-1: the MatchPersonsService originally built candidate
embeddings via ``getattr(person, "face_embedding", None)``, but the Person
entity has no such field — so candidates were always empty and every match
yielded Unknown. This repository persists per-person canonical embeddings so
the matching service can query them explicitly.
"""

from typing import Protocol
from uuid import UUID

from photo_archiver.domain.value_objects import FaceEmbedding


class FaceEmbeddingRepository(Protocol):
    """Define persistence operations for per-person face embeddings.

    Not decorated ``@runtime_checkable`` (unlike FaceDetector/Recognizer/
    Matcher) because repositories are never ``isinstance``-checked at runtime —
    callers wire concrete adapters by construction, so the check overhead is
    unwanted. Mirrors RecognitionRepository's convention.
    """

    def save(self, person_id: UUID, embedding: FaceEmbedding) -> None:
        """Persist or replace the canonical embedding for a person."""

    def find_by_person(self, person_id: UUID) -> FaceEmbedding | None:
        """Return the canonical embedding for a person, or ``None``."""

    def list_all(self) -> dict[UUID, FaceEmbedding]:
        """Return a ``person_id → embedding`` mapping for all known persons."""
