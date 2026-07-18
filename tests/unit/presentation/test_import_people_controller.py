"""Tests for ImportPeopleController — command construction + signal wiring."""

import pytest

pytest.importorskip("PySide6")

from pathlib import Path

from photo_archiver.application import ImportPeopleCommand, ImportPeopleUseCase
from photo_archiver.presentation.controllers import ImportPeopleController


class _FakeImportUseCase(ImportPeopleUseCase):
    """Captures the command passed to execute() so the test can assert it."""

    def __init__(self) -> None:
        self.last_command: ImportPeopleCommand | None = None

    def execute(self, command: ImportPeopleCommand):  # type: ignore[override]
        self.last_command = command
        from photo_archiver.application.dtos import ImportPeopleResult
        return ImportPeopleResult(imported_count=0, skipped_count=0, errors=())


class _FakeExecutor:
    """Captures the submitted task so the test can assert wiring without Qt threads."""

    def __init__(self) -> None:
        self.last_task = None

    def submit(self, task):
        self.last_task = task
        return task


def test_import_from_builds_command_with_path_and_header() -> None:
    """import_from() constructs ImportPeopleCommand with the chosen path + header flag."""
    use_case = _FakeImportUseCase()
    executor = _FakeExecutor()
    controller = ImportPeopleController(use_case, executor)  # type: ignore[arg-type]
    controller.import_from(Path("/people.txt"), has_header=True)
    assert executor.last_task is not None
    assert executor.last_task._command.source_path == Path("/people.txt")
    assert executor.last_task._command.has_header is True
    assert executor.last_task._command.sheet_name is None


def test_import_from_forwards_sheet_name() -> None:
    """import_from() forwards sheet_name for Excel sources."""
    use_case = _FakeImportUseCase()
    executor = _FakeExecutor()
    controller = ImportPeopleController(use_case, executor)  # type: ignore[arg-type]
    controller.import_from(Path("/people.xlsx"), sheet_name="Staff")
    assert executor.last_task._command.sheet_name == "Staff"


def test_connect_signals_wires_four_slots() -> None:
    """connect_signals wires started/progress/completed/failed like ScanController."""
    from PySide6.QtCore import QObject, Signal

    class Signals(QObject):
        started = Signal(object)
        progress = Signal(object)
        completed = Signal(object)
        failed = Signal(object)

    class FakeRunnable:
        def __init__(self) -> None:
            self.signals = Signals()

    runnable = FakeRunnable()
    called: list = []
    ImportPeopleController.connect_signals(
        runnable,
        started=lambda e: called.append("s"),
        progress=lambda e: called.append("p"),
        completed=lambda e: called.append("c"),
        failed=lambda e: called.append("f"),
    )
    runnable.signals.progress.emit(None)
    assert called == ["p"]
