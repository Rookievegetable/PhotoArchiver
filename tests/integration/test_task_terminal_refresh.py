"""Task terminals refresh real SQLite results under the current UI criteria."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QMessageBox

from photo_archiver.domain import Folder, MatchStatus, Person, Photo, PhotoPath, PhotoSearchCriteria, RecognitionResult
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.presentation.views.photo_list_model import PHOTO_ID_ROLE
from photo_archiver.workers.events import TaskCancelled, TaskCompleted, TaskFailed
from photo_archiver.workers.qt_executor import QtWorkerSignals


@pytest.mark.parametrize("task_name", ["import_people", "scan_and_register_photos", "match_persons", "archive_photos", "export"])
@pytest.mark.parametrize("kind", ["completed", "failed", "cancelled"])
def test_terminal_requeries_persisted_rows_without_losing_current_filter(
    qtbot, make_sqlite_context, monkeypatch, task_name, kind,
):
    context = make_sqlite_context()
    repositories = context.repositories
    person = Person(name="Alice")
    repositories.people.add(person)
    folder = Folder(path=PhotoPath("photos"), total_photos=3)
    repositories.folders.add(folder)
    monkeypatch.setattr(context.photo_list_controller, "load_thumbnail", Mock())
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=0))
    window = MainWindow(context)
    qtbot.addWidget(window)
    runnable = SimpleNamespace(signals=QtWorkerSignals(), replay_pending_terminal=lambda: None)
    assert window._task_coordinator.reserve(task_name) is not None
    window._connect_task_signals(runnable)

    # A changed filter during execution must win over the initial snapshot.
    window._on_filter_changed(PhotoSearchCriteria(match_status=MatchStatus.APPROVED))
    current = PhotoSearchCriteria(person_id=person.id, match_status=MatchStatus.PENDING)
    window._on_filter_changed(current)
    assert window._photo_list_model.rowCount() == 0

    selected = None
    for name, approved in [("partial.jpg", False), ("excluded.jpg", True), ("unmatched.jpg", None)]:
        photo = Photo(path=PhotoPath(f"photos/{name}"), folder_id=folder.id,
                      original_name=name, captured_at=datetime(2024, 1, 1))
        repositories.photos.add(photo)
        if approved is not None:
            result = RecognitionResult(photo_id=photo.id, confidence=0.9, person_id=person.id)
            if approved:
                result.approve()
            repositories.recognition.add(result)
        if name == "partial.jpg":
            selected = photo.id
    assert window._photo_list_model.rowCount() == 0
    event = {
        "completed": TaskCompleted(task_name),
        "failed": TaskFailed(task_name, RuntimeError("after partial persistence")),
        "cancelled": TaskCancelled(task_name),
    }[kind]
    getattr(runnable.signals, kind).emit(event)
    model = window._photo_list_model
    assert [model.data(model.index(row, 0), PHOTO_ID_ROLE) for row in range(model.rowCount())] == [selected]
    assert len(repositories.photos.list_all()) == 3
    assert window._current_criteria is current
    assert not window._task_coordinator.is_busy
    assert not window._cancel_action.isEnabled()
