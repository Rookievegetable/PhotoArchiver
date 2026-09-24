from pathlib import Path
from uuid import uuid4

from photo_archiver.application import StartRecognitionRunCommand
from photo_archiver.application.services import RunRecognitionService
from photo_archiver.domain import (
    FaceBox, FaceBoxEmbedding, FaceCountRange, FaceEmbedding, ImageUnreadableError,
)
from photo_archiver.infrastructure.repositories import (
    InMemoryFaceObservationRepository, InMemoryRecognitionRunRepository,
)


class _Detector:
    def __init__(self, values): self.values = values
    def detect_with_embeddings(self, image):
        value = self.values[image]
        if isinstance(value, Exception):
            raise value
        return value


class _Matcher:
    def match(self, embedding, candidates):
        return (next(iter(candidates)), 0.8) if candidates else None


class _Embeddings:
    def __init__(self, values=None): self.values = values or {}
    def list_all(self, limit=None, offset=0): return self.values


class _Results:
    def __init__(self): self.rows = []
    def add(self, result): self.rows.append(result)
    def list_by_photo(self, photo_id): return [r for r in self.rows if r.photo_id == photo_id]


def _pair(x, score=0.9):
    return FaceBoxEmbedding(FaceBox(x, 0, x + 10, 10, score), FaceEmbedding((1.0,)))


def test_run_persists_all_faces_scope_and_compatibility(tmp_path: Path):
    paths = [tmp_path / f"{i}.jpg" for i in range(3)]
    for path in paths:
        path.write_bytes(b"x")
    photo_ids = [uuid4() for _ in paths]
    run_repo = InMemoryRecognitionRunRepository()
    obs_repo = InMemoryFaceObservationRepository()
    results = _Results()
    service = RunRecognitionService(
        _Detector({paths[0]: [_pair(20, .8), _pair(0, .8), _pair(10, .9)],
                    paths[1]: [], paths[2]: ImageUnreadableError("bad")}),
        _Matcher(), _Embeddings(), results, run_repo, obs_repo, max_workers=2,
    )
    run = service.execute(StartRecognitionRunCommand(
        tuple(photo_ids), tuple(paths), (FaceCountRange(1, 1),), {"model": "test"},
    ))
    assert run.status == "completed"
    assert run.face_count == 3 and run.no_face_count == 1 and run.unreadable_count == 1
    observations = obs_repo.list_by_run(run.id)
    assert [o.face_index for o in observations] == [0, 1, 2]
    assert all(o.scope_verdict == "out_of_selected_scope" for o in observations)
    assert results.rows == []


def test_run_rerun_does_not_overwrite_old_run_or_observations(tmp_path: Path):
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"x")
    photo_id = uuid4()
    run_repo = InMemoryRecognitionRunRepository()
    obs_repo = InMemoryFaceObservationRepository()
    service = RunRecognitionService(
        _Detector({image: [_pair(0)]}), _Matcher(), _Embeddings(), _Results(), run_repo, obs_repo,
    )
    command = StartRecognitionRunCommand((photo_id,), (image,), (FaceCountRange(1, None),))
    first = service.execute(command)
    second = service.execute(command)
    assert first.id != second.id
    assert len(run_repo.list_runs()) == 2
    assert len(obs_repo.list_by_run(first.id)) == 1
    assert len(obs_repo.list_by_run(second.id)) == 1


def test_run_counts_detector_errors_and_keeps_batch_going(tmp_path: Path) -> None:
    image = tmp_path / "error.jpg"
    image.write_bytes(b"x")
    photo_id = uuid4()
    service = RunRecognitionService(
        _Detector({image: RuntimeError("inference failed")}), _Matcher(), _Embeddings(),
        _Results(), InMemoryRecognitionRunRepository(), InMemoryFaceObservationRepository(),
    )

    run = service.execute(StartRecognitionRunCommand((photo_id,), (image,)))

    assert run.status == "completed"
    assert run.error_count == 1
    assert run.unreadable_count == 0


def test_run_keeps_legacy_compatibility_only_for_in_scope_photos(tmp_path: Path) -> None:
    image = tmp_path / "face.jpg"
    image.write_bytes(b"x")
    photo_id = uuid4()
    person_id = uuid4()
    results = _Results()
    service = RunRecognitionService(
        _Detector({image: [_pair(0)]}), _Matcher(), _Embeddings({person_id: FaceEmbedding((1.0,))}),
        results, InMemoryRecognitionRunRepository(), InMemoryFaceObservationRepository(),
    )

    run = service.execute(StartRecognitionRunCommand(
        (photo_id,), (image,), (FaceCountRange(1, 1),),
    ))

    assert run.in_scope_photo_count == 1
    assert len(results.rows) == 1
    assert results.rows[0].photo_id == photo_id
    assert results.rows[0].person_id == person_id


def test_run_flushes_observations_at_fifty_with_remainder(tmp_path: Path) -> None:
    class RecordingObservations(InMemoryFaceObservationRepository):
        batches: list[int]

        def __init__(self) -> None:
            super().__init__()
            self.batches = []

        def add_many(self, observations) -> None:
            self.batches.append(len(observations))
            super().add_many(observations)

    paths = [tmp_path / f"{index}.jpg" for index in range(51)]
    for path in paths:
        path.write_bytes(b"x")
    observations = RecordingObservations()
    service = RunRecognitionService(
        _Detector({path: [_pair(index)] for index, path in enumerate(paths)}), _Matcher(), _Embeddings(),
        _Results(), InMemoryRecognitionRunRepository(), observations,
    )

    run = service.execute(StartRecognitionRunCommand(
        tuple(uuid4() for _ in paths), tuple(paths), (FaceCountRange(1, 1),),
    ))

    assert run.face_count == 51
    assert observations.batches == [50, 1]


def test_run_marks_cancelled_and_keeps_processed_observations(tmp_path: Path) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    service = RunRecognitionService(
        _Detector({first: [_pair(0)], second: [_pair(1)]}), _Matcher(), _Embeddings(),
        _Results(), InMemoryRecognitionRunRepository(), InMemoryFaceObservationRepository(),
    )

    class CancellingDetector:
        def detect_with_embeddings(self, image):
            if image == first:
                service.cancel()
            return [_pair(0 if image == first else 1)]

    service._detector = CancellingDetector()  # noqa: SLF001
    run = service.execute(StartRecognitionRunCommand(
        (uuid4(), uuid4()), (first, second), (FaceCountRange(1, 1),),
    ))

    assert run.status == "cancelled"
    assert run.face_count <= 2
