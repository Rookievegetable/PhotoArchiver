"""照片库「指定人员归档」对话框（追加轮 29，Owner）.

选择只有单个人脸的未匹配照片后：输入人员名，选择批次（新建 / 并入已导
入批次）→ 已导入批次若有该人名则归到对应人名下，否则新建人员挂靠批次。

范式同既有确认流：预演校验逐张披露 → 显式执行 → 如实回执（允许部分成
功，失败原因逐项列出）。磁盘文件一律不动。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.services.manual_attribution_service import (
    ManualAttributionCommand,
)
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import ROLE_PRIMARY, assign_role

if TYPE_CHECKING:
    from uuid import UUID

    from photo_archiver.application.services.manual_attribution_service import (
        ManualAttributionService,
    )


class ManualAttributionDialog(QDialog):
    """Collect the person name + batch choice and execute the attribution."""

    def __init__(
        self,
        service: "ManualAttributionService",
        photo_ids: tuple["UUID", ...],
        batches,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize with the target photos and the importable batches.

        Args:
            service: 指定人员归档服务（预演校验 + 执行）。
            photo_ids: 选中的照片 id（调用方已过滤非空选区）。
            batches: 可并入的已导入批次摘要（roster.batches，带 id/标签）。
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle(text.MANUAL_ATTRIBUTION_DIALOG_TITLE)
        self.setMinimumWidth(520)
        self._service = service
        self._photo_ids = tuple(photo_ids)
        self._batches = list(batches)
        self._result_message = ""
        self._eligible_count = 0
        self._build_ui()
        self._refresh_preview()
        self._refresh_name_completions()

    def _build_ui(self) -> None:
        """Lay out the preview, person name, batch choice and buttons."""
        layout = QVBoxLayout(self)

        self._preview_label = QLabel(self)
        self._preview_label.setWordWrap(True)
        layout.addWidget(self._preview_label)

        layout.addWidget(QLabel(text.MANUAL_ATTRIBUTION_PERSON_LABEL, self))
        self._name_edit = QLineEdit(self)
        self._name_edit.setPlaceholderText(
            text.MANUAL_ATTRIBUTION_PERSON_PLACEHOLDER,
        )
        self._name_edit.textChanged.connect(self._refresh_buttons)
        # 追加轮 30：并入已导入批次时输入部分姓名自动匹配（关联搜索）——
        # contains 过滤 + 大小写不敏感；匹配项即批次内既有人员（复用口径）。
        self._name_completer = QCompleter([], self)
        self._name_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._name_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._name_edit.setCompleter(self._name_completer)
        layout.addWidget(self._name_edit)

        layout.addWidget(QLabel(text.MANUAL_ATTRIBUTION_BATCH_LABEL, self))
        self._new_batch_radio = QRadioButton(
            text.MANUAL_ATTRIBUTION_NEW_BATCH, self,
        )
        self._new_batch_radio.setChecked(True)
        self._new_batch_radio.toggled.connect(self._refresh_name_completions)
        layout.addWidget(self._new_batch_radio)
        self._new_batch_edit = QLineEdit(self)
        self._new_batch_edit.setPlaceholderText(
            text.MANUAL_ATTRIBUTION_NEW_BATCH_PLACEHOLDER,
        )
        self._new_batch_edit.textChanged.connect(self._refresh_buttons)
        layout.addWidget(self._new_batch_edit)

        self._existing_batch_radio = QRadioButton(
            text.MANUAL_ATTRIBUTION_EXISTING_BATCH, self,
        )
        self._existing_batch_radio.toggled.connect(self._refresh_name_completions)
        layout.addWidget(self._existing_batch_radio)
        self._batch_combo = QComboBox(self)
        self._batch_combo.setMinimumWidth(320)
        for summary in self._batches:
            self._batch_combo.addItem(
                text.import_batch_entry_label(
                    summary.batch.file_name,
                    summary.batch.created_at,
                    summary.batch.status,
                    summary.person_count,
                ),
                summary.batch.id,
            )
        self._batch_combo.setEnabled(False)
        self._batch_combo.currentIndexChanged.connect(self._refresh_name_completions)
        layout.addWidget(self._batch_combo)

        self._warning_label = QLabel(self)
        self._warning_label.setWordWrap(True)
        self._warning_label.setVisible(False)
        layout.addWidget(self._warning_label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self._ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText(text.MANUAL_ATTRIBUTION_EXECUTE_BUTTON)
        assign_role(self._ok, ROLE_PRIMARY)
        cancel = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setDefault(True)
        cancel.setFocus()
        self._buttons.accepted.connect(self._on_confirm)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    # ── 状态 ──────────────────────────────────────────────────────────

    def _refresh_preview(self) -> None:
        """预演校验逐张披露（无副作用）——可归档/拒绝原因。"""
        preview = self._service.preview(self._photo_ids)
        blocked = {
            str(photo_id): reason
            for photo_id, reason in preview.items()
            if reason
        }
        eligible = len(self._photo_ids) - len(blocked)
        self._eligible_count = eligible
        self._preview_label.setText(
            text.MANUAL_ATTRIBUTION_PREVIEW.format(
                total=len(self._photo_ids), eligible=eligible,
            ),
        )
        if blocked:
            reasons = "\n".join(
                f"· {photo_id[:8]}…：{reason}" for photo_id, reason in blocked.items()
            )
            self._warning_label.setText(
                text.MANUAL_ATTRIBUTION_BLOCKED.format(reasons=reasons),
            )
            self._warning_label.setVisible(True)
        else:
            self._warning_label.setVisible(False)
        self._refresh_buttons()

    def _refresh_name_completions(self) -> None:
        """关联搜索数据源（追加轮 30）：并入已导入批次 → 该批次人员名列表；
        新建批次 → 无既有人员（清空补全）。"""
        names: tuple = ()
        if self._existing_batch_radio.isChecked():
            batch_id = self._batch_combo.currentData()
            if batch_id is not None:
                names = self._service.list_batch_person_names(batch_id)
        self._name_completer.setModel(QStringListModel(list(names), self))
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        """确认键启用门：姓名非空 + 批次方式完整 + 至少一张可归档（单脸）。"""
        has_name = bool(self._name_edit.text().strip())
        if self._new_batch_radio.isChecked():
            batch_ready = bool(self._new_batch_edit.text().strip())
        else:
            batch_ready = self._batch_combo.currentData() is not None
        self._new_batch_edit.setEnabled(self._new_batch_radio.isChecked())
        self._batch_combo.setEnabled(self._existing_batch_radio.isChecked())
        self._ok.setEnabled(
            has_name and batch_ready and self._eligible_count > 0,
        )

    def _on_confirm(self) -> None:
        """执行归档（允许部分成功）；回执如实逐项。"""
        person_name = self._name_edit.text().strip()
        if self._new_batch_radio.isChecked():
            command = ManualAttributionCommand(
                photo_ids=self._photo_ids,
                person_name=person_name,
                new_batch_name=self._new_batch_edit.text().strip(),
            )
        else:
            batch_id = self._batch_combo.currentData()
            command = ManualAttributionCommand(
                photo_ids=self._photo_ids,
                person_name=person_name,
                existing_batch_id=batch_id,
            )
        try:
            result = self._service.execute(command)
        except Exception as exc:  # noqa: BLE001 - UI boundary: show, log the detail
            logger.exception("Manual attribution failed")
            QMessageBox.critical(
                self, text.DELETE_FAILED_TITLE,
                f"{text.DELETE_FAILED_TITLE}：{exc}",
            )
            return
        failed = [
            outcome for outcome in result.outcomes if not outcome.ok
        ]
        message = text.MANUAL_ATTRIBUTION_DONE.format(
            assigned=result.assigned,
            total=len(self._photo_ids),
            person=result.person_name,
            batch=result.batch_name,
        )
        if failed:
            reasons = "\n".join(
                f"· {str(outcome.photo_id)[:8]}…：{outcome.reason}"
                for outcome in failed
            )
            message += "\n" + text.MANUAL_ATTRIBUTION_FAILED.format(
                reasons=reasons,
            )
        self._result_message = message
        self.accept()

    def last_message(self) -> str:
        """Return the outcome message for the caller's status bar."""
        return self._result_message
