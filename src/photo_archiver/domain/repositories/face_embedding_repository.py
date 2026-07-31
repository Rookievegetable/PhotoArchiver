"""Face embedding repository interface.

Step 10 Major fix M-1: the MatchPersonsService originally built candidate
embeddings via ``getattr(person, "face_embedding", None)``, but the Person
entity has no such field — so candidates were always empty and every match
yielded Unknown. This repository persists per-person canonical embeddings so
the matching service can query them explicitly.

ISSUE-003 resolution: ``list_all`` now accepts optional ``limit``/``offset``
parameters so callers facing large person volumes can page through embeddings
rather than loading the entire table into memory at once. Defaults preserve
the original full-scan behavior so existing callers are unaffected.
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

    def list_all(
        self,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[UUID, FaceEmbedding]:
        """Return a ``person_id → embedding`` mapping for known persons.

        Args:
            limit: Maximum number of embeddings to return. ``None`` (default)
                returns every persisted row — the original full-scan behavior,
                kept for backward compatibility with callers that do not page.
                Pass a positive int to cap memory when person volume is large.
            offset: Number of embeddings to skip before collecting rows.
                Defaults to ``0``; combine with ``limit`` for page-style access.

        Returns:
            A dict covering the requested slice of persisted embeddings.
            Empty when no row falls in the ``[offset, offset+limit)`` range.

        Raises:
            ValueError: When ``limit`` is non-positive or ``offset`` is negative.
        """
