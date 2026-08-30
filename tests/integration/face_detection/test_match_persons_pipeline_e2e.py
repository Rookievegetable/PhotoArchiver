"""Commit 4 — match-persons persistence integration (AC-015 evidence).

Runs the REAL MatchPersonsTask (Commit 1) → REAL MatchPersonsService → REAL
SQLite repositories (recognition / photo / person / face_embedding / folder)
→ REAL ReviewRecognitionService closed loop, with only the Face Model port
(FaceDetector / FaceRecognizer) replaced by a deterministic double and the
matching done by the real CosinePersonMatcher.

This proves the architecture + business chain (not the model): service output
is genuinely persisted as PENDING rows visible through list_pending(), and the
review workflow genuinely transitions them to APPROVED. No repository, service,
or SQLite component is mocked. Requires no InsightFace model pack.
"""

from pathlib import Path
from uuid import UUID

from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
from photo_archiver.application.commands import MatchPersonsCommand
from photo_archiver.application.services import MatchPersonsService, ReviewRecognitionService
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
from photo_archiver.workers import MatchPersonsTask
from photo_archiver.workers.events import TaskCompleted, TaskStarted


# Deterministic model-port doubles.
_PERSON_VECTOR = (1.0, 0.0, 0.0, 0.0)  # matches itself → cosine 1.0
_ORTHOGONAL_VECTOR = (0.0, 1.0, 0.0, 0.0)  # dot 0 → below threshold → Unknown


def _pair(embedding: FaceEmbedding) -> FaceBoxEmbedding:
    """Build one detected-face pair with a fixed high-confidence box."""
    return FaceBoxEmbedding(
        box=FaceBox(x1=0, y1=0, x2=10, y2=10, confidence=0.95),
        embedding=embedding,
    )


class _StubDetector:
    """Returns a configured per-image face list; ignores image bytes."""

    def __init__(self, by_image: dict[str, list[FaceBoxEmbedding]]) -> None:
        self._by_image = by_image

    def detect(self, image: Path) -> list[FaceBox]:
        """Return only the boxes for the configured image."""
        return [pair.box for pair in self._by_image.get(str(image), [])]

    def detect_with_embeddings(self, image: Path) -> list[FaceBoxEmbedding]:
        """Return the configured face-with-embedding pairs for the image."""
        return list(self._by_image.get(str(image), []))


class _UnusedRecognizer:
    """Satisfies the FaceRecognizer protocol slot; never called (Issue-001)."""

    def extract(self, image, box):  # noqa: ANN001
        raise NotImplementedError("recognizer must not be called on this path")

    def extract_from(self, box, faces):  # noqa: ANN001
        raise NotImplementedError("recognizer must not be called on this path")


class _SqliteStack:
    """One real SQLite schema with all repositories, plus id bookkeeping."""

    def __init__(self, db_path: Path) -> None:
        self._folder: Folder | None = None
        self.provider = SQLiteConnectionProvider(db_path)
        self.provider.initialize_schema()
        self.folders = SQLiteFolderRepository(self.provider)
        self.photos = SQLitePhotoRepository(self.provider)
        self.people = SQLitePersonRepository(self.provider)
        self.embeddings = SQLiteFaceEmbeddingRepository(self.provider)
        self.recognition = SQLiteRecognitionRepository(self.provider)

    def add_photo(self, name: str, path_name: str) -> UUID:
        """Persist a photo under this stack's shared folder and return its id."""
        folder = self._ensure_folder()
        photo = Photo(path=PhotoPath(path_name), folder_id=folder.id, original_name=name)
        self.photos.add(photo)
        return photo.id  # type: ignore[return-value]  # guaranteed by __post_init__

    def _ensure_folder(self) -> Folder:
        """Create the shared folder once per stack (folders.path is unique)."""
        if self._folder is None:
            self._folder = Folder(path=PhotoPath("photos"), total_photos=1)
            self.folders.add(self._folder)
        return self._folder

    def add_person(self, name: str = "Alice") -> Person:
        """Persist a person and return the aggregate with its stable id."""
        person = Person(name=name)
        self.people.add(person)
        return person


def _build_service(
    stack: _SqliteStack,
    by_image: dict[str, list[FaceBoxEmbedding]],
    *,
    max_workers: int = 1,
) -> MatchPersonsService:
    """Assemble the REAL service with deterministic model ports + real repos."""
    return MatchPersonsService(
        detector=_StubDetector(by_image),
        recognizer=_UnusedRecognizer(),  # type: ignore[arg-type]
        matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=stack.embeddings,
        recognition_repository=stack.recognition,
        max_workers=max_workers,
    )


def _run_task(task: MatchPersonsTask) -> dict:
    """Run a real WorkerTask end-to-end and capture its event stream."""
    events: list = []
    task.subscribe(events.append)
    results = task.run()
    started = [e for e in events if isinstance(e, TaskStarted)]
    completed = [e for e in events if isinstance(e, TaskCompleted)]
    assert len(started) == 1
    assert len(completed) == 1
    return {"results": results, "completed": completed[0], "events": events}


def test_real_task_persists_pending_records_to_sqlite(tmp_path: Path) -> None:
    """AC-015: Task→Service→SQLite persists PENDING rows visible via list_pending."""
    stack = _SqliteStack(tmp_path / "match.db")
    person = stack.add_person()
    photo_id = stack.add_photo("a.jpg", "photos/a.jpg")
    stack.embeddings.save(person.id, FaceEmbedding.from_sequence(_PERSON_VECTOR))
    raw = str(PhotoPath("photos/a.jpg").raw_path)
    service = _build_service(stack, {raw: [_pair(FaceEmbedding.from_sequence(_PERSON_VECTOR))]})
    task = MatchPersonsTask(
        service,
        MatchPersonsCommand(photo_ids=(photo_id,), images=(PhotoPath("photos/a.jpg").raw_path,)),
    )

    outcome = _run_task(task)

    assert len(outcome["results"]) == 1
    matched = stack.recognition.list_by_photo(photo_id)
    assert len(matched) == 1
    assert matched[0].status is MatchStatus.PENDING
    assert matched[0].person_id == person.id
    assert matched[0].confidence == 1.0
    pending = stack.recognition.list_pending()
    assert [r.id for r in pending] == [matched[0].id]


def test_face_below_threshold_persists_unknown_pending(tmp_path: Path) -> None:
    """A detected face that matches no candidate still persists as Unknown/PENDING."""
    stack = _SqliteStack(tmp_path / "match.db")
    person = stack.add_person()
    photo_id = stack.add_photo("a.jpg", "photos/a.jpg")
    stack.embeddings.save(person.id, FaceEmbedding.from_sequence(_PERSON_VECTOR))
    raw = str(PhotoPath("photos/a.jpg").raw_path)
    service = _build_service(
        stack,
        {raw: [_pair(FaceEmbedding.from_sequence(_ORTHOGONAL_VECTOR))]},
    )
    task = MatchPersonsTask(
        service,
        MatchPersonsCommand(photo_ids=(photo_id,), images=(PhotoPath("photos/a.jpg").raw_path,)),
    )

    outcome = _run_task(task)

    assert outcome["results"][0].best is None
    persisted = stack.recognition.list_by_photo(photo_id)
    assert len(persisted) == 1
    assert persisted[0].person_id is None
    assert persisted[0].confidence == 0.0
    assert persisted[0].status is MatchStatus.PENDING


def test_photo_without_face_persists_nothing(tmp_path: Path) -> None:
    """A photo with no detected face yields Unknown with no persisted record."""
    stack = _SqliteStack(tmp_path / "match.db")
    stack.add_person()
    photo_id = stack.add_photo("a.jpg", "photos/a.jpg")
    raw = str(PhotoPath("photos/a.jpg").raw_path)
    service = _build_service(stack, {raw: []})

    task = MatchPersonsTask(
        service,
        MatchPersonsCommand(photo_ids=(photo_id,), images=(PhotoPath("photos/a.jpg").raw_path,)),
    )
    outcome = _run_task(task)

    assert outcome["results"][0].best is None
    assert stack.recognition.list_by_photo(photo_id) == []


def test_review_approve_after_match_clears_pending(tmp_path: Path) -> None:
    """AC-015: matched PENDING results flow into the real review workflow."""
    stack = _SqliteStack(tmp_path / "match.db")
    person = stack.add_person()
    photo_id = stack.add_photo("a.jpg", "photos/a.jpg")
    stack.embeddings.save(person.id, FaceEmbedding.from_sequence(_PERSON_VECTOR))
    raw = str(PhotoPath("photos/a.jpg").raw_path)
    service = _build_service(stack, {raw: [_pair(FaceEmbedding.from_sequence(_PERSON_VECTOR))]})
    task = MatchPersonsTask(
        service,
        MatchPersonsCommand(photo_ids=(photo_id,), images=(PhotoPath("photos/a.jpg").raw_path,)),
    )
    _run_task(task)

    review = ReviewRecognitionService(stack.recognition)
    pending = stack.recognition.list_pending()
    assert len(pending) == 1
    assert pending[0].person_id == person.id

    transitioned = review.approve(pending[0].id)

    assert transitioned is not None
    assert transitioned.status is MatchStatus.APPROVED
    assert stack.recognition.list_pending() == []
    approved = stack.recognition.list_approved_by_person(person.id)
    assert [r.id for r in approved] == [pending[0].id]


def test_parallel_batch_persists_all_photos_in_order(tmp_path: Path) -> None:
    """max_workers > 1 still matches + persists every photo (single add_many)."""
    stack = _SqliteStack(tmp_path / "match.db")
    person = stack.add_person()
    stack.embeddings.save(person.id, FaceEmbedding.from_sequence(_PERSON_VECTOR))
    name_and_path = [("a.jpg", "photos/a.jpg"), ("b.jpg", "photos/b.jpg"), ("c.jpg", "photos/c.jpg")]
    photo_ids = tuple(stack.add_photo(n, p) for n, p in name_and_path)
    images = tuple(PhotoPath(p).raw_path for _, p in name_and_path)
    by_image = {
        str(PhotoPath(p).raw_path): [_pair(FaceEmbedding.from_sequence(_PERSON_VECTOR))]
        for _, p in name_and_path
    }
    service = _build_service(stack, by_image, max_workers=2)

    task = MatchPersonsTask(service, MatchPersonsCommand(photo_ids=photo_ids, images=images))
    outcome = _run_task(task)

    assert [r.photo_id for r in outcome["results"]] == list(photo_ids)
    pending = stack.recognition.list_pending()
    assert len(pending) == 3
    assert {r.photo_id for r in pending} == set(photo_ids)
    assert all(r.person_id == person.id for r in pending)


