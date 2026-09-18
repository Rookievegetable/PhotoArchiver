"""OverviewPresenter five-state matrix (Batch 3 IA) — pure logic, no Qt.

The presenter consumes the cached WorkspaceStatus snapshot via the real
WorkspaceController guidance translation; no repository, no widget, no
worker is involved.
"""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from photo_archiver.application.dtos.workspace import (
    ModelAvailability, WorkspaceStatus,
)
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.controllers.overview_presenter import (
    OverviewPresenter,
)
from photo_archiver.presentation.controllers.workspace_controller import (
    WorkspaceController,
)

READY = WorkspaceStatus(
    has_persons=True, has_photos=True, pending_match_count=3,
    pending_review_count=2, archivable_count=1, archive_root_available=True,
    model_availability=ModelAvailability.AVAILABLE,
)
EMPTY = replace(
    READY, has_persons=False, has_photos=False, pending_match_count=0,
    pending_review_count=0, archivable_count=0, archive_root_available=False,
)


def _presenter(status: WorkspaceStatus | None) -> OverviewPresenter:
    """Build the presenter over a real controller with a pre-cached snapshot."""
    controller = WorkspaceController(Mock())  # query never reached below.
    controller.status = status
    return OverviewPresenter(controller)


def test_missing_snapshot_renders_nothing_and_no_primary() -> None:
    model = _presenter(None).build()
    assert model.steps == ()
    assert model.primary is None
    assert model.primary_label == ""
    assert model.primary_tooltip == text.OVERVIEW_STATUS_NONE


def test_ready_state_lists_five_steps_with_flow_semantics() -> None:
    model = _presenter(READY).build()
    assert [step.label for step in model.steps] == [
        text.OVERVIEW_STEP_IMPORT, text.OVERVIEW_STEP_SCAN,
        text.OVERVIEW_STEP_MATCH, text.OVERVIEW_STEP_REVIEW,
        text.OVERVIEW_STEP_ARCHIVE,
    ]
    done = [step.done for step in model.steps]
    assert done == [True, True, False, False, False]  # 3 pending / 2 review / 1 archivable
    assert model.steps[2].detail == text.WORKSPACE_MATCH_READY.format(count=3)


def test_empty_library_primary_is_import() -> None:
    model = _presenter(EMPTY).build()
    assert model.primary == "import"
    assert model.primary_label == text.OVERVIEW_PRIMARY_IMPORT
    assert model.primary_tooltip == text.REFUSAL_NO_PERSONS
    assert [step.done for step in model.steps] == [False, False, False, True, True]


def test_persons_without_photos_primary_is_scan() -> None:
    model = _presenter(replace(EMPTY, has_persons=True)).build()
    assert model.primary == "scan"
    assert model.primary_label == text.OVERVIEW_PRIMARY_SCAN


def test_photos_without_persons_still_route_to_import() -> None:
    # 识别同时需要人员和照片：先扫描再导入是允许的，主 CTA 指向缺失的人员轴。
    model = _presenter(replace(EMPTY, has_photos=True)).build()
    assert model.primary == "import"
    assert model.primary_label == text.OVERVIEW_PRIMARY_IMPORT


def test_pending_match_with_available_model_primary_is_match() -> None:
    model = _presenter(READY).build()
    assert model.primary == "match"
    assert model.primary_label == text.OVERVIEW_PRIMARY_RUN_MATCH


@pytest.mark.parametrize("availability", [
    ModelAvailability.MISSING, ModelAvailability.UNKNOWN,
])
def test_unavailable_model_routes_to_model_help(availability: ModelAvailability) -> None:
    model = _presenter(replace(READY, model_availability=availability)).build()
    assert model.primary == "model"
    assert model.primary_label == text.OVERVIEW_PRIMARY_MODEL


def test_fully_recognized_pending_review_primary_is_review() -> None:
    status = replace(READY, pending_match_count=0)
    model = _presenter(status).build()
    assert model.primary == "review"
    assert model.primary_label == text.OVERVIEW_PRIMARY_REVIEW
    assert model.steps[3].done is False
    assert model.steps[2].done is True


def test_archivable_photos_primary_is_archive() -> None:
    status = replace(READY, pending_match_count=0, pending_review_count=0)
    model = _presenter(status).build()
    assert model.primary == "archive"
    assert model.primary_label == text.OVERVIEW_PRIMARY_ARCHIVE
    assert model.steps[4].done is False


def test_unavailable_archive_root_routes_to_settings() -> None:
    status = replace(
        READY, pending_match_count=0, pending_review_count=0,
        archivable_count=0, archive_root_available=False,
    )
    model = _presenter(status).build()
    assert model.primary == "settings"
    assert model.primary_label == text.OVERVIEW_PRIMARY_SETTINGS


def test_fully_processed_library_invites_more_scans() -> None:
    status = replace(
        READY, pending_match_count=0, pending_review_count=0,
        archivable_count=0,
    )
    model = _presenter(status).build()
    assert model.primary == "scan"
    assert all(step.done for step in model.steps)
