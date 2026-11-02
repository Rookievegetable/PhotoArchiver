"""照片库「指定人员归档」对话框测试（追加轮 29）.

确认键启用门（姓名+批次方式+批次内容）、命令组装（新建/并入两种方式）、
预演披露标签。服务为录制替身，不触真实库。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from datetime import datetime
from uuid import uuid4

from photo_archiver.application.services.manual_attribution_service import (
    ManualAttributionCommand,
    ManualAttributionResult,
)
from photo_archiver.presentation.views.manual_attribution_dialog import (
    ManualAttributionDialog,
)


class _StubService:
    def __init__(self) -> None:
        self.commands: list[ManualAttributionCommand] = []
        self._preview: dict = {}
        self.batch_names: tuple[str, ...] = ()

    def set_preview(self, preview: dict) -> None:
        self._preview = preview

    def preview(self, photo_ids):
        return {photo_id: self._preview.get(photo_id, "") for photo_id in photo_ids}

    def list_batch_person_names(self, _batch_id):
        return self.batch_names

    def execute(self, command):
        self.commands.append(command)
        return ManualAttributionResult(
            assigned=len(command.photo_ids), outcomes=(),
            person_id=uuid4(), person_name=command.person_name,
            batch_id=uuid4(), batch_name=command.new_batch_name or "批次",
        )


class _BatchSummary:
    """roster.batches 摘要形状的最小替身。"""

    def __init__(self, batch_id) -> None:
        from photo_archiver.domain.entities.import_batch import ImportBatch

        self.batch = ImportBatch(
            file_name="名单A.txt", file_hash="h", source_type="txt",
            status="confirmed", created_at=datetime(2026, 11, 1, 9, 0),
        )
        self.batch.id = batch_id
        self.person_count = 3


def _dialog(qtbot, service):
    from PySide6.QtWidgets import QDialogButtonBox

    dialog = ManualAttributionDialog(
        service, (uuid4(),), [_BatchSummary(uuid4())],
    )
    qtbot.addWidget(dialog)
    ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    return dialog, ok


def test_ok_gated_on_name_and_batch_choice(qtbot) -> None:
    service = _StubService()
    dialog, ok = _dialog(qtbot, service)

    assert not ok.isEnabled()  # 姓名未填

    dialog._name_edit.setText("王小明")
    assert not ok.isEnabled()  # 新建批次名未填
    dialog._new_batch_edit.setText("春游")
    assert ok.isEnabled()

    dialog._existing_batch_radio.setChecked(True)
    assert ok.isEnabled()  # 已导入批次默认选中一项
    dialog._name_edit.clear()
    assert not ok.isEnabled()  # 姓名清空 → 禁用


def test_confirm_builds_command_by_batch_mode(qtbot) -> None:
    service = _StubService()
    dialog, ok = _dialog(qtbot, service)
    dialog._name_edit.setText("王小明")

    dialog._new_batch_edit.setText("春游批次")
    dialog._on_confirm()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert service.commands[-1].new_batch_name == "春游批次"
    assert service.commands[-1].existing_batch_id is None

    dialog2, ok2 = _dialog(qtbot, service)
    dialog2._name_edit.setText("张三")
    dialog2._existing_batch_radio.setChecked(True)
    batch_id = dialog2._batch_combo.currentData()
    ok2.click()
    assert service.commands[-1].existing_batch_id == batch_id
    assert service.commands[-1].new_batch_name is None


def test_preview_discloses_blocked_photos(qtbot) -> None:
    service = _StubService()
    blocked_id = uuid4()
    service.set_preview({blocked_id: "照片包含 2 张人脸——只支持单人脸照片的指定归档"})
    # 预演在构造期执行一次（选区在打开时已固定）——先设预演数据再构造。
    from PySide6.QtWidgets import QDialogButtonBox

    dialog = ManualAttributionDialog(service, (blocked_id,), [_BatchSummary(uuid4())])
    qtbot.addWidget(dialog)
    _ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)

    assert "0 张可指定归档" in dialog._preview_label.text()
    assert "2 张人脸" in dialog._warning_label.text()
    assert dialog._warning_label.isVisibleTo(dialog)


def test_ok_disabled_when_nothing_eligible(qtbot) -> None:
    """追加轮 30：无一张可归档（全部非单脸/已归属）→ 确认键禁用（硬前提）。"""
    service = _StubService()
    single_id = uuid4()
    service.set_preview({single_id: "照片已有人员归属"})
    from PySide6.QtWidgets import QDialogButtonBox

    dialog = ManualAttributionDialog(service, (single_id,), [_BatchSummary(uuid4())])
    qtbot.addWidget(dialog)
    ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)

    dialog._name_edit.setText("王小明")
    dialog._new_batch_edit.setText("春游")
    assert dialog._eligible_count == 0
    assert not ok.isEnabled()  # 姓名/批次齐备但零可归档 → 仍禁用


def test_name_completer_searches_selected_batch(qtbot) -> None:
    """追加轮 30：并入已导入批次时姓名输入关联搜索——批次人员进补全模型，
    新建批次模式清空。"""
    service = _StubService()
    service.batch_names = ("1曹徽文", "2曹紫夏", "3贾偌涵")
    from PySide6.QtWidgets import QDialogButtonBox

    dialog = ManualAttributionDialog(service, (uuid4(),), [_BatchSummary(uuid4())])
    qtbot.addWidget(dialog)
    _ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)

    # 默认新建批次模式 → 无补全
    model = dialog._name_completer.model()
    assert model is not None and model.rowCount() == 0

    # 切到并入已导入批次 → 批次人员进入补全模型（contains 过滤由 QCompleter 承担）
    dialog._existing_batch_radio.setChecked(True)
    model = dialog._name_completer.model()
    names = [model.data(model.index(i, 0)) for i in range(model.rowCount())]
    assert names == ["1曹徽文", "2曹紫夏", "3贾偌涵"]

    # 切回新建批次 → 清空
    dialog._new_batch_radio.setChecked(True)
    assert dialog._name_completer.model().rowCount() == 0
