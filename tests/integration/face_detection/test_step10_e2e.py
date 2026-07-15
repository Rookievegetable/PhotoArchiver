"""End-to-end integration test for the Step 10 recognition closed loop.

Runs the real InsightFace detector + recognizer + cosine matcher + SQLite
recognition repository, then approves/rejects through the review service.
Requires the buffalo_l model pack (fetched via download_models.py) and a
sample face JPG under tests/integration/resources/. Both are skipped when
missing so CI can run the full suite without the model pack.
"""

from pathlib import Path

import pytest

from photo_archiver.application.commands import MatchPersonsCommand
from photo_archiver.application.services import (
    MatchPersonsService,
    ReviewRecognitionService,
)
from photo_archiver.ai import (
    CosinePersonMatcher,
    InsightFaceDetector,
    InsightFaceRecognizer,
)
from photo_archiver.domain import (
    Folder,
    MatchStatus,
    Photo,
    PhotoPath,
)
from photo_archiver.infrastructure import (
    SQLiteConnectionProvider,
    SQLiteFolderRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRepository,
)

_ROOT = Path(__file__).resolve().parents[2]
_MODEL_ROOT = _ROOT / "resources" / "models"
_SAMPLE_IMAGE = _ROOT / "tests" / "integration" / "resources" / "sample_face.jpg"

pytestmark = pytest.mark.skipif(
    not (InsightFaceDetector.model_available(_MODEL_ROOT) and _SAMPLE_IMAGE.exists()),
    reason="InsightFace model pack or sample image missing — run download_models.py",
)


@pytest.fixture(scope="module")
def detector() -> InsightFaceDetector:
    return InsightFaceDetector.from_model_path(_MODEL_ROOT)


@pytest.fixture(scope="module")
def recognizer(detector: InsightFaceDetector) -> InsightFaceRecognizer:
    return InsightFaceRecognizer(detector._analysis)  # type: ignore[attr-defined]


@pytest.fixture()
def photo_id(tmp_path: Path) -> tuple:
    """Persist a sample photo and folder, return (provider, photo_id, cleanup)."""
    provider = SQLiteConnectionProvider(tmp_path / "e2e.sqlite3")
    provider.initialize_schema()
    folder_repo = SQLiteFolderRepository(provider)
    photo_repo = SQLitePhotoRepository(provider)
    folder = Folder(path=PhotoPath("sample"), total_photos=1)
    folder_repo.add(folder)
    photo = Photo(path=PhotoPath("sample/face.jpg"), folder_id=folder.id)
    photo_repo.add(photo)
    return provider, photo.id


def test_end_to_end_detect_match_review_persist(
    tmp_path: Path,
    detector: InsightFaceDetector,
    recognizer: InsightFaceRecognizer,
    photo_id: tuple,
) -> None:
    """Full pipeline: detect → extract → match → persist → approve."""
    provider, target_photo_id = photo_id
    person_repo = SQLitePersonRepository(provider)
    recognition_repo = SQLiteRecognitionRepository(provider)

    matcher = CosinePersonMatcher(threshold=0.40)
    service = MatchPersonsService(
        detector=detector,
        recognizer=recognizer,
        matcher=matcher,
        person_repository=person_repo,
        photo_repository=SQLitePhotoRepository(provider),
        recognition_repository=recognition_repo,
        match_threshold=0.40,
    )
    command = MatchPersonsCommand(
        photo_ids=(target_photo_id,), images=(_SAMPLE_IMAGE,)
    )
    results = service.execute(command)
    assert len(results) == 1
    persisted = recognition_repo.list_by_photo(target_photo_id)
    assert len(persisted) == 1
    assert persisted[0].status is MatchStatus.PENDING

    review = ReviewRecognitionService(recognition_repo)
    refreshed = review.approve(persisted[0].id)
    assert refreshed is not None
    assert refreshed.status is MatchStatus.APPROVED
    assert recognition_repo.list_pending() == []


def test_end_to_end_bulk_reject(
    tmp_path: Path,
    detector: InsightFaceDetector,
    recognizer: InsightFaceRecognizer,
    photo_id: tuple,
) -> None:
    """Bulk reject must transition all pending results for a photo."""
    provider, target_photo_id = photo_id
    recognition_repo = SQLiteRecognitionRepository(provider)
    from photo_archiver.domain import RecognitionResult

    r1 = RecognitionResult(photo_id=target_photo_id, confidence=0.5)
    r2 = RecognitionResult(photo_id=target_photo_id, confidence=0.6)
    recognition_repo.add(r1)
    recognition_repo.add(r2)

    review = ReviewRecognitionService(recognition_repo)
    transitioned = review.bulk_reject((r1.id, r2.id))
    assert transitioned == 2
    assert recognition_repo.list_pending() == []
