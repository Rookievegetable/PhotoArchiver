"""Unit tests for InsightFaceDetector.detect_with_embeddings and InsightFaceRecognizer.extract_from.

ISSUE-001 regression coverage: the optimized pipeline must run
``FaceAnalysis.get`` exactly once per photo so the recognizer no longer
re-detects. These tests stub the FaceAnalysis instance with a fake that
counts ``get`` calls, so they run without the buffalo_l model pack.
"""

from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from photo_archiver.ai.insightface_detector import InsightFaceDetector
from photo_archiver.ai.insightface_recognizer import InsightFaceRecognizer
from photo_archiver.domain.value_objects import FaceBox, FaceEmbedding


class _FakeFaceAnalysis:
    """Stub FaceAnalysis that returns preconfigured faces and counts ``get`` calls."""

    def __init__(self, faces: list[dict]) -> None:
        self._faces = faces
        self.get_call_count = 0

    def get(self, image_bytes: object, max_num: int = 0) -> list[dict]:  # noqa: ARG002
        self.get_call_count += 1
        return self._faces


def _make_face(
    bbox: tuple[int, int, int, int],
    det_score: float,
    embedding_values: Sequence[float],
) -> dict:
    """Build a fake InsightFace face dict with bbox, det_score, and embedding."""
    return {
        "bbox": list(bbox),
        "det_score": det_score,
        "embedding": np.array(embedding_values, dtype=np.float32),
    }


def test_detect_with_embeddings_returns_pairs_in_one_pass() -> None:
    """detect_with_embeddings must return FaceBoxEmbedding pairs from a single analysis.get call."""
    faces = [
        _make_face(bbox=(10, 20, 60, 80), det_score=0.9, embedding_values=(0.1, 0.2, 0.3)),
        _make_face(bbox=(100, 100, 150, 150), det_score=0.7, embedding_values=(0.4, 0.5, 0.6)),
    ]
    fake = _FakeFaceAnalysis(faces)
    detector = InsightFaceDetector(fake)  # type: ignore[arg-type]

    with patch(
        "photo_archiver.ai.insightface_detector.cv2.imread",
        return_value=np.zeros((100, 100, 3)),
    ):
        pairs = detector.detect_with_embeddings(Path("/fake.jpg"))

    assert fake.get_call_count == 1
    assert len(pairs) == 2
    assert all(isinstance(p.box, FaceBox) for p in pairs)
    assert all(isinstance(p.embedding, FaceEmbedding) for p in pairs)
    assert pairs[0].box.x1 == 10
    assert pairs[0].box.confidence == 0.9
    assert tuple(pytest.approx(v) for v in pairs[0].embedding.vector) == (0.1, 0.2, 0.3)
    assert tuple(pytest.approx(v) for v in pairs[1].embedding.vector) == (0.4, 0.5, 0.6)


def test_detect_with_embeddings_empty_for_no_faces() -> None:
    """An image with no detected faces must return an empty pair list."""
    fake = _FakeFaceAnalysis([])
    detector = InsightFaceDetector(fake)  # type: ignore[arg-type]

    with patch(
        "photo_archiver.ai.insightface_detector.cv2.imread",
        return_value=np.zeros((100, 100, 3)),
    ):
        pairs = detector.detect_with_embeddings(Path("/empty.jpg"))

    assert pairs == []


def test_detect_with_embeddings_returns_empty_for_unreadable_image() -> None:
    """An unreadable image (cv2.imread returns None) must yield empty, not raise."""
    fake = _FakeFaceAnalysis([_make_face(bbox=(0, 0, 10, 10), det_score=0.9, embedding_values=(0.1,))])
    detector = InsightFaceDetector(fake)  # type: ignore[arg-type]

    with patch("photo_archiver.ai.insightface_detector.cv2.imread", return_value=None):
        pairs = detector.detect_with_embeddings(Path("/corrupt.jpg"))

    assert pairs == []
    assert fake.get_call_count == 0  # model never invoked when imread fails


def test_extract_from_reuses_provided_faces_without_redetecting() -> None:
    """extract_from must NOT call analysis.get — it reuses the detector's faces."""
    faces = [_make_face(bbox=(5, 5, 50, 50), det_score=0.8, embedding_values=(0.9, 0.8))]
    fake = _FakeFaceAnalysis(faces)
    recognizer = InsightFaceRecognizer(fake)  # type: ignore[arg-type]

    box = FaceBox(x1=5, y1=5, x2=50, y2=50, confidence=0.8)
    embedding = recognizer.extract_from(box, faces)

    assert fake.get_call_count == 0  # key regression: no re-detection
    assert tuple(pytest.approx(v) for v in embedding.vector) == (0.9, 0.8)


def test_extract_from_raises_when_no_face_matches_box() -> None:
    """extract_from must raise ValueError when no face bbox matches the requested box."""
    faces = [_make_face(bbox=(0, 0, 10, 10), det_score=0.5, embedding_values=(0.1,))]
    recognizer = InsightFaceRecognizer(_FakeFaceAnalysis(faces))  # type: ignore[arg-type]

    box = FaceBox(x1=200, y1=200, x2=300, y2=300)
    with pytest.raises(ValueError, match="no face"):
        recognizer.extract_from(box, faces)


def test_extract_legacy_path_still_works() -> None:
    """The legacy extract(image, box) wrapper must still function for compatibility."""
    faces = [_make_face(bbox=(0, 0, 10, 10), det_score=0.5, embedding_values=(0.1, 0.2))]
    fake = _FakeFaceAnalysis(faces)
    recognizer = InsightFaceRecognizer(fake)  # type: ignore[arg-type]

    with patch(
        "photo_archiver.ai.insightface_recognizer.cv2.imread",
        return_value=np.zeros((100, 100, 3)),
    ):
        box = FaceBox(x1=0, y1=0, x2=10, y2=10)
        embedding = recognizer.extract(Path("/fake.jpg"), box)

    assert tuple(pytest.approx(v) for v in embedding.vector) == (0.1, 0.2)
    assert fake.get_call_count == 1  # legacy path still detects once
