"""Presentation-layer startup failure guidance tests (Phase B P0-6)."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from photo_archiver.presentation import startup_failure
from photo_archiver.presentation.startup_failure import (
    CORRUPTED_DATABASE_TITLE,
    corrupted_database_guidance,
    show_corrupted_database_dialog,
)


def test_guidance_contains_recovery_information() -> None:
    """Guidance names the database, the backup directory, and concrete steps."""
    database_path = Path(r"D:\data\photo_archiver.db")
    message = corrupted_database_guidance(
        database_path=database_path,
        backup_directory=database_path.parent / "backups",
        issues=["failed to read page 2"],
    )
    assert "文件损坏" in message
    assert "无法继续启动" in message
    assert "不会覆盖、重建或更换" in message
    assert str(database_path) in message
    assert str(database_path.parent / "backups") in message
    assert "photo_archiver_YYYYMMDD_HHMMSS.db" in message
    assert "failed to read page 2" in message


def test_guidance_joins_all_issue_lines() -> None:
    """Every quick_check issue line survives into the technical-details tail."""
    message = corrupted_database_guidance(
        database_path=Path("a.db"),
        backup_directory=Path("backups"),
        issues=["issue-1", "issue-2"],
    )
    assert "issue-1；issue-2" in message


def test_dialog_reuses_existing_qapplication_and_reports_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dialog helper shows the guidance without creating a second QApplication."""
    existing = QApplication.instance() or QApplication([])
    captured: dict[str, str] = {}

    class FakeMessageBox:
        @staticmethod
        def critical(parent: object, title: str, text: str) -> None:
            captured["title"] = title
            captured["text"] = text

    monkeypatch.setattr(startup_failure, "QMessageBox", FakeMessageBox)

    show_corrupted_database_dialog("指引文本")

    assert QApplication.instance() is existing
    assert captured["title"] == CORRUPTED_DATABASE_TITLE
    assert captured["text"] == "指引文本"