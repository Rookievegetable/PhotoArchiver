"""P0-3 Excel import UI closed loop (real chain, integration).

Proves the real production path from the user entry to visible state:

    real .xlsx file → real "Import People" QAction → real file-picker boundary
    (modal double) → real ImportPeopleController → real worker task → real
    ImportPeopleService → real DispatchingPersonImportReader → real
    ExcelPersonImportReader (openpyxl) → real Person domain mapping → real
    SQLitePersonRepository → real SQLite → real repository reads → real
    FilterBar person-combo refresh.

Nothing in the core chain is mocked; only the modal QFileDialog is doubled,
per the established test policy for modal dialogs.
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")
pytest.importorskip("openpyxl")

from pathlib import Path

from PySide6.QtWidgets import QComboBox, QToolBar

# Import the app package first so its __init__ finishes initializing before
# MainWindow pulls app.context.ApplicationContext during its own import
# (same ordering note as test_main_window_smoke.py).
from photo_archiver.app import bootstrap_application
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.views import main_window as main_window_module
from photo_archiver.presentation.views.main_window import MainWindow

FILTER_DIALOG_TITLE = "Select People File"


def _write_people_workbook(path: Path) -> Path:
    """Create a real .xlsx people file (program-generated fixture)."""
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "People"
    worksheet.append(["name", "identity", "department", "note"])
    worksheet.append(["Alice", "A001", "Archive Dept", "Team lead"])
    worksheet.append(["Bob", "B002", None, None])
    workbook.save(path)
    workbook.close()
    return path


def test_excel_import_from_main_window_persists_and_refreshes_ui(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """Importing a real .xlsx through the real UI writes SQLite and updates the UI."""
    workbook_path = _write_people_workbook(tmp_path / "people.xlsx")
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'import.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    window = MainWindow(context)
    qtbot.addWidget(window)

    # Modal boundary double: the native file picker is the only non-real hop.
    picked: list[str] = []
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (picked.append(args) or workbook_path, FILTER_DIALOG_TITLE),
    )

    # Trigger the REAL user entry: the Import People toolbar action.
    toolbar = window.findChild(QToolBar, "Main")
    assert toolbar is not None
    import_action = next(a for a in toolbar.actions() if a.text() == "Import People")
    import_action.trigger()

    # Real persistence proof via the repository protocol (not ad-hoc SQL):
    # the worker chain must land both Excel rows in SQLite.
    people_repository = context.repositories.people
    qtbot.waitUntil(lambda: len(people_repository.list_all()) == 2, timeout=15000)

    alice = people_repository.find_by_identity("A001")
    assert alice is not None
    assert alice.name == "Alice"
    assert alice.department == "Archive Dept"
    bob = people_repository.find_by_identity("B002")
    assert bob is not None
    assert bob.name == "Bob"

    # Real UI refresh proof: the completed import re-populates the FilterBar
    # person axis with the imported people (MainWindow._on_completed contract).
    person_combo = window._filter_bar._person_combo
    assert isinstance(person_combo, QComboBox)
    qtbot.waitUntil(
        lambda: person_combo.itemText(1) == "Alice" and person_combo.itemText(2) == "Bob",
        timeout=15000,
    )
    assert person_combo.itemText(0) == "All persons"
    assert person_combo.count() == 3
    # The central surface must paint its background: without it, the reflow
    # triggered by this very import leaves ghost pixels on the real desktop.
    assert window.centralWidget().autoFillBackground() is True
