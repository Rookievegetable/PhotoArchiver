"""Stage C Commit 1 repository tests."""

from datetime import datetime
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from photo_archiver.domain import (
    FaceBox,
    FaceCountRange,
    FaceEmbedding,
    FaceObservation,
    Photo,
    PhotoPath,
    RecognitionRun,
    RecognitionRunStats,
    RunPhotoSnapshot,
)
from photo_archiver.infrastructure import (
    SQLiteConnectionProvider,
    SQLiteFaceObservationRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRunRepository,
)


def _provider(tmp_path: Path) -> SQLiteConnectionProvider:
    provider = SQLiteConnectionProvider(tmp_path / "stage-c.sqlite3")
    provider.initialize_schema()
    return provider


def _observation(run_id, photo_id, index: int = 0) -> FaceObservation:
    return FaceObservation(
        run_id=run_id,
        photo_id=photo_id,
        face_index=index,
        photo_face_count=2,
        det_score=0.9,
        box=FaceBox(index, 0, index + 10, 10),
        embedding=FaceEmbedding((0.1, 0.2)),
        scope_verdict="in_selected_scope",
    )


def test_sqlite_recognition_run_repositories_round_trip_and_keep_snapshot(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    runs = SQLiteRecognitionRunRepository(provider)
    photos = SQLitePhotoRepository(provider)
    photo = Photo(path=PhotoPath("event.jpg"))
    photos.add(photo)
    assert photo.id is not None
    run = RecognitionRun(parameters={"detector": "test", "quality_formula": "v1"})
    assert run.id is not None
    runs.add_run(run)
    runs.add_run_photos(
        run.id,
        [RunPhotoSnapshot(run.id, photo.id, str(photo.path), datetime(2026, 1, 1))],
    )
    runs.add_run_scopes(run.id, [FaceCountRange(1, 1), FaceCountRange(2, 3)])

    loaded = runs.get_run(run.id)
    assert loaded is not None
    assert loaded.parameters == {"detector": "test", "quality_formula": "v1"}
    assert runs.list_run_photos(run.id)[0].photo_id == photo.id
    assert runs.list_run_scopes(run.id) == [FaceCountRange(1, 1), FaceCountRange(2, 3)]

    run.parameters = {"detector": "changed"}
    run.start()
    run.complete(RecognitionRunStats(face_count=2, in_scope_photo_count=1))
    assert runs.update_run(run) == 1
    persisted = runs.get_run(run.id)
    assert persisted is not None
    assert persisted.parameters == {"detector": "test", "quality_formula": "v1"}
    assert persisted.face_count == 2


def test_sqlite_observation_batch_rejects_duplicate_keys(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    photos = SQLitePhotoRepository(provider)
    photo = Photo(path=PhotoPath("event.jpg"))
    photos.add(photo)
    assert photo.id is not None
    runs = SQLiteRecognitionRunRepository(provider)
    run = RecognitionRun()
    assert run.id is not None
    runs.add_run(run)
    observations = [_observation(run.id, photo.id, 0), _observation(run.id, photo.id, 1)]
    repository = SQLiteFaceObservationRepository(provider)
    repository.add_many(observations)

    assert repository.list_by_run(run.id) == observations
    with pytest.raises(sqlite3.IntegrityError):
        repository.add_many([_observation(run.id, photo.id, 0)])


def test_sqlite_photo_delete_cascades_run_photos_and_observations(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    photos = SQLitePhotoRepository(provider)
    photo = Photo(path=PhotoPath("event.jpg"))
    photos.add(photo)
    assert photo.id is not None
    runs = SQLiteRecognitionRunRepository(provider)
    run = RecognitionRun()
    assert run.id is not None
    runs.add_run(run)
    runs.add_run_photos(run.id, [RunPhotoSnapshot(run.id, photo.id, "event.jpg")])
    observations = SQLiteFaceObservationRepository(provider)
    observations.add_many([_observation(run.id, photo.id)])

    with provider.connect() as connection:
        connection.execute("DELETE FROM photos WHERE id = ?", (str(photo.id),))

    assert runs.get_run(run.id) is not None
    assert runs.list_run_photos(run.id) == []
    assert observations.list_by_run(run.id) == []


def test_in_memory_recognition_repositories_share_contract(tmp_path: Path) -> None:
    from photo_archiver.infrastructure.repositories import (
        InMemoryFaceObservationRepository,
        InMemoryRecognitionRunRepository,
    )

    runs = InMemoryRecognitionRunRepository()
    observations = InMemoryFaceObservationRepository()
    run = RecognitionRun()
    assert run.id is not None
    runs.add_run(run)
    runs.add_run_scopes(run.id, [FaceCountRange(11, None)])
    runs.add_run_photos(run.id, [])
    assert runs.get_run(run.id) is run
    assert runs.list_run_scopes(run.id) == [FaceCountRange(11, None)]

    photo_id = uuid4()
    observation = _observation(run.id, photo_id)
    observations.add_many([observation])
    assert observations.list_by_run_photo(run.id, photo_id) == [observation]
    with pytest.raises(ValueError):
        observations.add_many([observation])
