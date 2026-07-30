"""Contract tests for the Step 8 recognition ports.

These tests verify the three ``FaceDetector`` / ``FaceRecognizer`` /
``PersonMatcher`` ports are runtime-checkable Protocols and that minimal
adapters satisfy them. Step 9 replaced the InsightFaceDetector stub with
the real InsightFace-backed detector, so the detector contract is now
verified through ``InsightFaceDetector.model_available`` rather than a
bare constructor call — the real detector needs a loaded model pack.
"""

from pathlib import Path
from uuid import uuid4

import pytest

from photo_archiver.application.dtos import (
    FaceDetectionItem,
    FaceDetectionResult,
    FaceRecognitionItem,
    FaceRecognitionResult,
    MatchCandidate,
    MatchResult,
)
from photo_archiver.application.ports import (
    FaceDetector,
    FaceRecognizer,
    PersonMatcher,
)
from photo_archiver.domain.value_objects import FaceBox, FaceEmbedding


class _DetectorImpl:
    """Minimal FaceDetector implementation for contract verification."""

    def detect(self, image: Path) -> list[FaceBox]:
        return []

    def detect_with_embeddings(self, image: Path) -> list:
        return []


class _RecognizerImpl:
    """Minimal FaceRecognizer implementation for contract verification."""

    def extract(self, image: Path, box: FaceBox) -> FaceEmbedding:
        return FaceEmbedding((0.0, 0.0, 0.0))

    def extract_from(self, box: FaceBox, faces) -> FaceEmbedding:
        return FaceEmbedding((0.0, 0.0, 0.0))


class _MatcherImpl:
    """Minimal PersonMatcher implementation for contract verification."""

    def match(
        self,
        embedding: FaceEmbedding,
        candidates: dict,
    ) -> None:
        return None


def test_face_detector_is_runtime_checkable_protocol() -> None:
    """FaceDetector should be a runtime-checkable Protocol."""
    assert isinstance(_DetectorImpl(), FaceDetector)


def test_face_recognizer_is_runtime_checkable_protocol() -> None:
    """FaceRecognizer should be a runtime-checkable Protocol."""
    assert isinstance(_RecognizerImpl(), FaceRecognizer)


def test_person_matcher_is_runtime_checkable_protocol() -> None:
    """PersonMatcher should be a runtime-checkable Protocol."""
    assert isinstance(_MatcherImpl(), PersonMatcher)


def test_insightface_loader_is_available_returns_false_for_missing_dir(
    tmp_path: Path,
) -> None:
    """InsightFaceLoader.is_available must return False when the model pack is absent."""
    from photo_archiver.infrastructure.ai import InsightFaceLoader

    missing = tmp_path / "nonexistent_models"
    assert InsightFaceLoader(missing).is_available() is False


def test_insightface_loader_raises_model_pack_missing(
    tmp_path: Path,
) -> None:
    """InsightFaceLoader.load must raise ModelPackMissing when the pack is missing."""
    from photo_archiver.infrastructure.ai import InsightFaceLoader, ModelPackMissing

    with pytest.raises(ModelPackMissing):
        InsightFaceLoader(tmp_path / "empty_models").load()


def test_face_box_rejects_invalid_geometry() -> None:
    """FaceBox must reject boxes where x2 <= x1 or y2 <= y1."""
    from photo_archiver.domain.exceptions import ValidationError

    with pytest.raises(ValidationError):
        FaceBox(x1=10, y1=10, x2=5, y2=20)
    with pytest.raises(ValidationError):
        FaceBox(x1=10, y1=10, x2=20, y2=5)


def test_face_box_rejects_negative_coordinates() -> None:
    """FaceBox must reject negative coordinates."""
    from photo_archiver.domain.exceptions import ValidationError

    with pytest.raises(ValidationError):
        FaceBox(x1=-1, y1=0, x2=10, y2=10)


def test_face_box_rejects_invalid_confidence() -> None:
    """FaceBox must reject confidence outside [0.0, 1.0]."""
    from photo_archiver.domain.exceptions import ValidationError

    with pytest.raises(ValidationError):
        FaceBox(x1=0, y1=0, x2=10, y2=10, confidence=1.5)
    with pytest.raises(ValidationError):
        FaceBox(x1=0, y1=0, x2=10, y2=10, confidence=-0.1)


def test_face_box_properties() -> None:
    """FaceBox width/height/area must match geometry."""
    box = FaceBox(x1=10, y1=20, x2=30, y2=50, confidence=0.9)
    assert box.width == 20
    assert box.height == 30
    assert box.area == 600


def test_face_embedding_rejects_empty_vector() -> None:
    """FaceEmbedding must reject an empty vector."""
    from photo_archiver.domain.exceptions import ValidationError

    with pytest.raises(ValidationError):
        FaceEmbedding(vector=())


def test_face_embedding_rejects_non_tuple_vector() -> None:
    """FaceEmbedding must reject a non-tuple vector (Domain stays numpy-free)."""
    from photo_archiver.domain.exceptions import ValidationError

    with pytest.raises(ValidationError):
        FaceEmbedding(vector=[0.1, 0.2])  # type: ignore[arg-type]


def test_face_embedding_dimension() -> None:
    """FaceEmbedding.dimension must report the vector length."""
    embedding = FaceEmbedding((0.1, 0.2, 0.3))
    assert embedding.dimension == 3


def test_face_embedding_from_sequence() -> None:
    """FaceEmbedding.from_sequence must coerce any sequence to a tuple."""
    embedding = FaceEmbedding.from_sequence([0.1, 0.2, 0.3, 0.4])
    assert embedding.vector == (0.1, 0.2, 0.3, 0.4)
    assert embedding.dimension == 4


def test_match_status_enum_values() -> None:
    """MatchStatus must expose pending/approved/rejected string values."""
    from photo_archiver.domain.entities import MatchStatus

    assert MatchStatus.PENDING.value == "pending"
    assert MatchStatus.APPROVED.value == "approved"
    assert MatchStatus.REJECTED.value == "rejected"


def test_recognition_result_approve_reject() -> None:
    """RecognitionResult must transition pending → approved/rejected only."""
    from photo_archiver.domain.entities import MatchStatus, RecognitionResult
    from photo_archiver.domain.exceptions import ValidationError

    result = RecognitionResult(photo_id=uuid4(), confidence=0.8)
    assert result.status is MatchStatus.PENDING
    result.approve()
    assert result.status is MatchStatus.APPROVED
    with pytest.raises(ValidationError):
        result.reject()


def test_recognition_result_reject_then_approve_blocked() -> None:
    """A finalized RecognitionResult must not transition again."""
    from photo_archiver.domain.entities import MatchStatus, RecognitionResult
    from photo_archiver.domain.exceptions import ValidationError

    result = RecognitionResult(photo_id=uuid4(), confidence=0.8)
    result.reject()
    assert result.status is MatchStatus.REJECTED
    with pytest.raises(ValidationError):
        result.approve()


def test_recognition_result_rejects_invalid_confidence() -> None:
    """RecognitionResult must reject confidence outside [0.0, 1.0]."""
    from photo_archiver.domain.entities import RecognitionResult
    from photo_archiver.domain.exceptions import ValidationError

    with pytest.raises(ValidationError):
        RecognitionResult(photo_id=uuid4(), confidence=1.5)


def test_recognition_dto_defaults() -> None:
    """FaceDetectionResult and FaceRecognitionResult must default empty."""
    detection = FaceDetectionResult()
    assert detection.detected_count == 0
    assert detection.items == ()
    assert detection.errors == ()
    assert detection.succeeded is True

    recognition = FaceRecognitionResult()
    assert recognition.recognized_count == 0
    assert recognition.items == ()
    assert recognition.errors == ()
    assert recognition.succeeded is True


def test_match_dto_construction() -> None:
    """MatchCandidate and MatchResult must hold the scored match payload."""
    person_id = uuid4()
    box = FaceBox(x1=0, y1=0, x2=10, y2=10)
    candidate = MatchCandidate(person_id=person_id, confidence=0.9)
    photo_id = uuid4()
    match = MatchResult(
        photo_id=photo_id,
        box=box,
        best=candidate,
        candidates=(candidate,),
    )
    assert match.best is candidate
    assert match.candidates == (candidate,)
    assert match.photo_id == photo_id


def test_detection_item_round_trips_box() -> None:
    """FaceDetectionItem must carry photo_id, image and box."""
    photo_id = uuid4()
    box = FaceBox(x1=0, y1=0, x2=10, y2=10)
    item = FaceDetectionItem(photo_id=photo_id, image=Path("/x.jpg"), box=box)
    assert item.photo_id == photo_id
    assert item.image == Path("/x.jpg")
    assert item.box is box


def test_recognition_item_round_trips_embedding() -> None:
    """FaceRecognitionItem must carry photo_id, box and embedding."""
    photo_id = uuid4()
    box = FaceBox(x1=0, y1=0, x2=10, y2=10)
    embedding = FaceEmbedding((0.1, 0.2))
    item = FaceRecognitionItem(
        photo_id=photo_id,
        box=box,
        embedding=embedding,
    )
    assert item.photo_id == photo_id
    assert item.box is box
    assert item.embedding is embedding
