"""Batch roster deletion dialogs — 界面优化 §4.3（按批次删除 / 清空全部）.

两个独立入口共用一套"预览 → 明确二次确认 → 事务执行"流程：

- **按批次删除**：批次选择器 + 当前归属人员清单（执行时点解析，合并/
  迁移人员可能归属其他批次）+ 影响摘要 + 可选"同时删除批次记录和导入
  草稿"（默认不勾选，勾选后显示不可恢复警告）。
- **清空所有人员**：全名单展示 + 影响摘要 + 显式知悉勾选（未勾选时
  确认按钮禁用）。

视图只持 Application 服务（DEP-010）；执行结果按实际完成状态如实反馈
（§8.5/§8.6：失败说明对象与原因，不误报全部成功）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.commands.deletion import (
    ClearAllPeopleCommand,
    DeletePeopleByBatchCommand,
)
from photo_archiver.application.dtos.deletion import BatchRosterDeletionResult
from photo_archiver.application.services.manage_people_service import (
    ManagePeopleService,
)
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import ROLE_DANGER, assign_role

if TYPE_CHECKING:
    from uuid import UUID

    from photo_archiver.application.services.delete_person_service import (
        DeletePersonService,
    )


def _result_message(result: BatchRosterDeletionResult, *, batch_name: str) -> str:
    """Format the executed outcome exactly as it happened（§3.3 逐项如实）."""
    if batch_name:
        message = text.BATCH_DELETE_DONE.format(
            batch=batch_name, removed=result.removed,
            assignment_cascade=result.assignment_cascade,
            sample_cascade=result.sample_cascade,
            embedding_cascade=result.embedding_cascade,
            recognition_orphaned=result.recognition_orphaned,
        )
        if result.batch_record_deleted:
            message = text.BATCH_DELETE_DONE_CLEANUP.format(
                batch=batch_name, removed=result.removed,
                assignment_cascade=result.assignment_cascade,
                sample_cascade=result.sample_cascade,
                embedding_cascade=result.embedding_cascade,
                recognition_orphaned=result.recognition_orphaned,
                draft_rows_deleted=result.draft_rows_deleted,
            )
        return message
    return text.CLEAR_ALL_DONE.format(
        removed=result.removed,
        assignment_cascade=result.assignment_cascade,
        sample_cascade=result.sample_cascade,
        embedding_cascade=result.embedding_cascade,
        recognition_orphaned=result.recognition_orphaned,
    )


class BatchPersonDeletionDialog(QDialog):
    """Select an import batch, review the current members, confirm removal."""

    def __init__(
        self,
        manage_people: ManagePeopleService,
        delete_person: "DeletePersonService",
        parent: QWidget | None = None,
        preselect_batch_id: "UUID | None" = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(text.BATCH_DELETE_DIALOG_TITLE)
        self.setMinimumWidth(520)
        self._manage_people = manage_people
        self._delete_person = delete_person
        self._preselect_batch_id = preselect_batch_id
        self._result_message = ""
        self._build_ui()
        self._reload_batches()

    def _build_ui(self) -> None:
        """Lay out the batch selector, member list, impact summary, cleanup."""
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(text.BATCH_DELETE_SELECTOR_LABEL, self))
        self._batch_combo = QComboBox(self)
        self._batch_combo.setMinimumWidth(320)
        self._batch_combo.currentIndexChanged.connect(self._on_batch_selected)
        layout.addWidget(self._batch_combo)

        layout.addWidget(QLabel(text.BATCH_DELETE_MEMBERS_LABEL, self))
        self._members_list = QListWidget(self)
        self._members_list.setMaximumHeight(140)
        layout.addWidget(self._members_list)

        self._impact_label = QLabel(self)
        self._impact_label.setWordWrap(True)
        layout.addWidget(self._impact_label)

        self._cleanup_checkbox = QCheckBox(text.BATCH_DELETE_CLEANUP_CHECKBOX, self)
        self._cleanup_checkbox.toggled.connect(self._on_cleanup_toggled)
        layout.addWidget(self._cleanup_checkbox)
        self._cleanup_warning = QLabel(self)
        self._cleanup_warning.setWordWrap(True)
        self._cleanup_warning.setVisible(False)
        layout.addWidget(self._cleanup_warning)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        ok.setText("删除该批次人员")
        assign_role(ok, ROLE_DANGER)
        cancel.setDefault(True)
        self._buttons.accepted.connect(self._on_confirm)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    # ── 数据 + 渲染 ─────────────────────────────────────────────────────

    def _reload_batches(self) -> None:
        """Populate the batch selector from the roster's batch summaries."""
        roster = self._manage_people.roster()
        self._batch_combo.blockSignals(True)
        self._batch_combo.clear()
        for summary in roster.batches:
            self._batch_combo.addItem(
                f"{summary.batch.file_name}（{summary.person_count} 人）",
                summary.batch.id,
            )
        self._batch_combo.blockSignals(False)
        if self._preselect_batch_id is not None:
            index = self._batch_combo.findData(self._preselect_batch_id)
            if index >= 0:
                self._batch_combo.setCurrentIndex(index)
        self._on_batch_selected(self._batch_combo.currentIndex())

    def _current_batch_id(self) -> "UUID | None":
        return self._batch_combo.currentData()

    def _on_batch_selected(self, _index: int) -> None:
        """Refresh the member list and impact preview for the selected batch."""
        self._members_list.clear()
        self._cleanup_warning.setVisible(False)
        batch_id = self._current_batch_id()
        if batch_id is None:
            self._impact_label.setText(text.BATCH_DELETE_EMPTY)
            self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return
        preview = self._delete_person.preview_batch(batch_id)
        if preview.is_empty:
            self._impact_label.setText(text.BATCH_DELETE_EMPTY)
            self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            self._cleanup_checkbox.setEnabled(True)
            return
        for name in preview.people_names:
            self._members_list.addItem(name)
        self._impact_label.setText(text.BATCH_DELETE_IMPACT.format(
            person_count=preview.person_count,
            names="、".join(preview.people_names),
            assignment_count=preview.assignment_count,
            sample_count=preview.sample_count,
            embedding_count=preview.embedding_count,
            recognition_count=preview.recognition_count,
        ))
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def _on_cleanup_toggled(self, checked: bool) -> None:
        """Show the irreversible-warning when record cleanup is requested."""
        batch_id = self._current_batch_id()
        if not checked or batch_id is None:
            self._cleanup_warning.setVisible(False)
            return
        preview = self._delete_person.preview_batch(batch_id)
        self._cleanup_warning.setText(
            "⚠ " + text.BATCH_DELETE_CLEANUP_WARNING.format(
                draft_row_count=preview.draft_row_count,
            )
        )
        self._cleanup_warning.setVisible(True)

    def _on_confirm(self) -> None:
        """Execute inside the service's single transaction; report honestly."""
        batch_id = self._current_batch_id()
        if batch_id is None:
            return
        batch_name = self._batch_combo.currentText()
        try:
            result = self._delete_person.execute_batch(
                DeletePeopleByBatchCommand(
                    batch_id=batch_id,
                    delete_batch_record=self._cleanup_checkbox.isChecked(),
                ),
            )
        except Exception as exc:  # noqa: BLE001 - UI boundary: show, log the detail
            logger.exception("Batch people deletion failed")
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self, text.DELETE_FAILED_TITLE,
                f"{text.DELETE_FAILED_TITLE}：{exc}",
            )
            return
        self._result_message = _result_message(result, batch_name=batch_name)
        self.accept()

    def last_message(self) -> str:
        """Return the outcome message for the caller's status bar."""
        return self._result_message


class ClearAllPeopleDialog(QDialog):
    """Review the full roster and confirm clearing every person."""

    def __init__(
        self,
        manage_people: ManagePeopleService,
        delete_person: "DeletePersonService",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(text.CLEAR_ALL_DIALOG_TITLE)
        self.setMinimumWidth(520)
        self._manage_people = manage_people
        self._delete_person = delete_person
        self._result_message = ""
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        """Lay out the full roster view, impact summary and aware-confirm."""
        layout = QVBoxLayout(self)

        self._impact_label = QLabel(self)
        self._impact_label.setWordWrap(True)
        layout.addWidget(self._impact_label)

        self._roster_view = QTextEdit(self)
        self._roster_view.setReadOnly(True)
        self._roster_view.setMaximumHeight(180)
        layout.addWidget(self._roster_view)

        self._aware_checkbox = QCheckBox(text.CLEAR_ALL_CONFIRM_CHECKBOX, self)
        self._aware_checkbox.toggled.connect(self._on_aware_toggled)
        layout.addWidget(self._aware_checkbox)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        ok.setText("清空全部人员")
        assign_role(ok, ROLE_DANGER)
        ok.setEnabled(False)
        cancel.setDefault(True)
        self._buttons.accepted.connect(self._on_confirm)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _reload(self) -> None:
        """Fill the roster and impact preview from the service."""
        preview = self._delete_person.preview_clear_all()
        if preview.is_empty:
            self._impact_label.setText(text.PERSON_DELETE_EMPTY)
            self._roster_view.clear()
            self._aware_checkbox.setEnabled(False)
            return
        self._impact_label.setText(text.CLEAR_ALL_IMPACT.format(
            person_count=preview.person_count,
            names="、".join(preview.people_names),
            assignment_count=preview.assignment_count,
            sample_count=preview.sample_count,
            embedding_count=preview.embedding_count,
            recognition_count=preview.recognition_count,
        ))
        self._roster_view.setPlainText("\n".join(
            f"{index}. {name}"
            for index, name in enumerate(preview.people_names, 1)
        ))

    def _on_aware_toggled(self, checked: bool) -> None:
        """The confirm button stays disabled until the user explicitly agrees."""
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(checked)

    def _on_confirm(self) -> None:
        """Execute the clear-all inside the service's single transaction."""
        try:
            result = self._delete_person.execute_clear_all(ClearAllPeopleCommand())
        except Exception as exc:  # noqa: BLE001 - UI boundary: show, log the detail
            logger.exception("Clear-all people failed")
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self, text.DELETE_FAILED_TITLE,
                f"{text.DELETE_FAILED_TITLE}：{exc}",
            )
            return
        self._result_message = _result_message(result, batch_name="")
        self.accept()

    def last_message(self) -> str:
        """Return the outcome message for the caller's status bar."""
        return self._result_message
