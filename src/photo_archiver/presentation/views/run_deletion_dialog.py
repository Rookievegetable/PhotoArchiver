"""按识别运行删除名单/照片的确认对话框（批次删除功能 D1~D7）.

两个入口共用项目既有的确认流范式：**预览 → 级联披露 → 显式知悉勾选 →
事务执行 → 如实回执**。

- **名单侧**：默认「删除该运行指向的人员及其记录」（A3），可切换为
  「仅解除该运行的匹配关系，保留人员」（A1，状态迁移而非删行）。
- **照片侧**：默认保留该运行的聚类代际（B1），可勾选「同时清理该运行的
  聚类代际」（B2——级联带走该代际的身份决策行，先披露）。

硬阻断（D5）：归档记录 / GT 裁定 / 样本库任一非空即禁用执行按钮并说明原因
——这些证据删掉后无法靠重新识别还原。

视图只持 Application 服务（DEP-010）；磁盘文件一律不动（D3）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from loguru import logger
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.commands.deletion import (
    RUN_PEOPLE_MODE_DELETE,
    RUN_PEOPLE_MODE_UNASSIGN,
    DeleteRunPeopleCommand,
    DeleteRunPhotosCommand,
    DeleteRunRecordCommand,
)
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import ROLE_DANGER, assign_role

if TYPE_CHECKING:
    from photo_archiver.application.services.delete_run_people_service import (
        DeleteRunPeopleService,
    )
    from photo_archiver.application.services.delete_run_photos_service import (
        DeleteRunPhotosService,
    )
    from photo_archiver.application.services.delete_run_record_service import (
        DeleteRunRecordService,
    )


class _RunDeletionDialogBase(QDialog):
    """Shared scaffolding: impact label, aware checkbox, danger confirm button."""

    def __init__(self, title: str, run_label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self._result_message = ""
        layout = QVBoxLayout(self)

        self._run_label = QLabel(text.RUN_DELETE_RUN_LABEL.format(run=run_label), self)
        self._run_label.setWordWrap(True)
        layout.addWidget(self._run_label)

    def _finish(self, message: str) -> None:
        """Store the outcome message and close with acceptance."""
        self._result_message = message
        self.accept()

    def last_message(self) -> str:
        """Return the outcome message for the caller's status bar."""
        return self._result_message

    def _report_failure(self, exc: Exception) -> None:
        """Show the failure reason at the UI boundary（不误报成功）。"""
        logger.exception("Run-scoped deletion failed")
        QMessageBox.critical(
            self, text.DELETE_FAILED_TITLE,
            f"{text.DELETE_FAILED_TITLE}：{exc}",
        )


class RunPeopleDeletionDialog(_RunDeletionDialogBase):
    """Select the treatment for one recognition run's people and confirm it."""

    def __init__(
        self,
        delete_run_people: "DeleteRunPeopleService",
        run_id: UUID,
        run_label: str,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the dialog with the target run.

        Args:
            delete_run_people: 运行级名单删除服务（预览 + 执行）。
            run_id: 目标识别运行 id。
            run_label: 运行的可读标签（创建时间 · 状态 · 脸数）。
            parent: Optional parent widget.
        """
        super().__init__(text.RUN_DELETE_PEOPLE_DIALOG_TITLE, run_label, parent)
        self._delete_run_people = delete_run_people
        self._run_id = run_id
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        """Lay out the mode selector, impact preview and aware confirmation."""
        layout = self.layout()
        assert isinstance(layout, QVBoxLayout)  # 基类已装配 QVBoxLayout

        mode_group = QGroupBox(text.RUN_DELETE_PEOPLE_MODE_GROUP, self)
        mode_layout = QVBoxLayout(mode_group)
        self._delete_mode = QRadioButton(
            text.RUN_DELETE_PEOPLE_MODE_DELETE, mode_group,
        )
        self._delete_mode.setChecked(True)
        self._unassign_mode = QRadioButton(
            text.RUN_DELETE_PEOPLE_MODE_UNASSIGN, mode_group,
        )
        self._delete_mode.toggled.connect(lambda _checked: self._refresh())
        self._unassign_mode.toggled.connect(lambda _checked: self._refresh())
        mode_layout.addWidget(self._delete_mode)
        mode_layout.addWidget(self._unassign_mode)
        layout.addWidget(mode_group)

        self._impact_label = QLabel(self)
        self._impact_label.setWordWrap(True)
        layout.addWidget(self._impact_label)

        self._blocked_label = QLabel(self)
        self._blocked_label.setWordWrap(True)
        self._blocked_label.setVisible(False)
        layout.addWidget(self._blocked_label)

        self._aware_checkbox = QCheckBox(text.RUN_DELETE_AWARE_CHECKBOX, self)
        self._aware_checkbox.toggled.connect(self._on_aware_toggled)
        layout.addWidget(self._aware_checkbox)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self._ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText(text.RUN_DELETE_PEOPLE_BUTTON)
        assign_role(self._ok, ROLE_DANGER)
        cancel = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setDefault(True)
        cancel.setFocus()
        self._buttons.accepted.connect(self._on_confirm)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _refresh(self) -> None:
        """Re-render the impact preview for the selected mode."""
        preview = self._delete_run_people.preview(self._run_id)
        if preview.is_empty:
            self._impact_label.setText(text.RUN_DELETE_EMPTY)
            self._blocked_label.setVisible(False)
            self._aware_checkbox.setEnabled(False)
            self._ok.setEnabled(False)
            return
        if self._unassign_mode.isChecked():
            self._impact_label.setText(text.RUN_DELETE_PEOPLE_IMPACT_UNASSIGN.format(
                cluster_count=preview.cluster_count,
            ))
        else:
            self._impact_label.setText(text.RUN_DELETE_PEOPLE_IMPACT_DELETE.format(
                person_count=preview.person_count,
                names="、".join(preview.people_names) or "—",
                assignment_count=preview.assignment_count,
                sample_count=preview.sample_count,
                embedding_count=preview.embedding_count,
                recognition_count=preview.recognition_count,
                archive_count=preview.archive_count,
                ground_truth_count=preview.ground_truth_count,
            ))
        # A1 不删除任何证据——不受硬阻断约束。
        blocked = (
            preview.blocked_reasons if self._delete_mode.isChecked() else ()
        )
        if blocked:
            self._blocked_label.setText(text.RUN_DELETE_BLOCKED.format(
                reasons="\n".join(f"· {reason}" for reason in blocked),
            ))
            self._blocked_label.setVisible(True)
            self._aware_checkbox.setEnabled(False)
            self._ok.setEnabled(False)
            return
        self._blocked_label.setVisible(False)
        self._aware_checkbox.setEnabled(True)
        self._ok.setEnabled(self._aware_checkbox.isChecked())

    def _on_aware_toggled(self, checked: bool) -> None:
        """The confirm button stays disabled until the user explicitly agrees."""
        self._ok.setEnabled(checked)

    def _on_confirm(self) -> None:
        """Execute inside the service's single transaction; report honestly."""
        mode = (
            RUN_PEOPLE_MODE_UNASSIGN if self._unassign_mode.isChecked()
            else RUN_PEOPLE_MODE_DELETE
        )
        try:
            result = self._delete_run_people.execute(
                DeleteRunPeopleCommand(run_id=self._run_id, mode=mode),
            )
        except Exception as exc:  # noqa: BLE001 - UI boundary: show, log the detail
            self._report_failure(exc)
            return
        if mode == RUN_PEOPLE_MODE_UNASSIGN:
            message = text.RUN_DELETE_PEOPLE_UNASSIGN_DONE.format(
                unassigned=result.unassigned,
            )
        else:
            message = text.RUN_DELETE_PEOPLE_DONE.format(
                removed=result.removed,
                assignment_cascade=result.assignment_cascade,
                sample_cascade=result.sample_cascade,
                embedding_cascade=result.embedding_cascade,
                recognition_orphaned=result.recognition_orphaned,
                archive_orphaned=result.archive_orphaned,
            )
        self._finish(message)


class RunRecordDeletionDialog(_RunDeletionDialogBase):
    """Review one recognition run's residual record and confirm removal（功能 C）."""

    def __init__(
        self,
        delete_run_record: "DeleteRunRecordService",
        run_id: UUID,
        run_label: str,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the dialog with the target run.

        Args:
            delete_run_record: 运行记录清理服务（预览 + 执行，追加轮 21）。
            run_id: 目标识别运行 id。
            run_label: 运行的可读标签（创建时间 · 状态 · 脸数）。
            parent: Optional parent widget.
        """
        super().__init__(text.RUN_DELETE_RECORD_DIALOG_TITLE, run_label, parent)
        self._delete_run_record = delete_run_record
        self._run_id = run_id
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        """Lay out the impact preview, blocked label and aware confirmation."""
        layout = self.layout()
        assert isinstance(layout, QVBoxLayout)  # 基类已装配 QVBoxLayout

        self._impact_label = QLabel(self)
        self._impact_label.setWordWrap(True)
        layout.addWidget(self._impact_label)

        self._blocked_label = QLabel(self)
        self._blocked_label.setWordWrap(True)
        self._blocked_label.setVisible(False)
        layout.addWidget(self._blocked_label)

        self._aware_checkbox = QCheckBox(text.RUN_DELETE_AWARE_CHECKBOX, self)
        self._aware_checkbox.toggled.connect(self._on_aware_toggled)
        layout.addWidget(self._aware_checkbox)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self._ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText(text.RUN_DELETE_RECORD_BUTTON)
        assign_role(self._ok, ROLE_DANGER)
        cancel = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setDefault(True)
        cancel.setFocus()
        self._buttons.accepted.connect(self._on_confirm)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _refresh(self) -> None:
        """Re-render the residual-record preview."""
        preview = self._delete_run_record.preview(self._run_id)
        if not preview.run_found:
            self._impact_label.setText(text.RUN_DELETE_EMPTY)
            self._blocked_label.setVisible(False)
            self._aware_checkbox.setEnabled(False)
            self._ok.setEnabled(False)
            return
        self._impact_label.setText(text.RUN_DELETE_RECORD_IMPACT.format(
            generation_count=preview.generation_count,
            cluster_count=preview.cluster_count,
            decision_count=preview.decision_count,
            observation_count=preview.observation_count,
            snapshot_count=preview.snapshot_count,
        ))
        if preview.is_blocked:
            self._blocked_label.setText(text.RUN_DELETE_BLOCKED.format(
                reasons="\n".join(f"· {reason}" for reason in preview.blocked_reasons),
            ))
            self._blocked_label.setVisible(True)
            self._aware_checkbox.setEnabled(False)
            self._ok.setEnabled(False)
            return
        self._blocked_label.setVisible(False)
        self._aware_checkbox.setEnabled(True)
        self._ok.setEnabled(self._aware_checkbox.isChecked())

    def _on_aware_toggled(self, checked: bool) -> None:
        """The confirm button stays disabled until the user explicitly agrees."""
        self._ok.setEnabled(checked)

    def _on_confirm(self) -> None:
        """Execute inside the service's single transaction; report honestly."""
        try:
            result = self._delete_run_record.execute(
                DeleteRunRecordCommand(run_id=self._run_id),
            )
        except Exception as exc:  # noqa: BLE001 - UI boundary: show, log the detail
            self._report_failure(exc)
            return
        self._finish(text.RUN_DELETE_RECORD_DONE.format(
            generations_purged=result.generations_purged,
            decision_cascade=result.decision_cascade,
            observation_cascade=result.observation_cascade,
            snapshot_cascade=result.snapshot_cascade,
        ))


class RunPhotosDeletionDialog(_RunDeletionDialogBase):
    """Review the cascade of one recognition run's photos and confirm removal."""

    def __init__(
        self,
        delete_run_photos: "DeleteRunPhotosService",
        run_id: UUID,
        run_label: str,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the dialog with the target run.

        Args:
            delete_run_photos: 运行级照片删除服务（预览 + 执行）。
            run_id: 目标识别运行 id。
            run_label: 运行的可读标签（创建时间 · 状态 · 脸数）。
            parent: Optional parent widget.
        """
        super().__init__(text.RUN_DELETE_PHOTOS_DIALOG_TITLE, run_label, parent)
        self._delete_run_photos = delete_run_photos
        self._run_id = run_id
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        """Lay out the impact preview, purge option and aware confirmation."""
        layout = self.layout()
        assert isinstance(layout, QVBoxLayout)  # 基类已装配 QVBoxLayout

        self._impact_label = QLabel(self)
        self._impact_label.setWordWrap(True)
        layout.addWidget(self._impact_label)

        self._blocked_label = QLabel(self)
        self._blocked_label.setWordWrap(True)
        self._blocked_label.setVisible(False)
        layout.addWidget(self._blocked_label)

        self._purge_checkbox = QCheckBox(text.RUN_DELETE_PURGE_CHECKBOX, self)
        self._purge_checkbox.toggled.connect(self._on_purge_toggled)
        layout.addWidget(self._purge_checkbox)

        self._purge_warning = QLabel(self)
        self._purge_warning.setWordWrap(True)
        self._purge_warning.setVisible(False)
        layout.addWidget(self._purge_warning)

        self._aware_checkbox = QCheckBox(text.RUN_DELETE_AWARE_CHECKBOX, self)
        self._aware_checkbox.toggled.connect(self._on_aware_toggled)
        layout.addWidget(self._aware_checkbox)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self._ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText(text.RUN_DELETE_PHOTOS_BUTTON)
        assign_role(self._ok, ROLE_DANGER)
        cancel = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setDefault(True)
        cancel.setFocus()
        self._buttons.accepted.connect(self._on_confirm)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _refresh(self) -> None:
        """Re-render the cascade preview."""
        preview = self._delete_run_photos.preview(self._run_id)
        if not preview.run_found:
            self._impact_label.setText(text.RUN_DELETE_EMPTY)
            self._blocked_label.setVisible(False)
            self._aware_checkbox.setEnabled(False)
            self._purge_checkbox.setEnabled(False)
            self._ok.setEnabled(False)
            return
        if preview.is_empty:
            self._impact_label.setText(text.RUN_DELETE_NO_SNAPSHOT)
            self._blocked_label.setVisible(False)
            self._aware_checkbox.setEnabled(False)
            self._purge_checkbox.setEnabled(False)
            self._ok.setEnabled(False)
            return
        self._impact_label.setText(text.RUN_DELETE_PHOTOS_IMPACT.format(
            photo_count=preview.photo_count,
            recognition_count=preview.recognition_count,
            archive_count=preview.archive_count,
            observation_count=preview.observation_count,
            member_count=preview.member_count,
            sample_count=preview.sample_count,
            other_run_snapshot_count=preview.other_run_snapshot_count,
        ))
        self._purge_checkbox.setEnabled(True)
        self._on_purge_toggled(self._purge_checkbox.isChecked())
        if preview.is_blocked:
            self._blocked_label.setText(text.RUN_DELETE_BLOCKED.format(
                reasons="\n".join(f"· {reason}" for reason in preview.blocked_reasons),
            ))
            self._blocked_label.setVisible(True)
            self._aware_checkbox.setEnabled(False)
            self._ok.setEnabled(False)
            return
        self._blocked_label.setVisible(False)
        self._aware_checkbox.setEnabled(True)
        self._ok.setEnabled(self._aware_checkbox.isChecked())

    def _on_purge_toggled(self, checked: bool) -> None:
        """Show the irreversible-warning when the generation cleanup is requested."""
        if not checked:
            self._purge_warning.setVisible(False)
            return
        preview = self._delete_run_photos.preview(self._run_id)
        self._purge_warning.setText(text.RUN_DELETE_PURGE_WARNING.format(
            cluster_count=preview.cluster_count,
            decision_count=preview.decision_count,
        ))
        self._purge_warning.setVisible(True)

    def _on_aware_toggled(self, checked: bool) -> None:
        """The confirm button stays disabled until the user explicitly agrees."""
        self._ok.setEnabled(checked)

    def _on_confirm(self) -> None:
        """Execute inside the service's single transaction; report honestly."""
        try:
            result = self._delete_run_photos.execute(
                DeleteRunPhotosCommand(
                    run_id=self._run_id,
                    purge_cluster_generations=self._purge_checkbox.isChecked(),
                ),
            )
        except Exception as exc:  # noqa: BLE001 - UI boundary: show, log the detail
            self._report_failure(exc)
            return
        message = text.RUN_DELETE_PHOTOS_DONE.format(
            removed=result.removed,
            recognition_cascade=result.recognition_cascade,
            archive_cascade=result.archive_cascade,
            observation_cascade=result.observation_cascade,
            member_cascade=result.member_cascade,
            sample_cascade=result.sample_cascade,
            other_run_snapshot_cascade=result.other_run_snapshot_cascade,
        )
        message += text.RUN_DELETE_PHOTOS_DONE_EXTRA.format(
            unassigned_decisions=result.unassigned_decisions,
            clusters_recounted=result.clusters_recounted,
        )
        if result.generations_purged:
            message += text.RUN_DELETE_PHOTOS_DONE_PURGED.format(
                generations_purged=result.generations_purged,
            )
        self._finish(message)
