"""Batch 6 safety expression: archive scope honesty, dry-run default, danger confirms.

The archive preview must state its scope (selected N vs all approved), show
where sample files will land, default to dry-run (owner decision) and label
the confirm button with what it actually starts. The missing-root flow must
lead to settings, not just an error. Destructive confirmations keep default
focus on cancel and honestly state that the UI offers no undo.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDialogButtonBox, QLabel

from photo_archiver.application.dtos import ArchivePlan, ArchivePlanItem
from photo_archiver.domain import ArchivePath
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views import main_window as main_window_module
from photo_archiver.presentation.views.archive_preview_dialog import (
    ArchivePreviewDialog,
)
from photo_archiver.presentation.views.photo_deletion_confirm_dialog import (
    PhotoDeletionConfirmDialog,
)


def _plan(count: int) -> ArchivePlan:
    items = tuple(
        ArchivePlanItem(
            photo_id=uuid4(),
            source_path=Path(f"photos/p{i}.jpg"),
            target_path=ArchivePath(
                archive_root=str(Path("D:/archive")),
                person_name="Alice",
                event_or_date="2024-05-01",
                original_name=f"p{i}.jpg",
            ),
            person_id=uuid4(),
            person_name="Alice",
        )
        for i in range(count)
    )
    return ArchivePlan(items=items, skipped_count=1)


def _preview_dto(photo_count=2, recognition_count=3, archive_count=1, missing_count=0):
    return Mock(
        photo_count=photo_count,
        recognition_count=recognition_count,
        archive_count=archive_count,
        missing_count=missing_count,
    )


# ── Archive preview (scope, samples, dry-run default, semantic button) ──────


def test_scope_row_states_selection_vs_all(qtbot) -> None:
    selected = ArchivePreviewDialog(_plan(1), Path("D:/archive"), selected_count=3)
    qtbot.addWidget(selected)
    all_scope = ArchivePreviewDialog(_plan(1), Path("D:/archive"), selected_count=0)
    qtbot.addWidget(all_scope)

    selected_texts = [w.text() for w in selected.findChildren(QLabel)]
    all_texts = [w.text() for w in all_scope.findChildren(QLabel)]
    assert text.ARCHIVE_SCOPE_SELECTED.format(count=3) in selected_texts
    assert text.ARCHIVE_SCOPE_ALL in all_texts


def test_sample_rows_show_source_to_target_and_truncation_note(qtbot) -> None:
    dialog = ArchivePreviewDialog(_plan(10), Path("D:/archive"))
    qtbot.addWidget(dialog)

    assert dialog._sample_list.count() == 8  # bounded inline sample
    assert dialog._sample_list.item(0).text().startswith("p0.jpg → ")
    notes = [w.text() for w in dialog.findChildren(QLabel)]
    assert text.ARCHIVE_SAMPLE_TRUNCATED.format(shown=8, total=10) in notes

    small = ArchivePreviewDialog(_plan(2), Path("D:/archive"))
    qtbot.addWidget(small)
    assert small._sample_list.count() == 2


def test_dry_run_defaults_on_and_button_labels_switch(qtbot) -> None:
    """Owner decision: dry-run is the default; real write gets an explicit label."""
    dialog = ArchivePreviewDialog(_plan(1), Path("D:/archive"))
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.dry_run is True  # safe default
    assert dialog._accept_button.text() == text.ARCHIVE_DRY_RUN_BUTTON
    assert dialog._accept_button.isDefault()

    dialog._dry_run_check.setChecked(False)  # 正式写入
    assert dialog._accept_button.text() == text.ARCHIVE_EXECUTE_BUTTON
    assert not dialog._accept_button.isDefault()
    cancel = dialog._buttons.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel.isDefault()

    dialog._dry_run_check.setChecked(True)
    assert dialog._accept_button.text() == text.ARCHIVE_DRY_RUN_BUTTON
    assert dialog._accept_button.isDefault()


def test_conflict_strategy_hint_states_consequences(qtbot) -> None:
    dialog = ArchivePreviewDialog(_plan(1), Path("D:/archive"))
    qtbot.addWidget(dialog)

    hint = dialog._strategy_hint
    assert hint.text() == text.ARCHIVE_CONFLICT_HINTS["skip"]
    overwrite_index = dialog._strategy_combo.findData("overwrite")
    dialog._strategy_combo.setCurrentIndex(overwrite_index)
    assert hint.text() == text.ARCHIVE_CONFLICT_HINTS["overwrite"]


# ── Missing archive root leads to settings (Batch 6) ────────────────────────


class _FakeRootBox:
    """QMessageBox double recording label buttons; answer set per test."""

    Icon = SimpleNamespace(Question=object())
    StandardButton = SimpleNamespace(NoButton=object())
    ButtonRole = SimpleNamespace(YesRole="yes", NoRole="no")

    def __init__(self, *args) -> None:
        self._yes_token: object = object()  # handler compares with `is`
        self._answer = self._yes_token  # default: user picks 去设置

    def addButton(self, label, role):  # noqa: ANN001
        return self._yes_token if role == "yes" else object()

    def setDefaultButton(self, button) -> None:  # noqa: ANN001
        pass

    def exec(self) -> int:
        return 0

    def clickedButton(self):  # noqa: ANN001
        return self._answer


def _handler_self(monkeypatch, answer: str, opened: list) -> SimpleNamespace:
    """Bare handler receiver: root missing, settings entry recorded.

    The undecorated method body only needs the root resolver and the settings
    entry — admission is separately covered by the coordination tests.
    """
    self_mock = SimpleNamespace(
        _effective_archive_root=lambda: None,
        _open_settings_dialog=lambda: opened.append(1),
    )
    monkeypatch.setattr(main_window_module, "QMessageBox", _FakeRootBox)
    if answer == "dismiss":
        # User cancels: clickedButton must not be the YesRole token.
        monkeypatch.setattr(
            _FakeRootBox, "clickedButton", lambda self: object(),
        )
    return self_mock


def test_root_missing_prompt_opens_settings_on_confirmation(qtbot, monkeypatch) -> None:
    opened: list = []
    self_mock = _handler_self(monkeypatch, "setup", opened)
    main_window_module.MainWindow._on_archive_clicked.__wrapped__(self_mock)  # type: ignore[attr-defined]
    assert opened == [1]


def test_root_missing_prompt_decline_changes_nothing(qtbot, monkeypatch) -> None:
    opened: list = []
    self_mock = _handler_self(monkeypatch, "dismiss", opened)
    main_window_module.MainWindow._on_archive_clicked.__wrapped__(self_mock)  # type: ignore[attr-defined]
    assert opened == []


# ── Destructive confirmations (Batch 6: cancel default + no-undo honesty) ───


def test_photo_deletion_confirm_defaults_to_cancel_and_states_no_undo(qtbot) -> None:
    dialog = PhotoDeletionConfirmDialog(_preview_dto())
    qtbot.addWidget(dialog)
    dialog.show()

    box = dialog.findChildren(QDialogButtonBox)[0]
    assert box.button(QDialogButtonBox.StandardButton.Cancel).isDefault()
    assert text.DELETE_PHOTOS_IRREVERSIBLE in dialog._confirmation_text()


def test_photo_deletion_missing_note_still_rendered(qtbot) -> None:
    dialog = PhotoDeletionConfirmDialog(_preview_dto(missing_count=4))
    qtbot.addWidget(dialog)
    body = dialog._confirmation_text()
    assert text.DELETE_PHOTOS_MISSING_NOTE.format(missing_count=4) in body
    assert text.DELETE_PHOTOS_IRREVERSIBLE in body
