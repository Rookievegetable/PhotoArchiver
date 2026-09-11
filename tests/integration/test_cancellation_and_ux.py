"""Cancellation wiring + empty-state UX — ADR-036 D7 (Phase F F-3).

体检 N-3：import 任务此前未接 cancelled 信号（取消后 UI 停在 "Cancelling …"）、
导出无取消通道。本套件经真实 MainWindow + 真实 Worker 线程验证：

    import:  QFileDialog 桩 → 真实 _on_import_clicked → 真实 runnable
             （use case 换成阻塞桩以确定性地控制取消时点）
             → _on_cancel_clicked（真实处理器）→ cancelled 终态 → UI 复位
    export:  ExportDialog 桩（同 test_export_ui_closed_loop 边界策略）→
             真实 _on_export_clicked → 阻塞桩 service → 真实取消 →
             UI 复位且无半文件（原子写 + 桩未写盘）

取消粒度为任务边界（LIMIT-002 同型，ADR-036 D7 既定语义）：阻塞桩返回后
WorkerTask 的边界 raise_if_cancelled 才触发 cancelled——这是确定性的，不
依赖竞态时序。
"""

import threading
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from photo_archiver.application.dtos import ImportPeopleResult
from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.presentation.views import main_window as main_window_module
from photo_archiver.presentation.views.main_window import MainWindow

_WAIT_TERMINAL_MS = 15000


class _BlockingImportUseCase:
    """Block inside execute() so the test controls the cancel timing deterministically."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def execute(self, command):
        self.entered.set()
        self.release.wait(timeout=10)
        return ImportPeopleResult(imported_count=0, skipped_count=0, errors=())


def _write_people_txt(path: Path) -> None:
    path.write_text("姓名,工号,部门\n张三,T001,研发部\n", encoding="utf-8")


def test_import_cancel_resets_ui(qtbot, make_sqlite_context, monkeypatch, tmp_path: Path) -> None:
    context = make_sqlite_context("cancel_import.db")
    window = MainWindow(context)
    qtbot.addWidget(window)

    blocking = _BlockingImportUseCase()
    monkeypatch.setattr(window._import_controller, "_use_case", blocking)
    people_txt = _write_people_txt(tmp_path / "people.txt")
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *args, **kwargs: (str(people_txt), "")),
    )

    window._on_import_clicked()
    assert blocking.entered.wait(timeout=5), "worker never reached execute()"

    window._on_cancel_clicked()  # 真实处理器：runnable.cancel + Cancelling 状态
    blocking.release.set()

    qtbot.waitUntil(
        lambda: "已取消" in window._status_label.text(), timeout=_WAIT_TERMINAL_MS
    )
    assert not window._cancel_action.isEnabled()
    assert window._active_runnable is None  # N-9: 终态清零


class _BlockingExportService:
    """Block inside export() — the real ExportTask boundary then raises cancelled."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.output_written: list[str] = []

    def export(self, exporter, output_path, scope, criteria=None):  # noqa: ANN001
        self.entered.set()
        self.release.wait(timeout=10)
        return str(output_path)


def test_export_cancel_resets_ui_and_writes_no_file(
    qtbot, make_sqlite_context, monkeypatch, tmp_path: Path
) -> None:
    context = make_sqlite_context("cancel_export.db")
    window = MainWindow(context)
    qtbot.addWidget(window)

    blocking = _BlockingExportService()
    monkeypatch.setattr(window._export_controller, "_service", blocking)
    output_path = tmp_path / "cancelled_export.csv"

    class _FakeExportDialog:
        def __init__(self, output_path: Path) -> None:
            self._output_path = output_path

        def exec(self) -> int:
            return 1  # Accepted

        @property
        def output_path(self) -> Path:
            return self._output_path

        @property
        def scope(self) -> ExportScope:
            return ExportScope.ALL

        @property
        def format_name(self) -> str:
            return "csv"

    monkeypatch.setattr(
        main_window_module,
        "ExportDialog",
        lambda parent=None, active_criteria=None: _FakeExportDialog(output_path),
    )

    window._on_export_clicked()  # 真实处理器：提交 + cancelled 接线 + Cancel 使能
    assert blocking.entered.wait(timeout=5), "worker never reached export()"

    window._on_cancel_clicked()
    blocking.release.set()

    qtbot.waitUntil(
        lambda: "已取消" in window._status_label.text(), timeout=_WAIT_TERMINAL_MS
    )
    assert not window._cancel_action.isEnabled()
    assert window._export_action.isEnabled()
    assert window._active_runnable is None
    assert not output_path.exists()  # 无半文件：桩未写盘 + 原子写保障


def test_empty_state_placeholder_toggles_with_photo_rows(
    qtbot, make_sqlite_context
) -> None:
    """ADR-036：空库显示行动指引占位，照片注册后回到照片墙页。"""
    from datetime import datetime

    from photo_archiver.domain import Folder, Photo, PhotoPath

    context = make_sqlite_context("empty_state.db")
    window = MainWindow(context)
    qtbot.addWidget(window)
    assert window._photo_list_stack.currentIndex() == 1  # 空态

    folder = Folder(path=PhotoPath("photos"), total_photos=1)
    context.repositories.folders.add(folder)
    context.repositories.photos.add(
        Photo(
            path=PhotoPath("photos/only.jpg"),
            folder_id=folder.id,
            original_name="only.jpg",
            captured_at=datetime(2024, 1, 1, 8, 0, 0),
        )
    )
    window._refresh_photo_list()
    assert window._photo_list_stack.currentIndex() == 0  # 照片墙

    photo_id = context.repositories.photos.list_all()[0].id
    context.repositories.photos.remove([photo_id])
    window._refresh_photo_list()
    assert window._photo_list_stack.currentIndex() == 1  # 删除后回到空态
