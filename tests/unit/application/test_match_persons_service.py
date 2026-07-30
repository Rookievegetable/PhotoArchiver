"""Unit tests for the MatchPersonsService Application-layer orchestration."""

from pathlib import Path
from uuid import uuid4

import pytest

from photo_archiver.application.commands import MatchPersonsCommand
from photo_archiver.application.services import MatchPersonsService
from photo_archiver.domain import (
    FaceEmbedding,
    FaceEmbeddingRepository,
    RecognitionRepository,
)
from photo_archiver.domain.value_objects import FaceBox, FaceBoxEmbedding


class _StubDetector:
    """FaceDetector stub returning preconfigured box/embedding pairs."""

    def __init__(self, pairs_per_image: dict[Path, list]) -> None:
        self._pairs = pairs_per_image

    def detect(self, image: Path) -> list:  # noqa: ARG002
        """Legacy box-only API retained for Protocol compatibility."""
        return [pair.box for pair in self._pairs.get(image, [])]

    def detect_with_embeddings(self, image: Path) -> list:
        return self._pairs.get(image, [])


class _StubRecognizer:
    """FaceRecognizer stub returning a fixed embedding."""

    def __init__(self, embedding: FaceEmbedding) -> None:
        self._embedding = embedding

    def extract(self, image: Path, box) -> FaceEmbedding:  # noqa: ARG002
        return self._embedding

    def extract_from(self, box, faces) -> FaceEmbedding:  # noqa: ARG002
        return self._embedding


class _StubMatcher:
    """PersonMatcher stub returning a preconfigured result."""

    def __init__(self, result: tuple | None) -> None:
        self._result = result
        self.calls: list = []

    def match(self, embedding: FaceEmbedding, candidates: dict) -> tuple | None:  # noqa: ARG002
        self.calls.append((embedding, candidates))
        return self._result


class _StubFaceEmbeddingRepository(FaceEmbeddingRepository):
    """Minimal FaceEmbeddingRepository for service tests."""

    def __init__(self, candidates: dict) -> None:
        self._candidates = candidates

    def save(self, person_id, embedding: FaceEmbedding) -> None:
        self._candidates[person_id] = embedding

    def find_by_person(self, person_id) -> FaceEmbedding | None:
        return self._candidates.get(person_id)

    def list_all(self) -> dict:
        return self._candidates


class _StubRecognitionRepository(RecognitionRepository):
    def __init__(self) -> None:
        self.added: list = []

    def add(self, result) -> None:
        self.added.append(result)

    def find_by_id(self, result_id):
        return None

    def list_by_photo(self, photo_id) -> list:
        return []

    def list_pending(self) -> list:
        return []

    def update_status(self, result_id, status) -> None:
        raise NotImplementedError


def _build_service(
    detector_pairs: dict[Path, list],
    embedding: FaceEmbedding,
    matcher_result: tuple | None,
    candidates: dict | None = None,
) -> tuple[MatchPersonsService, _StubMatcher, _StubRecognitionRepository]:
    """Wire a MatchPersonsService with stubbed ports."""
    detector = _StubDetector(detector_pairs)
    recognizer = _StubRecognizer(embedding)
    matcher = _StubMatcher(matcher_result)
    embedding_repo = _StubFaceEmbeddingRepository(candidates or {})
    recognition_repo = _StubRecognitionRepository()
    service = MatchPersonsService(
        detector=detector,
        recognizer=recognizer,
        matcher=matcher,
        face_embedding_repository=embedding_repo,
        recognition_repository=recognition_repo,
    )
    return service, matcher, recognition_repo


def test_match_service_rejects_length_mismatch() -> None:
    """photo_ids and images tuples must have equal length."""
    service, _, _ = _build_service({}, FaceEmbedding((0.1,)), None)
    command = MatchPersonsCommand(
        photo_ids=(uuid4(),),
        images=(Path("/a.jpg"), Path("/b.jpg")),
    )
    with pytest.raises(ValueError):
        service.execute(command)


def test_match_service_no_face_yields_unknown(tmp_path: Path) -> None:
    """A photo with no detected face must yield a MatchResult with best=None."""
    image = tmp_path / "empty.jpg"
    image.write_bytes(b"")
    service, _, recognition_repo = _build_service(
        {image: []}, FaceEmbedding((0.1,)), None
    )
    photo_id = uuid4()
    command = MatchPersonsCommand(photo_ids=(photo_id,), images=(image,))
    results = service.execute(command)
    assert len(results) == 1
    assert results[0].best is None
    assert results[0].box is None
    assert recognition_repo.added == []


def test_match_service_match_success_persists_result(tmp_path: Path) -> None:
    """A successful match must persist a RecognitionResult with person_id."""
    image = tmp_path / "face.jpg"
    image.write_bytes(b"")
    box = FaceBox(x1=0, y1=0, x2=10, y2=10, confidence=0.9)
    embedding = FaceEmbedding((0.5, 0.5))
    person_id = uuid4()
    service, _, recognition_repo = _build_service(
        {image: [FaceBoxEmbedding(box=box, embedding=embedding)]},
        embedding,
        (person_id, 0.85),
    )
    photo_id = uuid4()
    command = MatchPersonsCommand(photo_ids=(photo_id,), images=(image,))
    results = service.execute(command)
    assert len(results) == 1
    assert results[0].box == box
    assert len(recognition_repo.added) == 1
    persisted = recognition_repo.added[0]
    assert persisted.photo_id == photo_id
    assert persisted.person_id == person_id
    assert persisted.confidence == 0.85
    from photo_archiver.domain import MatchStatus

    assert persisted.status is MatchStatus.PENDING


def test_match_service_unknown_match_persists_without_person(tmp_path: Path) -> None:
    """A below-threshold match must persist a result with person_id=None."""
    image = tmp_path / "face.jpg"
    image.write_bytes(b"")
    box = FaceBox(x1=0, y1=0, x2=10, y2=10)
    embedding = FaceEmbedding((0.1,))
    service, _, recognition_repo = _build_service(
        {image: [FaceBoxEmbedding(box=box, embedding=embedding)]}, embedding, None
    )
    photo_id = uuid4()
    command = MatchPersonsCommand(photo_ids=(photo_id,), images=(image,))
    results = service.execute(command)
    assert results[0].box == box
    assert len(recognition_repo.added) == 1
    persisted = recognition_repo.added[0]
    assert persisted.person_id is None
    assert persisted.confidence == 0.0


def test_match_service_uses_top1_first_face_only(tmp_path: Path) -> None:
    """Per裁决 #5, only the first detected face is matched (Top-1)."""
    image = tmp_path / "two_faces.jpg"
    image.write_bytes(b"")
    box1 = FaceBox(x1=0, y1=0, x2=10, y2=10)
    box2 = FaceBox(x1=20, y1=20, x2=30, y2=30)
    embedding = FaceEmbedding((0.5,))
    service, _, recognition_repo = _build_service(
        {
            image: [
                FaceBoxEmbedding(box=box1, embedding=embedding),
                FaceBoxEmbedding(box=box2, embedding=embedding),
            ]
        },
        embedding,
        (uuid4(), 0.7),
    )
    command = MatchPersonsCommand(
        photo_ids=(uuid4(),), images=(image,)
    )
    service.execute(command)
    assert len(recognition_repo.added) == 1
    assert recognition_repo.added[0].confidence == 0.7


def test_match_service_processes_batch_in_order(tmp_path: Path) -> None:
    """A multi-photo command must yield results in command order."""
    box = FaceBox(x1=0, y1=0, x2=10, y2=10)
    embedding = FaceEmbedding((0.3,))
    image1 = tmp_path / "a.jpg"
    image1.write_bytes(b"")
    image2 = tmp_path / "b.jpg"
    image2.write_bytes(b"")
    id1, id2 = uuid4(), uuid4()
    service, _, _ = _build_service(
        {image1: [FaceBoxEmbedding(box=box, embedding=embedding)], image2: []},
        embedding,
        None,
    )
    command = MatchPersonsCommand(
        photo_ids=(id1, id2), images=(image1, image2)
    )
    results = service.execute(command)
    assert len(results) == 2
    assert results[0].photo_id == id1
    assert results[0].box == box
    assert results[1].photo_id == id2
    assert results[1].box is None
