"""Smoke tests for SettingsDialog construction + cancel/save flow (Step 13)."""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from pathlib import Path

from PySide6.QtWidgets import QDialog

from photo_archiver.application.dtos.settings import UserPreferences
from photo_archiver.application.services import SettingsService
from photo_archiver.infrastructure.persistence import InMemoryUserSettingsStore
from photo_archiver.presentation.controllers import SettingsController
from photo_archiver.presentation.views.settings_dialog import SettingsDialog


def test_settings_dialog_constructs_and_loads_fields(qtbot) -> None:
    """SettingsDialog should populate every field after showEvent fires.

    review M-5 fix: load is deferred from construction to first showEvent so
    construction is cheap and QSettings I/O does not block the constructor.
    Tests must therefore call showEvent (via qtbot.waitExposed or manual show)
    before asserting field values.
    """
    persisted = UserPreferences(
        theme="dark",
        language="zh",
        default_import_path=Path("/imports"),
        default_export_path=Path("/exports"),
        match_threshold=0.55,
        max_workers=8,
    )
    store = InMemoryUserSettingsStore(persisted)
    service = SettingsService(store, None)
    controller = SettingsController(service)
    dialog = SettingsDialog(controller)
    qtbot.addWidget(dialog)
    # Show the dialog so showEvent fires and the persisted values load.
    dialog.show()
    qtbot.waitExposed(dialog)
    assert dialog.windowTitle() == "Settings"
    assert dialog._theme_combo.currentText() == "dark"
    assert dialog._language_combo.currentText() == "zh"
    assert dialog._import_path_edit.text() == str(Path("/imports"))
    assert dialog._export_path_edit.text() == str(Path("/exports"))
    assert dialog._threshold_spin.value() == pytest.approx(0.55)
    assert dialog._workers_spin.value() == 8
    dialog.close()


def test_settings_dialog_cancel_returns_rejected_without_save(qtbot) -> None:
    """Cancel button must reject the dialog without calling the service save."""
    persisted = UserPreferences()
    store = InMemoryUserSettingsStore(persisted)
    service = SettingsService(store, None)
    controller = SettingsController(service)
    dialog = SettingsDialog(controller)
    qtbot.addWidget(dialog)
    # Reject without interacting — the reject slot is wired to the Cancel button.
    dialog.reject()
    assert dialog.result() == QDialog.Rejected
    # Store snapshot should be unchanged.
    assert store.load() == persisted


def test_settings_dialog_collect_preferences_round_trips_fields(qtbot) -> None:
    """_collect_preferences must read every widget value into a fresh UserPreferences.

    Field values are populated via showEvent (review M-5 deferral); this test
    shows the dialog first so load fires, then collects and asserts round-trip.
    """
    persisted = UserPreferences(
        theme="light",
        language="en",
        default_import_path=None,
        default_export_path=None,
        match_threshold=0.4,
        max_workers=4,
    )
    store = InMemoryUserSettingsStore(persisted)
    service = SettingsService(store, None)
    controller = SettingsController(service)
    dialog = SettingsDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    collected = dialog._collect_preferences()
    assert collected == persisted
    dialog.close()
