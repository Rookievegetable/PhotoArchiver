"""Batch 3 navigation, overview CTA and persistent task panel (no workers).

Information-architecture acceptance: five navigation entries, page stack,
trigger-style review/settings rows, data-tools page hosting the maintenance
actions, and a task panel that stays visible on every page.
"""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QToolBar, QToolButton, QMessageBox

from photo_archiver.application.dtos.workspace import (
    ModelAvailability, WorkspaceStatus,
)
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views import main_window as module
from photo_archiver.presentation.views.main_window import MainWindow

READY = WorkspaceStatus(
    has_persons=True, has_photos=True, pending_match_count=3,
    pending_review_count=2, archivable_count=1, archive_root_available=True,
    model_availability=ModelAvailability.AVAILABLE,
)
EMPTY = replace(
    READY, has_persons=False, has_photos=False, pending_match_count=0,
    pending_review_count=0, archivable_count=0, archive_root_available=False,
)


@pytest.fixture
def nav(qtbot, make_sqlite_context, monkeypatch, tmp_path):
    """A shown MainWindow over a mockable readiness snapshot; no workers."""
    context = make_sqlite_context(
        db_name="nav_ui.db", model_path=tmp_path / "missing-models",
    )
    state = SimpleNamespace(value=EMPTY)
    query = Mock(side_effect=lambda root: state.value)
    monkeypatch.setattr(context.services.workspace_readiness, "execute", query)
    monkeypatch.setattr(context.worker_executor, "submit", Mock(
        side_effect=AssertionError("Navigation tests must not launch workers"),
    ))
    monkeypatch.setattr(context.photo_list_controller, "load_thumbnail", Mock())
    root = tmp_path / "archive"
    monkeypatch.setattr(MainWindow, "_effective_archive_root", lambda self: root)
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=0))
    monkeypatch.setattr(QMessageBox, "information", Mock(return_value=0))
    window = MainWindow(context)
    qtbot.addWidget(window)
    window.show()
    return SimpleNamespace(window=window, state=state, query=query, root=root)


def test_main_toolbar_holds_primary_flow_in_order(nav) -> None:
    window = nav.window
    toolbar = window.findChild(QToolBar, "Main")
    assert toolbar is not None
    assert [action.text() for action in toolbar.actions()] == [
        text.ACTION_IMPORT_PEOPLE, text.ACTION_SCAN_FOLDER,
        text.ACTION_RUN_FACE_RECOGNITION, text.ACTION_REVIEW_PENDING,
        text.ACTION_ARCHIVE,
    ]


def test_data_tools_page_holds_maintenance_actions(nav) -> None:
    window = nav.window
    tools = window.findChild(QToolBar, "DataTools")
    assert tools is not None
    labels = {action.text() for action in tools.actions()}
    assert labels == {
        text.ACTION_EXPORT_DATA, text.ACTION_DETECT_DUPLICATES,
        text.ACTION_DELETE_PERSON,
    }
    main = window.findChild(QToolBar, "Main")
    assert main is not None
    assert not labels & {action.text() for action in main.actions()}


@pytest.mark.parametrize("status, expected_label, expected_primary", [
    (EMPTY, text.OVERVIEW_PRIMARY_IMPORT, "import"),
    (replace(EMPTY, has_persons=True), text.OVERVIEW_PRIMARY_SCAN, "scan"),
    (replace(EMPTY, has_photos=True), text.OVERVIEW_PRIMARY_IMPORT, "import"),
    (replace(READY, pending_match_count=0), text.OVERVIEW_PRIMARY_REVIEW, "review"),
    (replace(READY, pending_match_count=0, pending_review_count=0),
     text.OVERVIEW_PRIMARY_ARCHIVE, "archive"),
])
def test_overview_primary_cta_tracks_the_five_states(
    nav, status, expected_label, expected_primary,
) -> None:
    nav.state.value = status
    nav.window._refresh_workspace_state()
    button = nav.window._overview_page._primary_button
    assert button.isVisible()
    assert button.text() == expected_label
    assert nav.window._overview_page._model.primary == expected_primary
    assert button.isEnabled()


def test_overview_cta_routes_through_the_real_import_picker(nav, monkeypatch) -> None:
    picker = Mock(return_value=("", ""))
    monkeypatch.setattr(module.QFileDialog, "getOpenFileName", picker)
    nav.window._overview_page._primary_button.click()
    picker.assert_called_once()
    assert not nav.window._task_coordinator.is_busy


def test_navigation_switches_between_the_three_pages(nav) -> None:
    window = nav.window
    assert window._pages.currentIndex() == 0  # 概览是首页
    window._nav_list.setCurrentRow(1)
    assert window._pages.currentIndex() == 1
    window._nav_list.setCurrentRow(3)
    assert window._pages.currentIndex() == 2
    window._nav_list.setCurrentRow(0)
    assert window._pages.currentIndex() == 0


def test_review_center_nav_opens_dialog_and_snaps_back(nav, monkeypatch) -> None:
    exec_mock = Mock(return_value=1)
    monkeypatch.setattr(
        module, "ReviewDialog", lambda *args: SimpleNamespace(exec=exec_mock),
    )
    window = nav.window
    window._nav_list.setCurrentRow(2)
    exec_mock.assert_called_once()
    assert window._pages.currentIndex() == 0  # 触发式导航不切页
    assert window._nav_list.currentRow() == 0  # 高亮回到当前页


def test_settings_nav_opens_dialog_and_snaps_back(nav, monkeypatch) -> None:
    exec_mock = Mock(return_value=1)
    monkeypatch.setattr(
        module, "SettingsDialog", lambda *args: SimpleNamespace(exec=exec_mock),
    )
    window = nav.window
    window._nav_list.setCurrentRow(4)
    exec_mock.assert_called_once()
    assert window._pages.currentIndex() == 0
    assert window._nav_list.currentRow() == 0
    nav.query.assert_called_with(nav.root)  # 对话框返回后刷新快照


def test_task_panel_stays_visible_on_every_page(nav) -> None:
    window = nav.window
    cancel_button = window.findChild(QToolButton, "CancelTask")
    assert cancel_button is not None
    for row in (0, 1, 3, 0):  # 仅页面行；行 2/4 是触发式导航项（会开模态对话框）
        window._nav_list.setCurrentRow(row)
        assert window._status.isVisible()
        assert window._progress.isVisible()
        assert cancel_button.isVisible()
        assert cancel_button.defaultAction() is window._cancel_action


def test_busy_disables_data_tools_and_overview_cta_then_restores(nav) -> None:
    window = nav.window
    reservation = window._task_coordinator.reserve("扫描")
    window._on_task_state_changed()
    assert all(not action.isEnabled() for action in window._conflicting_actions)
    assert not window._export_action.isEnabled()
    assert window._export_action.toolTip() == text.STATUS_TASK_BUSY.format(label="扫描")
    assert not window._overview_page._primary_button.isEnabled()
    window._task_coordinator.release(reservation)
    window._on_task_state_changed()
    assert window._export_action.isEnabled()
    assert window._overview_page._primary_button.isEnabled()


def test_nav_entries_carry_the_five_labels(nav) -> None:
    window = nav.window
    labels = [window._nav_list.item(row).text() for row in range(window._nav_list.count())]
    assert labels == [
        text.NAV_OVERVIEW, text.NAV_PHOTO_LIBRARY, text.NAV_REVIEW_CENTER,
        text.NAV_DATA_TOOLS, text.NAV_SETTINGS,
    ]

