"""Stage C Commit 1 domain boundary tests."""

import pytest

from photo_archiver.domain import (
    FaceCountRange,
    FaceObservation,
    RecognitionRun,
    RecognitionRunStats,
    ValidationError,
    classify_scope,
)
from photo_archiver.domain.value_objects import FaceBox, FaceEmbedding
from uuid import uuid4


def test_face_count_range_parses_and_round_trips() -> None:
    ranges = [FaceCountRange.parse("1"), FaceCountRange.parse("2-3"), FaceCountRange.parse("11+")]

    assert [str(value) for value in ranges] == ["1", "2-3", "11+"]
    assert ranges[0].contains(1) and not ranges[0].contains(2)
    assert ranges[1].contains(3) and not ranges[1].contains(4)
    assert ranges[2].contains(11)


@pytest.mark.parametrize("text", ["", "-1", "3-2", "1-", "x", "1-2-3"])
def test_face_count_range_rejects_invalid_text(text: str) -> None:
    with pytest.raises(ValidationError):
        FaceCountRange.parse(text)


def test_classify_scope_is_photo_level() -> None:
    selected = [FaceCountRange(1, 1)]

    assert classify_scope(1, selected) == "in_selected_scope"
    assert classify_scope(5, selected) == "out_of_selected_scope"
    with pytest.raises(ValidationError):
        classify_scope(0, selected)


def test_face_observation_is_immutable_and_requires_real_face() -> None:
    observation = FaceObservation(
        run_id=uuid4(),
        photo_id=uuid4(),
        face_index=0,
        photo_face_count=2,
        det_score=0.9,
        box=FaceBox(0, 0, 10, 10),
        embedding=FaceEmbedding((0.1, 0.2)),
        scope_verdict="in_selected_scope",
    )

    with pytest.raises(Exception):
        observation.det_score = 0.1  # type: ignore[misc]
    with pytest.raises(ValidationError):
        FaceObservation(
            run_id=observation.run_id,
            photo_id=observation.photo_id,
            face_index=0,
            photo_face_count=0,
            det_score=0.9,
            box=FaceBox(0, 0, 10, 10),
            embedding=FaceEmbedding((0.1,)),
            scope_verdict="out_of_selected_scope",
        )


def test_recognition_run_lifecycle_and_terminal_guard() -> None:
    run = RecognitionRun(parameters={"detector": "test", "quality_formula": "v1"})

    with pytest.raises(ValidationError):
        run.complete(RecognitionRunStats())
    run.start()
    run.complete(RecognitionRunStats(face_count=2, in_scope_photo_count=1))
    assert run.status == "completed"
    with pytest.raises(ValidationError):
        run.start()
    with pytest.raises(ValidationError):
        run.cancel()


def test_recognition_run_stats_reject_negative_values() -> None:
    with pytest.raises(ValidationError):
        RecognitionRunStats(face_count=-1)
