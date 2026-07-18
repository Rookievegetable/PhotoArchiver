"""Tests for ArchiveController — preview + execute command construction."""

import pytest

pytest.importorskip("PySide6")

from pathlib import Path
from uuid import uuid4

from photo_archiver.application.dtos import ArchivePlan
from photo_archiver.presentation.controllers import ArchiveController


class _FakePlanner:
    """Captures preview() args and returns a canned plan."""

    def __init__(self, plan: ArchivePlan) -> None:
        self._plan = plan
        self.calls: list = []

    def plan(self, archive_root, person_ids):
        self.calls.append((archive_root, person_ids))
        return self._plan


class _FakeArchiveUseCase:
    """Captures execute() command for assertion."""

    def __init__(self) -> None:
        self.last_command = None

    def execute(self, command):
        self.last_command = command
        from photo_archiver.application.dtos import ArchiveResult
        return ArchiveResult(planned_count=0)


class _FakeExecutor:
    def __init__(self) -> None:
        self.last_task = None

    def submit(self, task):
        self.last_task = task
        return task


def test_preview_calls_planner_with_root_and_person_ids() -> None:
    """preview() forwards archive_root + person_ids to the planner, synchronously."""
    planner = _FakePlanner(ArchivePlan())
    controller = ArchiveController(
        planner,  # type: ignore[arg-type]
        _FakeArchiveUseCase(),  # type: ignore[arg-type]
        _FakeExecutor(),  # type: ignore[arg-type]
    )
    pid = uuid4()
    controller.preview(Path("/archive"), (pid,))
    assert planner.calls[0] == (str(Path("/archive")), (pid,))


def test_execute_builds_command_with_strategy_and_dry_run() -> None:
    """execute() builds ArchivePhotosCommand carrying all flags."""
    use_case = _FakeArchiveUseCase()
    executor = _FakeExecutor()
    controller = ArchiveController(
        _FakePlanner(ArchivePlan()),  # type: ignore[arg-type]
        use_case,  # type: ignore[arg-type]
        executor,  # type: ignore[arg-type]
    )
    pid = uuid4()
    controller.execute(
        Path("/archive"),
        person_ids=(pid,),
        conflict_strategy="rename",
        dry_run=True,
    )
    cmd = executor.last_task._command
    assert cmd.archive_root == Path("/archive")
    assert cmd.person_ids == (pid,)
    assert cmd.conflict_strategy == "rename"
    assert cmd.dry_run is True


def test_execute_defaults_person_ids_to_empty_tuple() -> None:
    """execute() with no person_ids means 'all persons with approvals'."""
    executor = _FakeExecutor()
    controller = ArchiveController(
        _FakePlanner(ArchivePlan()),  # type: ignore[arg-type]
        _FakeArchiveUseCase(),  # type: ignore[arg-type]
        executor,  # type: ignore[arg-type]
    )
    controller.execute(Path("/archive"))
    assert executor.last_task._command.person_ids == ()
