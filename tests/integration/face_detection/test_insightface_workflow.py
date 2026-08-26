"""Integration tests for the real InsightFace detector and recognizer.

These tests require the ``buffalo_l`` model pack to be present under
``resources/models/`` (fetched via ``scripts/download_models.py``). When the
pack is missing, the tests skip themselves rather than fail, so CI can run
the full suite without a model pack and only exercise detection when the
pack is pre-downloaded.

Run locally::

    python scripts/download_models.py
    pytest tests/integration/face_detection/ -v
"""

from pathlib import Path

import pytest

from photo_archiver.ai import (
    CosinePersonMatcher,
    InsightFaceDetector,
    InsightFaceRecognizer,
)
from photo_archiver.domain.value_objects import FaceBox
from photo_archiver.infrastructure.ai import InsightFaceLoader, ModelPackMissing

_ROOT = Path(__file__).resolve().parents[3]
_MODEL_ROOT = _ROOT / "resources" / "models"
_SAMPLE_IMAGE = _ROOT / "tests" / "integration" / "resources" / "sample_face.jpg"


def _model_available() -> bool:
    """Return whether the buffalo_l model pack is present."""
    return InsightFaceLoader(_MODEL_ROOT).is_available()


def _sample_available() -> bool:
    """Return whether the sample face image is present."""
    return _SAMPLE_IMAGE.exists()


pytestmark = pytest.mark.skipif(
    not (_model_available() and _sample_available()),
    reason=(
        "InsightFace model pack or sample image missing — run "
        "`python scripts/download_models.py` and add a sample face JPG"
    ),
)


@pytest.fixture(scope="module")
def detector() -> InsightFaceDetector:
    """Build a detector bound to the local model pack."""
    analysis = InsightFaceLoader(_MODEL_ROOT).load()
    return InsightFaceDetector(analysis)


@pytest.fixture(scope="module")
def recognizer(detector: InsightFaceDetector) -> InsightFaceRecognizer:
    """Build a recognizer reusing the detector's model analysis instance."""
    return InsightFaceRecognizer(detector.analysis)


def test_detector_finds_face_in_sample(detector: InsightFaceDetector) -> None:
    """The real detector must return at least one FaceBox for the sample."""
    boxes = detector.detect(_SAMPLE_IMAGE)
    assert len(boxes) >= 1
    for box in boxes:
        assert isinstance(box, FaceBox)
        assert box.confidence is not None
        assert box.confidence > 0.0


def test_recognizer_extracts_embedding_for_box(
    detector: InsightFaceDetector,
    recognizer: InsightFaceRecognizer,
) -> None:
    """The recognizer must return a non-empty embedding for a detected face."""
    boxes = detector.detect(_SAMPLE_IMAGE)
    embedding = recognizer.extract(_SAMPLE_IMAGE, boxes[0])
    assert embedding.dimension > 0
    assert any(v != 0.0 for v in embedding.vector)


def test_recognizer_dimension_is_512(recognizer: InsightFaceRecognizer) -> None:
    """The buffalo_l pack must produce 512-dimensional embeddings."""
    assert recognizer.embedding_dimension() == 512


def test_detector_returns_empty_for_unreadable_image(detector: InsightFaceDetector) -> None:
    """An unreadable image must yield an empty box list, not an exception."""
    boxes = detector.detect(Path("/nonexistent/photo.jpg"))
    assert boxes == []


def test_detector_raises_model_pack_missing_for_empty_dir(tmp_path: Path) -> None:
    """InsightFaceLoader.load must raise ModelPackMissing when the pack is missing."""
    with pytest.raises(ModelPackMissing):
        InsightFaceLoader(tmp_path / "empty_models").load()


def test_matcher_round_trips_real_embedding(
    detector: InsightFaceDetector,
    recognizer: InsightFaceRecognizer,
) -> None:
    """A real embedding must be matchable against itself by cosine similarity."""
    boxes = detector.detect(_SAMPLE_IMAGE)
    embedding = recognizer.extract(_SAMPLE_IMAGE, boxes[0])
    from uuid import uuid4

    person_id = uuid4()
    matcher = CosinePersonMatcher(threshold=0.5)
    result = matcher.match(embedding, {person_id: embedding})
    assert result is not None
    matched_id, confidence = result
    assert matched_id == person_id
    assert confidence > 0.9
