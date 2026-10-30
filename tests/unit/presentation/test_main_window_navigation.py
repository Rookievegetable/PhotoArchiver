"""Batch 3 navigation, overview CTA and persistent task panel (no workers).

Information-architecture acceptance: six navigation entries (stage B adds
人员与分组; 2026-10-01 turns the review center into a persistent page),
page stack, settings trigger row, data-tools page hosting the maintenance
actions, and a task panel that stays visible on every page.
"""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QPushButton, QToolBar, QToolButton, QMessageBox

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


def test_main_toolbar_hosts_plugin_actions_only(nav) -> None:
    """Owner 2026-10-30：固定入口栏撤除——四个流程动作不再占顶部工具栏。

    工具栏对象保留为插件挂点（ADR-038 findChild "Main"）；默认零插件时
    工具栏隐藏（界面上完全不出现）。四个固定动作仍存在且可用（入口移入
    各页面：导入→人员与分组页按钮、扫描→照片库页下一步/空态、审核→导航
    审核中心、归档→照片库页下一步/批量归档）。
    """
    window = nav.window
    toolbar = window.findChild(QToolBar, "Main")
    assert toolbar is not None
    assert toolbar.actions() == []
    assert toolbar.isHidden()
    # 四个固定动作仍完整接线：在窗口准入体系内（忙碌置灰集）、可从其入口
    # 触发（各动作的启用态仍随工作区快照/任务态计算，如归档需配置根目录）。
    for action in (
        window._import_action, window._scan_action,
        window._review_action, window._archive_action,
    ):
        assert action in window._conflicting_actions


def test_data_tools_page_holds_maintenance_actions(nav) -> None:
    """维护四入口＝数据工具页操作卡（参考图基线：文字按钮行 → 卡片网格）。

    卡片点击经 ``action.trigger()`` 走原处理器链——卡片文本必须与 QAction
    文本一致，且主工具栏不出现任何维护入口（D1 裁决保持）。
    """
    window = nav.window
    cards = window.findChildren(QPushButton, "ActionCard")
    assert len(cards) == 4
    labels = {card.text() for card in cards}
    assert labels == {
        text.ACTION_EXPORT_DATA, text.ACTION_DETECT_DUPLICATES,
        text.ACTION_REANALYZE_ALL, text.ACTION_DELETE_PERSON,
    }
    main = window.findChild(QToolBar, "Main")
    assert main is not None
    assert not labels & {action.text() for action in main.actions()}


def test_data_tools_card_triggers_its_action(nav, monkeypatch) -> None:
    """卡片点击＝对应 QAction.trigger（处理器链/准入语义不变）。

    导出卡点击走真实 `_on_export_clicked` → ExportDialog（模态）——基类
    QDialog.exec 打桩成立即返回，点击链路完整但不阻塞。
    """
    from PySide6.QtWidgets import QDialog

    window = nav.window
    cards = {card.text(): card for card in window.findChildren(QPushButton, "ActionCard")}
    export_card = cards[text.ACTION_EXPORT_DATA]
    assert export_card.toolTip()  # 描述进 tooltip（卡片面＝图标＋动作名）
    monkeypatch.setattr(
        QDialog, "exec", lambda self: QDialog.DialogCode.Rejected,
    )
    export_card.click()  # 不抛出不阻塞即通过（exec 被桩化）


# 任务书 §3：扫描（登记+特征）不再要求名单——空库主 CTA 指向扫描；
# 无缺特征、无待审、无归档根时走归档链（设置）。
@pytest.mark.parametrize("status, expected_label, expected_primary", [
    (EMPTY, text.OVERVIEW_PRIMARY_SCAN, "scan"),
    (replace(EMPTY, has_persons=True), text.OVERVIEW_PRIMARY_SCAN, "scan"),
    (replace(EMPTY, has_photos=True), text.OVERVIEW_PRIMARY_SETTINGS, "settings"),
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
    # Owner 2026-10-30：概览页 CTA 不再显示（按钮对象保留承载引导态数据）；
    # 文本/模型/启用语义仍逐态跟踪。
    assert not button.isVisible()
    assert button.text() == expected_label
    assert nav.window._overview_page._model.primary == expected_primary
    assert button.isEnabled()


def test_overview_cta_routes_through_the_real_scan_picker(nav, monkeypatch) -> None:
    # 空库主 CTA = 扫描（任务书 §3）——文件夹选择器入口。
    picker = Mock(return_value="")
    monkeypatch.setattr(module.QFileDialog, "getExistingDirectory", picker)
    nav.window._overview_page._primary_button.click()
    picker.assert_called_once()
    assert not nav.window._task_coordinator.is_busy


def test_people_page_import_button_routes_through_the_real_file_picker(
    nav, monkeypatch,
) -> None:
    """Owner 2026-10-30：导入人员入口移入人员与分组页——按钮经
    import_requested → _import_action → 既有文件选择链（准入语义不变）。"""
    picker = Mock(return_value=("", ""))
    monkeypatch.setattr(module.QFileDialog, "getOpenFileName", picker)
    page = nav.window._people_admin_page
    assert page._import_button.text() == text.ACTION_IMPORT_PEOPLE
    page._import_button.click()
    picker.assert_called_once()
    assert not nav.window._task_coordinator.is_busy


def test_navigation_switches_between_the_five_pages(nav) -> None:
    """导航调序（Owner 2026-10-30）：行 1＝人员与分组、行 2＝照片库；
    页面栈索引不变（人员页仍在栈位 2、照片库在栈位 1）。"""
    window = nav.window
    assert window._pages.currentIndex() == 0  # 概览是首页
    window._nav_list.setCurrentRow(1)
    assert window._pages.currentIndex() == 2  # 人员与分组（阶段 B 新页）
    window._nav_list.setCurrentRow(2)
    assert window._pages.currentIndex() == 1  # 照片库
    window._nav_list.setCurrentRow(3)
    assert window._pages.currentIndex() == 3  # 审核中心（2026-10-01 页面化）
    window._nav_list.setCurrentRow(4)
    assert window._pages.currentIndex() == 4  # 数据工具
    window._nav_list.setCurrentRow(0)
    assert window._pages.currentIndex() == 0


def test_review_center_nav_switches_to_persistent_page(nav) -> None:
    """2026-10-01 页面化：审核中心是常驻页面，高亮驻留、进入即刷新队列。"""
    window = nav.window
    refresh = Mock(wraps=window._review_center_page.refresh)
    window._review_center_page.refresh = refresh  # type: ignore[method-assign]
    window._nav_list.setCurrentRow(3)
    assert window._pages.currentIndex() == 3
    assert window._nav_list.currentRow() == 3  # 页面行高亮驻留（不再回弹）
    assert window._review_center_page.isVisible()
    refresh.assert_called_once()


def test_settings_nav_opens_dialog_and_snaps_back(nav, monkeypatch) -> None:
    exec_mock = Mock(return_value=1)
    monkeypatch.setattr(
        module, "SettingsDialog", lambda *args: SimpleNamespace(exec=exec_mock),
    )
    window = nav.window
    window._nav_list.setCurrentRow(5)
    exec_mock.assert_called_once()
    assert window._pages.currentIndex() == 0
    assert window._nav_list.currentRow() == 0
    nav.query.assert_called_with(nav.root)  # 对话框返回后刷新快照


def test_task_panel_stays_visible_on_every_page(nav) -> None:
    window = nav.window
    cancel_button = window.findChild(QToolButton, "CancelTask")
    assert cancel_button is not None
    for row in (0, 1, 2, 3, 4, 0):  # 页面行；行 5（设置）是触发式导航项（会开模态对话框）
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


def test_nav_entries_carry_the_six_labels(nav) -> None:
    window = nav.window
    labels = [window._nav_list.item(row).text() for row in range(window._nav_list.count())]
    # Owner 2026-10-30：照片库/人员与分组位置调换。
    assert labels == [
        text.NAV_OVERVIEW, text.NAV_PEOPLE, text.NAV_PHOTO_LIBRARY,
        text.NAV_REVIEW_CENTER, text.NAV_DATA_TOOLS, text.NAV_SETTINGS,
    ]

