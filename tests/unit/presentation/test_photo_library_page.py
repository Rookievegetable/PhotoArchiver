"""Batch 4 photo-library page: three empty states, context bulk bar, detail.

Empty-state discrimination (library-empty vs filtered-empty vs busy), the
selection-count bulk bar that only appears with a selection, and the
read-only detail dialog over already-loaded data. The readiness snapshot is
doubled like in the workspace-state tests; no workers, no repository from
widgets.
"""

import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from photo_archiver.application.dtos.workspace import (
    ModelAvailability, WorkspaceStatus,
)
from photo_archiver.domain import Photo, PhotoPath
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
def library(qtbot, make_sqlite_context, monkeypatch, tmp_path):
    """A shown MainWindow over a mockable readiness snapshot; no workers."""
    context = make_sqlite_context(
        db_name="library_ui.db", model_path=tmp_path / "missing-models",
    )
    state = SimpleNamespace(value=EMPTY)
    query = Mock(side_effect=lambda root: state.value)
    monkeypatch.setattr(context.services.workspace_readiness, "execute", query)
    monkeypatch.setattr(context.worker_executor, "submit", Mock(
        side_effect=AssertionError("Library tests must not launch workers"),
    ))
    monkeypatch.setattr(context.photo_list_controller, "load_thumbnail", Mock())
    root = tmp_path / "archive"
    monkeypatch.setattr(MainWindow, "_effective_archive_root", lambda self: root)
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=0))
    monkeypatch.setattr(QMessageBox, "information", Mock(return_value=0))
    window = MainWindow(context)
    qtbot.addWidget(window)
    window.show()
    window._nav_list.setCurrentRow(1)  # 照片库页
    return SimpleNamespace(window=window, state=state, query=query, root=root)


def test_empty_library_shows_scan_cta(library) -> None:
    window = library.window
    library.state.value = EMPTY
    window._refresh_workspace_state()
    assert window._photo_list_stack.currentIndex() == 1
    assert window._empty_scan_button.text() == text.PHOTO_EMPTY_LIBRARY_ACTION
    assert not window._bulk_archive_button.isVisible()
    assert not window._bulk_delete_button.isVisible()


def test_filtered_empty_shows_clear_cta_not_library_cta(library) -> None:
    """A photo-bearing library with zero results must NOT say "scan"."""
    window = library.window
    library.state.value = READY  # 库中有照片……
    window._refresh_photo_list()  # ……但真实库查询为 0（构造库为空）
    window._refresh_workspace_state()
    # has_photos=True（快照）而结果 0 → 筛选无结果态
    assert window._photo_list_stack.currentIndex() == 2
    assert window._empty_clear_button.text() == text.PHOTO_EMPTY_FILTERED_ACTION


def test_clear_filters_cta_resets_summary(library) -> None:
    window = library.window
    window._filter_bar._status_combo.setCurrentIndex(0)
    window._empty_clear_button.click()
    assert window._filter_bar._summary_label.text() == text.FILTER_SUMMARY_NONE


def test_busy_shows_progress_explanation_state(library) -> None:
    window = library.window
    reservation = window._task_coordinator.reserve("扫描")
    window._on_task_state_changed()
    assert window._photo_list_stack.currentIndex() == 3
    window._task_coordinator.release(reservation)
    window._on_task_state_changed()
    assert window._photo_list_stack.currentIndex() == 1  # 回到空库态


def test_bulk_bar_appears_only_with_selection_and_counts(library) -> None:
    window = library.window
    photo = Photo(path=PhotoPath("photos/a.jpg"), folder_id=None, original_name="a.jpg")
    window._photo_list_model.load_photos([photo])
    assert not window._bulk_archive_button.isVisible()
    assert not window._bulk_delete_button.isVisible()
    selection = window._photo_list.selectionModel()
    selection.select(window._photo_list_model.index(0, 0), selection.SelectionFlag.Select)
    assert window._bulk_archive_button.isVisible()
    assert window._bulk_archive_button.text() == text.BULK_ARCHIVE_BUTTON.format(count=1)
    assert window._bulk_delete_button.text() == text.BULK_DELETE_BUTTON.format(count=1)
    selection.clearSelection()
    assert not window._bulk_archive_button.isVisible()
    assert not window._bulk_delete_button.isVisible()


def test_bulk_bar_disables_during_busy(library) -> None:
    window = library.window
    photo = Photo(path=PhotoPath("photos/a.jpg"), folder_id=None, original_name="a.jpg")
    window._photo_list_model.load_photos([photo])
    selection = window._photo_list.selectionModel()
    selection.select(window._photo_list_model.index(0, 0), selection.SelectionFlag.Select)
    reservation = window._task_coordinator.reserve("扫描")
    window._render_workspace_actions()
    assert not window._bulk_archive_button.isEnabled()
    assert not window._bulk_delete_button.isEnabled()
    window._task_coordinator.release(reservation)
    window._render_workspace_actions()
    assert window._bulk_archive_button.isEnabled()
    assert window._bulk_delete_button.isEnabled()


def test_detail_dialog_opens_for_double_clicked_photo(library, monkeypatch) -> None:
    window = library.window
    photo = Photo(
        path=PhotoPath("photos/a.jpg"), folder_id=None, original_name="a.jpg",
    )
    window._photos_by_id[photo.id] = photo
    window._photo_list_model.load_photos([photo])
    index = window._photo_list_model.index(0, 0)
    exec_mock = Mock(return_value=1)
    monkeypatch.setattr(
        module, "PhotoDetailDialog",
        lambda *args, **kwargs: SimpleNamespace(exec=exec_mock),
    )
    window._on_photo_double_clicked(index)
    exec_mock.assert_called_once()


def test_detail_dialog_shows_count_after_query(library) -> None:
    """The filter-bar count reflects the query size after every refresh."""
    window = library.window
    window._refresh_photo_list()
    assert window._filter_bar._count_label.text() == text.FILTER_RESULT_COUNT.format(count=0)


def test_detail_dialog_degrades_without_data(qtbot) -> None:
    """No badge, no captured time, no thumbnail → explicit fallbacks only."""
    from PySide6.QtWidgets import QLabel

    from photo_archiver.presentation.views.photo_detail_dialog import PhotoDetailDialog

    photo = Photo(path=PhotoPath("photos/x.jpg"), folder_id=None, original_name=None)
    dialog = PhotoDetailDialog(photo, badge=None, thumbnail_path=None)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == text.PHOTO_DETAIL_TITLE
    texts = [widget.text() for widget in dialog.findChildren(QLabel)]
    assert text.PHOTO_DETAIL_CAPTURED_UNKNOWN in texts
    assert text.PHOTO_DETAIL_THUMB_PENDING in texts
    assert text.PHOTO_DETAIL_STATUS.format(badge=text.FILTER_STATUS_UNMATCHED) in texts
    assert text.PHOTO_DETAIL_PATH.format(path=str(photo.path.raw_path)) in texts


# ---- 2026-09-30 选中态优化：选择操作簇 + 多选交互回归 ----
# QTest 纪律（方案 §15）：所有修饰键/拖拽交互走 QTest 标准接口——手工构造
# QMouseEvent 会静默丢失修饰键（运行时探针实证），禁止用于交互断言。


def _seed_photos(library, count: int):
    window = library.window
    photos = [
        Photo(
            path=PhotoPath(f"photos/p{i}.jpg"),
            folder_id=None,
            original_name=f"p{i}.jpg",
        )
        for i in range(count)
    ]
    window._photo_list_model.load_photos(photos)
    return photos


def _photo_rect(window, row: int) -> QRect:
    model = window._photo_list_model
    return window._photo_list.visualRect(model.index(row, 0))


def _wait_laid_out(qtbot, window) -> None:
    model = window._photo_list_model
    qtbot.waitUntil(
        lambda: model.rowCount() > 0
        and window._photo_list.visualRect(model.index(0, 0)).isValid(),
        timeout=5000,
    )


def test_select_all_button_is_permanent_without_selection(library) -> None:
    """§19：「全选」常驻可见可用；0 选区时批量动作/清除选择全部隐藏。"""
    window = library.window
    assert window._select_all_button.text() == text.SELECT_ALL_PHOTOS
    assert window._select_all_button.isVisible()
    assert window._select_all_button.isEnabled()
    assert not window._clear_selection_button.isVisible()
    assert not window._bulk_archive_button.isVisible()
    assert not window._bulk_delete_button.isVisible()


def test_select_all_scopes_to_current_model_rows(library) -> None:
    """§11/§20：selectAll 作用于模型行 = 当前筛选结果，不越过筛选。"""
    window = library.window
    _seed_photos(library, 5)
    window._select_all_button.click()
    assert len(window._photo_list.selectedIndexes()) == 5
    assert window._bulk_archive_button.text() == text.BULK_ARCHIVE_BUTTON.format(count=5)


def test_select_all_on_empty_library_is_noop(library) -> None:
    """§19 补充：0 张照片时点全选——无异常、无选区、批量栏不出现。"""
    window = library.window
    window._select_all_button.click()
    assert window._photo_list.selectedIndexes() == []
    assert not window._bulk_archive_button.isVisible()


def test_clear_selection_hides_bulk_bar(library) -> None:
    """§19：「清除选择」仅在有选区时可见；点击后选区与批量栏一并归零。"""
    window = library.window
    _seed_photos(library, 2)
    selection = window._photo_list.selectionModel()
    selection.select(window._photo_list_model.index(0, 0), selection.SelectionFlag.Select)
    assert window._clear_selection_button.isVisible()
    window._clear_selection_button.click()
    assert window._photo_list.selectedIndexes() == []
    assert not window._clear_selection_button.isVisible()
    assert not window._bulk_archive_button.isVisible()


def test_selection_cluster_disables_during_busy(library) -> None:
    """§19：busy 期间全选/清除选择置灰，disabled 按钮不触发任何槽。"""
    window = library.window
    _seed_photos(library, 1)
    selection = window._photo_list.selectionModel()
    selection.select(window._photo_list_model.index(0, 0), selection.SelectionFlag.Select)
    reservation = window._task_coordinator.reserve("扫描")
    window._render_workspace_actions()
    assert not window._select_all_button.isEnabled()
    assert not window._clear_selection_button.isEnabled()
    window._task_coordinator.release(reservation)
    window._render_workspace_actions()
    assert window._select_all_button.isEnabled()
    assert window._clear_selection_button.isEnabled()


def test_marquee_selection_rect_visibility_is_enabled(library) -> None:
    """§18：框选矩形可见开关已开启（框选能力本身原生存在）。"""
    assert library.window._photo_list.isSelectionRectVisible() is True


def test_model_reload_resets_selection(library) -> None:
    """§20：筛选切换（load_photos → modelReset）清空选区——既有行为钉死；
    新结果集上全选只覆盖新行数。"""
    window = library.window
    _seed_photos(library, 3)
    window._select_all_button.click()
    assert len(window._photo_list.selectedIndexes()) == 3
    _seed_photos(library, 2)
    assert window._photo_list.selectedIndexes() == []
    assert not window._bulk_archive_button.isVisible()
    window._select_all_button.click()
    assert len(window._photo_list.selectedIndexes()) == 2


def test_ctrl_click_multi_select_reaches_bulk_consumers(library, qtbot) -> None:
    """§17/§21：Ctrl 跳选经 QTest 验证；选区消费端拿到完整 id 集合。"""
    window = library.window
    photos = _seed_photos(library, 6)
    _wait_laid_out(qtbot, window)
    viewport = window._photo_list.viewport()
    QTest.mouseClick(
        viewport, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier, _photo_rect(window, 0).center(),
    )
    QTest.mouseClick(
        viewport, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier, _photo_rect(window, 3).center(),
    )
    rows = sorted(index.row() for index in window._photo_list.selectedIndexes())
    assert rows == [0, 3]
    assert set(window._collect_selected_photo_ids()) == {
        photos[0].id, photos[3].id,
    }


def test_shift_click_range_select_via_qtest(library, qtbot) -> None:
    """§17：Shift 范围选择经 QTest 验证。"""
    window = library.window
    _seed_photos(library, 6)
    _wait_laid_out(qtbot, window)
    viewport = window._photo_list.viewport()
    QTest.mouseClick(
        viewport, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier, _photo_rect(window, 0).center(),
    )
    QTest.mouseClick(
        viewport, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier, _photo_rect(window, 2).center(),
    )
    rows = sorted(index.row() for index in window._photo_list.selectedIndexes())
    assert rows == [0, 1, 2]


def test_drag_marquee_click_semantics_on_cell(library, qtbot) -> None:
    """§17：从 cell-0 右下方单元间隙按下、密步进拖过 cell-0、在中心释放。

    Windows 原生平台下 QTest 合成的移动不携带按键，框选扫掠不推进（QtTest
    平台限制，真实用户鼠标拖拽不受影响）——本用例因此钉死的是"该手势序列
    在任何语义下（框选扫掠或 press/release 点击）都必须恰好选中 cell-0、
    邻格不受污染"；真正的框选扫掠行为由 offscreen 子进程探针验证（见下）。
    """
    window = library.window
    _seed_photos(library, 6)
    _wait_laid_out(qtbot, window)
    viewport = window._photo_list.viewport()
    cell = _photo_rect(window, 0)
    start = QPoint(cell.right() + 4, cell.bottom() + 6)
    end = QPoint(cell.center().x(), cell.center().y())
    QTest.mousePress(
        viewport, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier, start,
    )
    steps = 24
    for step in range(1, steps + 1):
        QTest.mouseMove(viewport, QPoint(
            int(start.x() + (end.x() - start.x()) * step / steps),
            int(start.y() + (end.y() - start.y()) * step / steps),
        ))
        qtbot.wait(0)
    QTest.mouseRelease(
        viewport, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier, end,
    )
    rows = sorted(index.row() for index in window._photo_list.selectedIndexes())
    assert rows == [0]


_MARQUEE_PROBE = """\"\"\"Offscreen marquee probe: rubber band visibility + swept selection.

Runs in an isolated subprocess because Windows-native QTest moves carry no
mouse buttons (QCursor.setPos path), so the marquee never advances there;
the offscreen platform synthesizes button-held moves. Config replicates the
photo wall exactly. Hand-built QMouseEvent moves are used for BUTTON-HELD
drag only — no keyboard modifiers involved (the QTest discipline in the
plan bans hand-built events for MODIFIER behavior, which stays on QTest).
\"\"\"
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (
    QAbstractListModel, QEvent, QModelIndex, QPoint, QPointF, QSize, Qt,
)
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QAbstractItemView, QListView

app = QApplication(sys.argv)
assert app.platformName() == "offscreen"


class M(QAbstractListModel):
    def __init__(self, n):
        super().__init__()
        self._n = n

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._n

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return f"item{index.row()}"
        return None


view = QListView()
view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
view.setViewMode(QListView.ViewMode.IconMode)
view.setFlow(QListView.Flow.LeftToRight)
view.setWrapping(True)
view.setResizeMode(QListView.ResizeMode.Adjust)
view.setUniformItemSizes(True)
view.setGridSize(QSize(184, 202))
view.setSpacing(8)
view.setSelectionRectVisible(True)
assert view.isSelectionRectVisible() is True
view.setModel(M(6))
view.resize(600, 700)
view.show()
app.processEvents()


def send(vp, etype, pos, button, buttons):
    global_pos = QPointF(vp.mapToGlobal(QPointF(pos)))
    QApplication.sendEvent(
        vp,
        QMouseEvent(etype, QPointF(pos), global_pos, button, buttons,
                    Qt.KeyboardModifier.NoModifier),
    )


viewport = view.viewport()
cell = view.visualRect(view.model().index(0, 0))
last = view.visualRect(view.model().index(5, 0))
strip_top = last.bottom() + 12
before = viewport.grab().toImage()

# 间隙按下 → 下探到最后一行下方的确定空白带 → 横向扫过（框带底缘在此区域内）
start = QPoint(cell.right() + 4, cell.bottom() + 6)
send(viewport, QEvent.Type.MouseButtonPress, start,
     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
app.processEvents()
strip_entry = QPoint(start.x() + 30, strip_top + 2)
for step in range(1, 25):
    x = start.x() + (strip_entry.x() - start.x()) * step / 24
    y = start.y() + (strip_entry.y() - start.y()) * step / 24
    send(viewport, QEvent.Type.MouseMove, QPoint(int(x), int(y)),
         Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    app.processEvents()
for step in range(1, 13):
    send(viewport, QEvent.Type.MouseMove,
         QPoint(strip_entry.x() + step * 8, strip_entry.y() + step * 2),
         Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    app.processEvents()
during = viewport.grab().toImage()

changed = sum(
    1
    for x in range(strip_entry.x(), strip_entry.x() + 96)
    for y in range(strip_entry.y(), strip_entry.y() + 26)
    if during.pixelColor(x, y) != before.pixelColor(x, y)
)
print(f"BAND_PIXELS={changed}")

# 框带收回到只覆盖 cell-0 → 释放：真实框选扫掠的选区必须恰好是它
end = QPoint(cell.center().x(), cell.center().y())
for step in range(1, 41):
    x = strip_entry.x() + 96 + (end.x() - (strip_entry.x() + 96)) * step / 40
    y = strip_entry.y() + 24 + (end.y() - (strip_entry.y() + 24)) * step / 40
    send(viewport, QEvent.Type.MouseMove, QPoint(int(x), int(y)),
         Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    app.processEvents()
send(viewport, QEvent.Type.MouseButtonRelease, end,
     Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
app.processEvents()
rows = sorted(index.row() for index in view.selectedIndexes())
print(f"SWEPT_ROWS={rows}")
"""


def test_marquee_band_paints_and_sweeps_offscreen(tmp_path) -> None:
    """§17/§18：框选矩形拖拽期间可见 + 真实框选扫掠选中目标（offscreen 子进程）。

    生产布线由进程内 test_marquee_selection_rect_visibility_is_enabled 钉死；
    本用例在受控 Qt 平台上证明该布线产生可见的框选矩形，且框带只覆盖
    cell-0 时扫掠选区恰好是 cell-0（清除并选中语义，不残留邻格）。
    """
    script = tmp_path / "marquee_probe.py"
    script.write_text(_MARQUEE_PROBE, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    pixels = int(result.stdout.split("BAND_PIXELS=")[1].splitlines()[0])
    swept = result.stdout.split("SWEPT_ROWS=")[1].splitlines()[0]
    assert pixels >= 8, f"rubber band not painted: {pixels} changed pixels"
    assert swept == "[0]", f"marquee sweep selected {swept}, expected [0]"