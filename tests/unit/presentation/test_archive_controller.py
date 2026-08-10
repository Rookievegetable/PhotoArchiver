"""Tests for ArchiveController — preview + execute command construction."""

import pytest

pytest.importorskip("PySide6")

from pathlib import Path
from uuid import uuid4

from photo_archiver.application.dtos import ArchivePlan
from photo_archiver.presentation.controllers import ArchiveController


class _FakeArchiveUseCase:
    """Captures execute() command + preview() args for assertion."""

    def __init__(self, plan: ArchivePlan | None = None) -> None:
        self.last_command = None
        self.preview_calls: list = []
        self._plan = plan or ArchivePlan()

    def preview(self, archive_root, person_ids=(), photo_ids=()):
        self.preview_calls.append((archive_root, person_ids, photo_ids))
        return self._plan

    def execute(self, command):
        self.last_command = command
        from photo_archiver.application.dtos import ArchiveResult
        return ArchiveResult(planned_count=0)


class _FakeExecutor:
    """Captures the submitted task's command without穿透 task private attrs.

    review m-5 fix: stores last_command directly from the task's __init__ arg
    via a peek accessor, so the test doesn't reach into _command.
    """

    def __init__(self) -> None:
        self.last_task = None
        self.last_command = None

    def submit(self, task):
        self.last_task = task
        # ArchivePhotosTask stores the command as _command; we peek once at
        # submit time rather than letting tests穿透 later. This keeps the
        # fragile reach localized to the fake, not spread across assertions.
        self.last_command = getattr(task, "_command", None)
        return task


def test_preview_calls_use_case_preview_with_root_and_person_ids() -> None:
    """preview() forwards archive_root + person_ids to the use case, synchronously."""
    use_case = _FakeArchiveUseCase()
    controller = ArchiveController(
        use_case,  # type: ignore[arg-type]
        _FakeExecutor(),  # type: ignore[arg-type]
    )
    pid = uuid4()
    controller.preview(Path("/archive"), (pid,))
    assert use_case.preview_calls[0] == (str(Path("/archive")), (pid,), ())


def test_execute_builds_command_with_strategy_and_dry_run() -> None:
    """execute() builds ArchivePhotosCommand carrying all flags."""
    use_case = _FakeArchiveUseCase()
    executor = _FakeExecutor()
    controller = ArchiveController(
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
    cmd = executor.last_command
    assert cmd.archive_root == Path("/archive")
    assert cmd.person_ids == (pid,)
    assert cmd.conflict_strategy == "rename"
    assert cmd.dry_run is True


def test_execute_defaults_person_ids_to_empty_tuple() -> None:
    """execute() with no person_ids means 'all persons with approvals'."""
    executor = _FakeExecutor()
    controller = ArchiveController(
        _FakeArchiveUseCase(),  # type: ignore[arg-type]
        executor,  # type: ignore[arg-type]
    )
    controller.execute(Path("/archive"))
    assert executor.last_command.person_ids == ()
