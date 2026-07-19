"""Cosine-similarity person matcher backing the ``PersonMatcher`` port.

This module implements :class:`PersonMatcher` with plain Python math so the
``ai/`` layer does not pull numpy into the matching hot path. The matcher
normalises the query and candidate embeddings then returns the best
``person_id`` whose cosine similarity clears the configured threshold.
"""

import math
from uuid import UUID

from loguru import logger

from photo_archiver.domain.value_objects import FaceEmbedding

# Matcher-only default; production wiring injects AppSettings.match_threshold
# (default 0.40) per裁决 #3. This constant exists so CosinePersonMatcher can be
# constructed standalone in unit tests without pulling settings infrastructure.
_DEFAULT_THRESHOLD = 0.4


class CosinePersonMatcher:
    """Match a face embedding against candidate persons by cosine similarity.

    The matcher holds a configurable ``threshold`` so Step 10 user-review
    wiring can read it from :class:`AppSettings` rather than hardcoding it
    here. ``confidence`` is returned in ``[0.0, 1.0]`` by clipping cosine
    similarity (which lives in ``[-1.0, 1.0]``) into ``[0.0, 1.0]``.
    """

    def __init__(self, threshold: float = _DEFAULT_THRESHOLD) -> None:
        """Store the configured similarity threshold.

        Args:
            threshold: Minimum cosine similarity for a candidate to be
                returned, in ``[0.0, 1.0]``.
        """
        if not -1.0 <= threshold <= 1.0:
            raise ValueError("CosinePersonMatcher threshold must be in [-1.0, 1.0]")
        self._threshold = threshold
        logger.debug("CosinePersonMatcher ready (threshold={})", threshold)

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
            configured threshold, otherwise ``None``. Empty ``candidates``
            always returns ``None``.
        """
        if not candidates:
            return None
        query_norm = _norm(embedding.vector)
        if query_norm == 0.0:
            return None
        best_id: UUID | None = None
        best_confidence = -1.0
        for person_id, candidate in candidates.items():
            candidate_norm = _norm(candidate.vector)
            if candidate_norm == 0.0:
                continue
            similarity = _dot(embedding.vector, candidate.vector) / (query_norm * candidate_norm)
            # review Major fix: threshold lives in cosine [-1,1] domain, NOT in
            # the [0,1] confidence reporting domain. Previous (sim+1)/2 mapping
            # made threshold=0.40 accept cosine >= -0.2 (almost everyone matches).
            if similarity >= self._threshold and similarity >= best_confidence:
                best_id = person_id
                best_confidence = similarity
        if best_id is None:
            return None
        # Report confidence in [0,1] for UI/logs; threshold comparison happened
        # in cosine [-1,1] domain above (review Major fix).
        reported_confidence = max(0.0, min(1.0, (best_confidence + 1.0) / 2.0))
        return best_id, reported_confidence


def _dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Return the dot product of two equal-length float tuples."""
    if len(a) != len(b):
        raise ValueError("embedding dimension mismatch")
    return sum(x * y for x, y in zip(a, b))


def _norm(a: tuple[float, ...]) -> float:
    """Return the Euclidean norm of a float tuple."""
    return math.sqrt(sum(x * x for x in a))
