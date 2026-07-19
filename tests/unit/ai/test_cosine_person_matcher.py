"""Unit tests for the cosine-similarity person matcher."""

from uuid import uuid4

import pytest

from photo_archiver.ai import CosinePersonMatcher
from photo_archiver.domain.value_objects import FaceEmbedding


def test_cosine_matcher_returns_none_for_empty_candidates() -> None:
    """An empty candidate mapping must produce no match."""
    matcher = CosinePersonMatcher(threshold=0.5)
    embedding = FaceEmbedding((0.1, 0.2, 0.3))
    assert matcher.match(embedding, {}) is None


def test_cosine_matcher_returns_none_for_zero_query_vector() -> None:
    """A zero query vector cannot be normalised, so no match."""
    matcher = CosinePersonMatcher(threshold=0.5)
    embedding = FaceEmbedding((0.0, 0.0, 0.0))
    candidate_id = uuid4()
    candidates = {candidate_id: FaceEmbedding((0.1, 0.2, 0.3))}
    assert matcher.match(embedding, candidates) is None


def test_cosine_matcher_returns_none_for_zero_candidate_vector() -> None:
    """Zero-vector candidates are skipped, leaving no valid match."""
    matcher = CosinePersonMatcher(threshold=0.5)
    embedding = FaceEmbedding((0.1, 0.2, 0.3))
    candidate_id = uuid4()
    candidates = {candidate_id: FaceEmbedding((0.0, 0.0, 0.0))}
    assert matcher.match(embedding, candidates) is None


def test_cosine_matcher_returns_best_above_threshold() -> None:
    """The matcher must return the highest-confidence candidate above threshold."""
    matcher = CosinePersonMatcher(threshold=0.5)
    embedding = FaceEmbedding((1.0, 0.0, 0.0))
    best_id = uuid4()
    worse_id = uuid4()
    candidates = {
        best_id: FaceEmbedding((0.9, 0.1, 0.0)),
        worse_id: FaceEmbedding((0.1, 0.9, 0.0)),
    }
    result = matcher.match(embedding, candidates)
    assert result is not None
    person_id, confidence = result
    assert person_id == best_id
    assert confidence > 0.5


def test_cosine_matcher_returns_none_below_threshold() -> None:
    """When all candidates fall below threshold, no match is returned."""
    matcher = CosinePersonMatcher(threshold=0.9)
    embedding = FaceEmbedding((1.0, 0.0, 0.0))
    candidate_id = uuid4()
    candidates = {candidate_id: FaceEmbedding((0.1, 0.9, 0.0))}
    assert matcher.match(embedding, candidates) is None


def test_cosine_matcher_confidence_clipped_to_unit_range() -> None:
    """Confidence must be clipped into [0.0, 1.0] even for opposite vectors.

    review Major fix: threshold now lives in cosine [-1,1] domain. threshold=-1.0
    accepts the opposite candidate (similarity=-1.0) so we can verify the
    returned confidence is clipped into [0,1] for reporting.
    """
    matcher = CosinePersonMatcher(threshold=-1.0)
    embedding = FaceEmbedding((1.0, 0.0))
    candidate_id = uuid4()
    candidates = {candidate_id: FaceEmbedding((-1.0, 0.0))}
    result = matcher.match(embedding, candidates)
    assert result is not None
    _, confidence = result
    assert 0.0 <= confidence <= 1.0


def test_cosine_matcher_rejects_invalid_threshold() -> None:
    """Threshold must be in [-1.0, 1.0] (review Major fix: cosine domain)."""
    with pytest.raises(ValueError):
        CosinePersonMatcher(threshold=-1.1)
    with pytest.raises(ValueError):
        CosinePersonMatcher(threshold=1.1)


def test_cosine_matcher_rejects_dimension_mismatch() -> None:
    """A query/candidate dimension mismatch must raise."""
    matcher = CosinePersonMatcher(threshold=0.5)
    embedding = FaceEmbedding((1.0, 0.0))
    candidate_id = uuid4()
    candidates = {candidate_id: FaceEmbedding((0.1, 0.2, 0.3))}
    with pytest.raises(ValueError):
        matcher.match(embedding, candidates)
