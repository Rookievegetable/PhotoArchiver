"""Person matcher port for matching face embeddings to known persons."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from photo_archiver.domain.value_objects import FaceEmbedding


@runtime_checkable
class PersonMatcher(Protocol):
    """Match a face embedding against candidate person embeddings.

    The matcher receives the query embedding together with a mapping of
    ``person_id`` → candidate embedding. It returns the best matching
    ``person_id`` and the confidence score, or ``None`` when no candidate
    clears the configured threshold. Implementations MUST NOT mutate the
    candidate mapping or make archival decisions — matching is pure scoring.
    """

    def match(
        self,
        embedding: FaceEmbedding,
        candidates: dict[UUID, FaceEmbedding],
    ) -> tuple[UUID, float] | None:
        """Return the best ``(person_id, confidence)`` pair, or ``None``.

        Args:
            embedding: The query face embedding to match.
            candidates: A mapping from person id to known face embedding.

        Returns:
            A ``(person_id, confidence)`` tuple for the best match above the
            configured threshold, otherwise ``None``. ``confidence`` is in
            ``[0.0, 1.0]``.
        """
        ...
