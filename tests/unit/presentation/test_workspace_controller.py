"""Batch2 action policy: ordered prerequisites and a shared cached snapshot."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

pytest.importorskip("PySide6")

from photo_archiver.application.dtos.workspace import ModelAvailability, WorkspaceStatus
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.controllers.workspace_controller import (
    ActionGuidance,
    WorkspaceController,
)


READY = WorkspaceStatus(
    has_persons=True, has_photos=True, pending_match_count=3,
    pending_review_count=2, archivable_count=1, archive_root_available=True,
    model_availability=ModelAvailability.AVAILABLE,
)


@pytest.mark.parametrize("changes, expected", [
    ({"has_persons": False, "has_photos": False, "pending_match_count": 0,
      "model_availability": ModelAvailability.MISSING},
     ActionGuidance(False, text.REFUSAL_NO_PERSONS, "import")),
    ({"has_photos": False, "pending_match_count": 0,
      "model_availability": ModelAvailability.MISSING},
     ActionGuidance(False, text.REFUSAL_NO_PHOTOS, "scan")),
    ({"pending_match_count": 0, "model_availability": ModelAvailability.MISSING},
     ActionGuidance(False, text.WORKSPACE_MODEL_MISSING, "model")),
    ({"model_availability": ModelAvailability.MISSING},
     ActionGuidance(False, text.WORKSPACE_MODEL_MISSING, "model")),
    ({"model_availability": ModelAvailability.UNKNOWN},
     ActionGuidance(False, text.WORKSPACE_MODEL_UNKNOWN, "model")),
    ({}, ActionGuidance(True, text.WORKSPACE_MATCH_READY.format(count=3))),
    # 阶段 C Commit 3：全部已识别不再拒绝——识别可重跑，审核是下一步指引。
    ({"pending_match_count": 0},
     ActionGuidance(True, text.WORKSPACE_REANALYSIS_READY, "review")),
])
def test_match_prerequisite_matrix(changes, expected):
    query = Mock()
    query.execute.return_value = replace(READY, **changes)
    controller = WorkspaceController(query)
    controller.refresh(None)
    assert controller.match_guidance() == expected
    query.execute.assert_called_once_with(None)


@pytest.mark.parametrize("changes, expected", [
    ({"archive_root_available": False, "archivable_count": 0},
     ActionGuidance(False, text.WORKSPACE_ROOT_UNAVAILABLE, "settings")),
    ({"archive_root_available": False},
     ActionGuidance(False, text.WORKSPACE_ROOT_UNAVAILABLE, "settings")),
    ({"archivable_count": 0}, ActionGuidance(False, text.WORKSPACE_ARCHIVE_EMPTY, "review")),
    ({}, ActionGuidance(True, text.WORKSPACE_ARCHIVE_READY.format(count=1))),
])
def test_archive_prerequisite_matrix(changes, expected):
    controller = WorkspaceController(Mock(execute=Mock(return_value=replace(READY, **changes))))
    controller.refresh(Path("archive"))
    assert controller.archive_guidance() == expected


@pytest.mark.parametrize("count", [0, 7])
def test_review_remains_accessible_even_when_empty(count):
    controller = WorkspaceController(Mock(execute=Mock(
        return_value=replace(READY, pending_review_count=count),
    )))
    controller.refresh(None)
    assert controller.review_guidance() == ActionGuidance(
        True, text.REVIEW_EMPTY if count == 0 else text.STATUS_PENDING_REVIEW_COUNT.format(count=count),
    )


def test_unloaded_snapshot_does_not_query_implicitly():
    query = Mock()
    controller = WorkspaceController(query)
    assert controller.status is None
    assert controller.match_guidance() == ActionGuidance(False, text.WORKSPACE_UNKNOWN)
    assert controller.archive_guidance() == ActionGuidance(False, text.WORKSPACE_UNKNOWN)
    assert controller.review_guidance() == ActionGuidance(True, text.REVIEW_EMPTY)
    query.execute.assert_not_called()


def test_refresh_forwards_root_and_replaces_snapshot_only_on_explicit_refresh():
    query = Mock(execute=Mock(return_value=READY))
    controller = WorkspaceController(query)
    root = Path("archive")
    assert controller.refresh(root) is READY
    assert controller.status is READY
    query.execute.assert_called_once_with(root)
    next_status = replace(READY, pending_match_count=0, archivable_count=0)
    query.execute.return_value = next_status
    for _ in range(3):
        assert controller.match_guidance().enabled
        assert controller.archive_guidance().enabled
        controller.review_guidance()
    assert query.execute.call_count == 1
    assert controller.refresh(None) is next_status
    assert controller.status is next_status
    query.execute.assert_called_with(None)
    assert controller.match_guidance().next_action == "review"
    assert controller.archive_guidance().next_action == "review"
