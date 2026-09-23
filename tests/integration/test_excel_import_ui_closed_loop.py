"""P0-3 Excel import UI closed loop (real chain, integration).

Proves the real production path from the user entry to visible state
(people-import redesign stage A: two-stage draft flow):

    real .xlsx file → real "导入人员" QAction → real file-picker boundary
    (modal double) → real ParseImportDraftService → real
    FileRosterTableReader (openpyxl) → real ImportPreviewDialog (modal exec
    double, real construction) → real ConfirmImportService → real
    SQLitePersonRepository → real SQLite → real repository reads → real
    FilterBar person-combo refresh.

Nothing in the core chain is mocked; only the two modal boundaries
(file picker, dialog.exec) are doubled, per the established test policy.
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

FILTER_DIALOG_TITLE = "选择人员文件"


def _write_people_workbook(
    path: Path, rows: list[tuple[str, str, str | None, str | None]] | None = None,
) -> Path:
    """Create a real .xlsx people file (program-generated fixture)."""
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "People"
    worksheet.append(["name", "identity", "department", "note"])
    for row in rows if rows is not None else (
        ("Alice", "A001", "Archive Dept", "Team lead"),
        ("Bob", "B002", None, None),
    ):
        worksheet.append(list(row))
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

    # Stage A modal boundary: the preview dialog constructs for real (parse
    # already ran synchronously) but exec() accepts immediately — the window
    # then confirms synchronously (2 rows ≤ CONFIRM_SYNC_LIMIT).
    class _AutoAcceptDialog(main_window_module.ImportPreviewDialog):
        def exec(self) -> int:
            return 1

    monkeypatch.setattr(
        main_window_module, "ImportPreviewDialog", _AutoAcceptDialog,
    )

    # Trigger the REAL user entry: the Import People toolbar action.
    toolbar = window.findChild(QToolBar, "Main")
    assert toolbar is not None
    import_action = next(a for a in toolbar.actions() if a.text() == "导入人员")
    import_action.trigger()

    # Real persistence proof via the repository protocol (not ad-hoc SQL):
    # the synchronous confirm must land both Excel rows in SQLite.
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

    # Poll manually (same pumping as waitUntil) with a rich failure dump —
    # LIMIT-005's intermittent stall needs on-failure evidence to diagnose.
    import time

    deadline = time.monotonic() + 20
    while person_combo.itemText(0) != "Alice" or person_combo.itemText(1) != "Bob":
        if time.monotonic() > deadline:
            pytest.fail(
                "person combo never refreshed after import: "
                f"people={[p.name for p in people_repository.list_all()]} "
                f"combo={[person_combo.itemText(i) for i in range(person_combo.count())]} "
                f"status={window._status_label.text()!r}"
            )
        qtbot.wait(50)

    assert person_combo.placeholderText() == "全部人员"
    assert person_combo.currentIndex() == -1  # unselected = no constraint
    assert person_combo.count() == 2  # Alice + Bob — real entries only


def test_second_import_refreshes_the_people_page_without_restart(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """Stage-B review #4: the people page must show every batch right away.

    The page was already open when the second file was imported, so nothing but
    the window's refresh path can bring the new roster in — the regression was
    a page that stayed on the first batch until the application restarted.
    """
    first = _write_people_workbook(tmp_path / "first.xlsx")
    second = _write_people_workbook(
        tmp_path / "second.xlsx", rows=[("Carol", "C003", None, None)],
    )
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'people_page.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    window = MainWindow(context)
    qtbot.addWidget(window)

    window._nav_list.setCurrentRow(2)  # 打开「人员与分组」页
    page = window._people_admin_page
    assert page._table.rowCount() == 0

    pending = [first, second]
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (pending.pop(0), FILTER_DIALOG_TITLE),
    )

    class _AutoAcceptDialog(main_window_module.ImportPreviewDialog):
        def exec(self) -> int:
            return 1

    monkeypatch.setattr(main_window_module, "ImportPreviewDialog", _AutoAcceptDialog)

    toolbar = window.findChild(QToolBar, "Main")
    assert toolbar is not None
    import_action = next(a for a in toolbar.actions() if a.text() == "导入人员")

    import_action.trigger()
    qtbot.waitUntil(lambda: page._table.rowCount() == 2, timeout=15000)
    assert [page._table.item(row, 1).text() for row in range(2)] == ["Alice", "Bob"]

    import_action.trigger()  # 第二批：页面必须当场显示 3 人
    qtbot.waitUntil(lambda: page._table.rowCount() == 3, timeout=15000)
    assert [page._table.item(row, 1).text() for row in range(3)] == [
        "Alice", "Bob", "Carol",
    ]
    assert page._table.item(2, 5).text() == "second.xlsx"  # 来源批次列同步
