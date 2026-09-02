"""Commit 4 — UI → Application → Persistence evidence (AC-016).

Drives the REAL MatchPersonsController (Commit 2) through a REAL
QtWorkerExecutor thread pool — exactly what the UI submits via the Commit 3
MainWindow action — into REAL MatchPersonsService → REAL SQLite repositories.
Only the Face Model port is a deterministic double (real CosinePersonMatcher).

After the completed signal fires on the caller thread, the PENDING rows are
visible through a separate repository handle, proving the persisted chain the
UI hands off to. The controller's single-flight guard is released by the
terminal event per the Commit 2 contract, so a second click re-runs the
real-DB refusals path (already-recognized resume semantics).
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from pathlib import Path
from uuid import UUID

from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
from photo_archiver.application.services import MatchPersonsService
from photo_archiver.domain import (
    FaceBox,
    FaceBoxEmbedding,
    FaceEmbedding,
    Folder,
    MatchStatus,
    Person,
    Photo,
    PhotoPath,
)
from photo_archiver.infrastructure import (
    SQLiteConnectionProvider,
    SQLiteFaceEmbeddingRepository,
    SQLiteFolderRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRepository,
)
from photo_archiver.presentation.controllers import MatchPersonsController
from photo_archiver.workers import QtWorkerExecutor

_PERSON_VECTOR = (1.0, 0.0, 0.0, 0.0)


class _FaceStub:
    """Deterministic FaceDetector returning one known embedding per image."""

    def detect_with_embeddings(self, image: Path) -> list[FaceBoxEmbedding]:
        """Return a single detected face with the person's embedding."""
        return [
            FaceBoxEmbedding(
                box=FaceBox(x1=0, y1=0, x2=10, y2=10, confidence=0.95),
                embedding=FaceEmbedding.from_sequence(_PERSON_VECTOR),
            )
        ]

    def detect(self, image: Path) -> list[FaceBox]:
        """Return only the boxes for the detected face."""
        return [
            FaceBox(x1=0, y1=0, x2=10, y2=10, confidence=0.95),
        ]


class _UnusedRecognizer:
    """Satisfies the FaceRecognizer slot; never invoked on this path."""

    def extract(self, image, box):  # noqa: ANN001
        raise NotImplementedError

    def extract_from(self, box, faces):  # noqa: ANN001
        raise NotImplementedError


class _RealSqlite:
    """Real provider + repositories for one tmp database plus seed helper."""

    def __init__(self, db_path: Path) -> None:
        self.provider = SQLiteConnectionProvider(db_path)
        self.provider.initialize_schema()
        self.folders = SQLiteFolderRepository(self.provider)
        self.photos = SQLitePhotoRepository(self.provider)
        self.people = SQLitePersonRepository(self.provider)
        self.embeddings = SQLiteFaceEmbeddingRepository(self.provider)
        self.recognition = SQLiteRecognitionRepository(self.provider)

    def seed_person_and_photo(self) -> tuple[Person, UUID]:
        """Persist folder + photo + person + canonical embedding; return ids."""
        folder = Folder(path=PhotoPath("photos"), total_photos=1)
        self.folders.add(folder)
        photo = Photo(path=PhotoPath("photos/a.jpg"), folder_id=folder.id, original_name="a.jpg")
        self.photos.add(photo)
        person = Person(name="Alice")
        self.people.add(person)
        self.embeddings.save(person.id, FaceEmbedding.from_sequence(_PERSON_VECTOR))
        return person, photo.id  # type: ignore[return-value]  # guaranteed by __post_init__


def _make_service(db: _RealSqlite) -> MatchPersonsService:
    """REAL service with deterministic model ports + real repos."""
    return MatchPersonsService(
        detector=_FaceStub(),  # type: ignore[arg-type]
        recognizer=_UnusedRecognizer(),  # type: ignore[arg-type]
        matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=db.embeddings,
        recognition_repository=db.recognition,
    )


def test_controller_real_thread_pool_persists_pending(qtbot, tmp_path: Path) -> None:
    """AC-016: UI-bound start_match → real thread pool → SQLite PENDING visible."""
    db = _RealSqlite(tmp_path / "chain.db")
    person, _photo_id = db.seed_person_and_photo()

    service = _make_service(db)
    controller = MatchPersonsController(
        photos=db.photos,
        people=db.people,
        recognition=db.recognition,
        use_case=service,
        executor=QtWorkerExecutor(),
    )
    runnable = controller.start_match()
    assert runnable is not None, controller.last_refusal_reason
    controller.connect_signals(
        runnable,
        lambda _e: None,
        lambda _e: None,
        lambda _e: None,
        lambda _e: None,
    )

    blocker = qtbot.waitSignal(runnable.signals.completed, timeout=8000)
    assert blocker is not False

    # Diagnostic: poll for the pending row to distinguish a pure event-loop /
    # timing effect from a genuine persistence failure.
    qtbot.waitUntil(
        lambda: len(db.recognition.list_pending()) > 0,
        timeout=5000,
    )

    # Persistence visible from a fresh read via the same real repository.
    pending = db.recognition.list_pending()
    assert len(pending) == 1
    assert pending[0].person_id == person.id
    assert pending[0].status is MatchStatus.PENDING
    assert pending[0].confidence == 1.0

    # Single-flight guard released by the terminal event (Commit 2 contract).
    # Phase C CI finding: the guard-release and this read race across threads
    # (on Windows the race window even took down the interpreter) — poll
    # instead of asserting immediately after waitSignal.
    qtbot.waitUntil(lambda: not controller.is_running, timeout=8000)


def test_second_run_refused_by_real_db_resume_semantics(qtbot, tmp_path: Path) -> None:
    """After persistence, a second start is refused by the real already-matched query."""
    db = _RealSqlite(tmp_path / "chain.db")
    person, _photo_id = db.seed_person_and_photo()

    service = _make_service(db)
    controller = MatchPersonsController(
        photos=db.photos,
        people=db.people,
        recognition=db.recognition,
        use_case=service,
        executor=QtWorkerExecutor(),
    )
    first = controller.start_match()
    assert first is not None, controller.last_refusal_reason
    controller.connect_signals(
        first,
        lambda _e: None,
        lambda _e: None,
        lambda _e: None,
        lambda _e: None,
    )
    qtbot.waitSignal(first.signals.completed, timeout=8000)
    # Visibility race: the completion may land before the worker connection's
    # commit is visible from the main-thread connection. Poll — this exactly
    # mirrors production, where the completed slot runs on the next event-loop
    # turn after the commit becomes visible.
    qtbot.waitUntil(lambda: len(db.recognition.list_pending()) > 0, timeout=5000)
    # Phase C CI finding: poll for the guard release too — the worker-thread
    # releaser and the main-thread read must not be assumed ordered.
    qtbot.waitUntil(lambda: not controller.is_running, timeout=8000)

    second = controller.start_match()

    assert second is None
    assert "already have recognition results" in controller.last_refusal_reason
