"""N1 大批量人员导入闭环（真实链路，B13/B14 自动化等价物）.

1200 行名单经真实 MainWindow 链路（导入动作 → ImportPeopleController →
worker task → ImportPeopleService 分批（500/500/200 三个原子批）→
DispatchingPersonImportReader → SQLite）落库，验证：

- B13：一次导入 1200 / 跳过 0 / 错误 0，`people` 表 +1200，筛选栏人员轴刷新；
- B14：同一文件二次导入全部按 identity 查重跳过（跨批幂等，0 / 1200）。

仅模态文件对话框为替身（既定策略）；不依赖 InsightFace 模型（LIMIT-001 /
CI Principle 3）。取代桌面清单 B13/B14 的手工环节——人工仅余导入期间
UI 冻结感的观感抽查。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from pathlib import Path

from PySide6.QtWidgets import QToolBar

# Import the app package first so its __init__ finishes initializing before
# MainWindow pulls app.context.ApplicationContext during its own import
# (same ordering note as test_main_window_smoke.py).
from photo_archiver.presentation.views import main_window as main_window_module
from photo_archiver.presentation.views.main_window import MainWindow

ROW_COUNT = 1200  # 跨 500/500/200 三个原子批
_FILTER_DIALOG_TITLE = "选择人员文件"


def _write_people_txt(path: Path) -> Path:
    """Create the 1200-row people list (program-generated fixture)."""
    rows = ["name,identity,department,note"]
    rows += [
        f"批量人员_{i:04d},B{i:05d},批次部,跨批原子验证" for i in range(1, ROW_COUNT + 1)
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def _capture_terminal_events(window: MainWindow, monkeypatch) -> list:
    """Intercept the window's terminal slots (completed + failed) class-wide.

    1200 行全跳的重导会在毫秒级完成——测试对 runnable 信号的迟到订阅会输给
    窗口自身的一次性 ``replay_pending_terminal()``（生产语义：窗口槽必达）。
    在类级包装 ``_on_completed`` / ``_on_failed``，无论终态经 queued 信号
    还是 replay 直发，都必然经过这两个槽——以此捕获事件，杜绝竞速。
    """
    captured: list = []
    original_completed = MainWindow._on_completed
    original_failed = MainWindow._on_failed

    def _completed(self, event) -> None:
        captured.append(event)
        original_completed(self, event)

    def _failed(self, event) -> None:
        captured.append(event)
        original_failed(self, event)

    monkeypatch.setattr(MainWindow, "_on_completed", _completed)
    monkeypatch.setattr(MainWindow, "_on_failed", _failed)
    return captured


def _trigger_import(window: MainWindow, path: Path, monkeypatch) -> list:
    """Trigger the real Import People action with the picker doubled; return
    the captured terminal-event list (caller waits on its length)."""
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (path, _FILTER_DIALOG_TITLE),
    )
    toolbar = window.findChild(QToolBar, "Main")
    assert toolbar is not None
    import_action = next(a for a in toolbar.actions() if a.text() == "导入人员")
    captured = _capture_terminal_events(window, monkeypatch)
    import_action.trigger()
    return captured


def test_bulk_import_1200_rows_persists_refreshes_and_dedupes(
    qtbot, make_sqlite_context, tmp_path: Path, monkeypatch
) -> None:
    """B13/B14：1200 行真实导入 + 二次导入跨批幂等全跳。"""
    people_txt = _write_people_txt(tmp_path / "people_1200.txt")
    context = make_sqlite_context("bulk.db")
    window = MainWindow(context)
    qtbot.addWidget(window)
    people_repository = context.repositories.people

    # ---- 第一次导入：1200 / 0 / 0（跨 500/500/200 三个原子批） ----
    results = _trigger_import(window, people_txt, monkeypatch)
    qtbot.waitUntil(lambda: len(results) >= 1, timeout=60000)
    event = results[0]
    assert event.__class__.__name__ == "TaskCompleted"  # 失败会以 TaskFailed 进同一列表
    qtbot.waitUntil(lambda: len(people_repository.list_all()) == ROW_COUNT, timeout=30000)

    assert len(results) == 1
    import_result = event.result
    assert import_result.imported_count == ROW_COUNT
    assert import_result.skipped_count == 0
    assert list(import_result.errors) == []

    # 抽查批首、批界（500）、批尾（1200）三行真实落库。
    assert people_repository.find_by_identity("B00001") is not None
    assert people_repository.find_by_identity("B00500") is not None
    assert people_repository.find_by_identity("B01200") is not None

    # 真实 UI 刷新：筛选栏人员轴包含导入人员（1200 个真实条目，无占位项）。
    person_combo = window._filter_bar._person_combo
    qtbot.waitUntil(lambda: person_combo.count() == ROW_COUNT, timeout=30000)
    assert person_combo.itemText(0) == "批量人员_0001"
    assert person_combo.itemText(ROW_COUNT - 1) == "批量人员_1200"

    # ---- 第二次导入：B14 跨批幂等——0 导入 / 1200 跳过 / 0 错误 ----
    results = _trigger_import(window, people_txt, monkeypatch)
    qtbot.waitUntil(lambda: len(results) >= 1, timeout=60000)
    event = results[0]

    assert event.__class__.__name__ == "TaskCompleted"  # 失败会以 TaskFailed 进同一列表
    assert len(results) == 1
    dedupe_result = event.result
    assert dedupe_result.imported_count == 0
    assert dedupe_result.skipped_count == ROW_COUNT
    assert list(dedupe_result.errors) == []
    assert len(people_repository.list_all()) == ROW_COUNT  # 库计数不变
