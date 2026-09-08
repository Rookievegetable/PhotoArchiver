"""Tests for DetectDuplicatesController disposal orchestration (Phase E E-4, D6).

验证 controller 在报告对话框确认后：预览非空 → 二次确认（monkeypatch 掉模态
QMessageBox）→ 以预览建议删除集执行 DisposeDuplicatesUseCase → 展示完成文案。
只测编排逻辑；对话框/文案渲染由 test_deletion_ui_dialogs.py 覆盖。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from uuid import uuid4

from PySide6.QtWidgets import QMessageBox

from photo_archiver.application.commands import DisposeDuplicatesCommand
from photo_archiver.application.dtos.deletion import (
    DuplicateDisposalGroup,
    DuplicateDisposalPreview,
    DuplicateDisposalResult,
)
from photo_archiver.presentation.controllers import DetectDuplicatesController


class _StubDisposal:
    """Minimal DisposeDuplicatesUseCase recording the executed command."""

    def __init__(self, preview: DuplicateDisposalPreview) -> None:
        self._preview = preview
        self.executed: DisposeDuplicatesCommand | None = None

    def preview(self) -> DuplicateDisposalPreview:
        return self._preview

    def execute(self, command: DisposeDuplicatesCommand) -> DuplicateDisposalResult:
        self.executed = command
        return DuplicateDisposalResult(
            requested=command.photo_ids and len(command.photo_ids) or 0,
            removed=len(command.photo_ids),
            rejected=0,
            groups_affected=1,
        )


def _non_empty_preview() -> DuplicateDisposalPreview:
    """Build a preview with one group (keep + 2 removable)."""
    keep_id = uuid4()
    remove_a, remove_b = uuid4(), uuid4()
    group = DuplicateDisposalGroup(
        content_hash="dup",
        keep_photo_id=keep_id,
        remove_photo_ids=(remove_a, remove_b),
        recognition_count=0,
        archive_count=0,
    )
    return DuplicateDisposalPreview(groups=(group,))


def test_disposal_confirmed_executes_removable_ids(
    monkeypatch,
) -> None:
    """确认「按建议处置」→ 以预览建议删除集执行 UseCase，展示完成文案。"""
    preview = _non_empty_preview()
    disposal = _StubDisposal(preview)
    controller = DetectDuplicatesController(service=object(), disposal=disposal)  # type: ignore[arg-type]
    # controller 无 QWidget parent → self.parent() 返 None → MessageBox 无父窗口（可测）

    info_calls: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QMessageBox, "information",
        lambda *args, **kwargs: info_calls.append(str(args[2])),
    )

    controller._dispose_confirmed()

    assert disposal.executed is not None
    removable = tuple(
        pid for group in preview.groups for pid in group.remove_photo_ids
    )
    assert disposal.executed.photo_ids == removable
    assert any("处置完成" in message for message in info_calls)


def test_disposal_cancelled_does_not_execute(monkeypatch) -> None:
    """二次确认被取消 → 不执行 UseCase，不弹出完成提示。"""
    preview = _non_empty_preview()
    disposal = _StubDisposal(preview)
    controller = DetectDuplicatesController(service=object(), disposal=disposal)  # type: ignore[arg-type]

    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    info_calls: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information",
        lambda *args, **kwargs: info_calls.append(str(args[2])),
    )

    controller._dispose_confirmed()

    assert disposal.executed is None
    assert not info_calls


def test_disposal_no_disposal_wired_is_noop() -> None:
    """未注入 disposal（首版只读路径）时编排 no-op。"""
    controller = DetectDuplicatesController(service=object(), disposal=None)  # type: ignore[arg-type]

    controller._dispose_confirmed()  # 不应抛错，不应有副作用

    assert controller._disposal is None