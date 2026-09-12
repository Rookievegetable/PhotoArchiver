"""Photo wall status badges — G-4 (体检 §6 识别/归档状态列缺失).

真实 SQLite + 真实 MainWindow：照片墙每个 cell 经 STATUS_BADGE_ROLE 携带
"识别状态 · 归档" 角标文本（未匹配照片标"未匹配"，有归档记录的追加
"· 已归档"）。
"""

from datetime import datetime

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from photo_archiver.domain import (
    ArchiveStatus,
    Folder,
    MatchStatus,
    Person,
    Photo,
    PhotoPath,
    RecognitionResult,
)
from photo_archiver.domain.entities.archive import ArchiveRecord
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.presentation.views.photo_list_model import STATUS_BADGE_ROLE


def _seed(context, tmp_path):
    repositories = context.repositories
    folder = Folder(path=PhotoPath("photos"), total_photos=2)
    repositories.folders.add(folder)
    approved = Photo(
        path=PhotoPath("photos/approved.jpg"),
        folder_id=folder.id,
        original_name="approved.jpg",
        captured_at=datetime(2024, 1, 1, 8, 0, 0),
    )
    plain = Photo(
        path=PhotoPath("photos/plain.jpg"),
        folder_id=folder.id,
        original_name="plain.jpg",
        captured_at=datetime(2024, 1, 2, 8, 0, 0),
    )
    repositories.photos.add(approved)
    repositories.photos.add(plain)
    person = Person(name="Alice")
    repositories.people.add(person)
    result = RecognitionResult(photo_id=approved.id, confidence=0.9, person_id=person.id)  # type: ignore[arg-type]
    result.approve()
    repositories.recognition.add(result)
    repositories.archive_records.add(
        ArchiveRecord(
            photo_id=approved.id,  # type: ignore[arg-type]
            target_archive_root=str(tmp_path),
            target_person_name="Alice",
            target_event_or_date="2024-01-01",
            target_original_name="approved.jpg",
            status=ArchiveStatus.ARCHIVED,
        )
    )
    return approved, plain


def _badge_for(window, photo) -> str | None:
    for row in range(window._photo_list_model.rowCount()):
        index = window._photo_list_model.index(row, 0)
        if window._photo_list_model.data(index) == photo.original_name:
            return window._photo_list_model.data(index, STATUS_BADGE_ROLE)
    return None


def test_badges_reflect_recognition_and_archive_state(
    qtbot, make_sqlite_context, tmp_path
) -> None:
    context = make_sqlite_context("badges.db", output_root=tmp_path / "out")
    approved, plain = _seed(context, tmp_path)
    window = MainWindow(context)
    qtbot.addWidget(window)

    assert _badge_for(window, approved) == "已通过 · 已归档"
    assert _badge_for(window, plain) == "未匹配"


def test_badges_refresh_after_status_change(
    qtbot, make_sqlite_context, tmp_path
) -> None:
    """审核动作改变识别状态后，角标随下一次刷新更新（待审核 → 已通过）。"""
    context = make_sqlite_context("badges_refresh.db", output_root=tmp_path / "out")
    repositories = context.repositories
    folder = Folder(path=PhotoPath("photos"), total_photos=1)
    repositories.folders.add(folder)
    photo = Photo(
        path=PhotoPath("photos/pending.jpg"),
        folder_id=folder.id,
        original_name="pending.jpg",
        captured_at=datetime(2024, 1, 1, 8, 0, 0),
    )
    repositories.photos.add(photo)
    person = Person(name="Alice")
    repositories.people.add(person)
    result = RecognitionResult(photo_id=photo.id, confidence=0.9, person_id=person.id)  # type: ignore[arg-type]
    repositories.recognition.add(result)

    window = MainWindow(context)
    qtbot.addWidget(window)
    assert _badge_for(window, photo) == "待审核"

    result.approve()
    repositories.recognition.update_status(result.id, MatchStatus.APPROVED)
    window._refresh_photo_list()

    assert _badge_for(window, photo) == "已通过"
