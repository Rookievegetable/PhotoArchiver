""""未匹配"筛选 UI 全链路 — ADR-036 D6 用户可达性闭环。

真实 MainWindow → FilterBar 选择"未匹配" → criteria_changed →
_on_filter_changed → SearchPhotosService → PhotoRepository.search
（真实 SQLite LEFT JOIN … IS NULL）→ 照片墙只显示无识别结果的照片。
"""

from datetime import datetime

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from photo_archiver.domain import (
    Folder,
    MatchStatus,
    Person,
    Photo,
    PhotoPath,
    RecognitionResult,
)
from photo_archiver.presentation.views.main_window import MainWindow


def test_unmatched_filter_shows_only_photos_without_recognition_results(
    qtbot, make_sqlite_context
) -> None:
    context = make_sqlite_context("unmatched_ui.db")
    repositories = context.repositories

    folder = Folder(path=PhotoPath("photos"), total_photos=2)
    repositories.folders.add(folder)
    matched = Photo(
        path=PhotoPath("photos/matched.jpg"),
        folder_id=folder.id,
        original_name="matched.jpg",
        captured_at=datetime(2024, 1, 1, 8, 0, 0),
    )
    unmatched = Photo(
        path=PhotoPath("photos/unmatched.jpg"),
        folder_id=folder.id,
        original_name="unmatched.jpg",
        captured_at=datetime(2024, 1, 2, 8, 0, 0),
    )
    repositories.photos.add(matched)
    repositories.photos.add(unmatched)

    person = Person(name="Alice")
    repositories.people.add(person)
    repositories.recognition.add(
        RecognitionResult(photo_id=matched.id, confidence=0.9, person_id=person.id)  # type: ignore[arg-type]
    )

    window = MainWindow(context)
    qtbot.addWidget(window)

    # 无筛选：照片墙显示全部两张。
    assert window._photo_list_model.rowCount() == 2

    index = window._filter_bar._status_combo.findData("unmatched")
    assert index >= 0
    window._filter_bar._status_combo.setCurrentIndex(index)

    names = {
        window._photo_list_model.index(row, 0).data() for row in range(window._photo_list_model.rowCount())
    }
    assert names == {"unmatched.jpg"}

    # 切回待审核：只显示有识别结果的照片（AND 语义与哨兵互斥）。
    pending_index = window._filter_bar._status_combo.findData(MatchStatus.PENDING.value)
    window._filter_bar._status_combo.setCurrentIndex(pending_index)
    names = {
        window._photo_list_model.index(row, 0).data() for row in range(window._photo_list_model.rowCount())
    }
    assert names == {"matched.jpg"}
