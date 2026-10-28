"""Person deletion dialog — Phase E E-4（ADR-034 D2/D3 确认流）.

交互式人员删除：下拉选择人员 → 实时预览级联计数（嵌入将删、识别归属置空、
**照片与磁盘文件全保留**）→ 显式确认后交由 ``DeletePersonUseCase.execute``。
视图持 Application 的读取服务与 UseCase Protocol（Presentation → Application
允许，DEP-010）；不触碰仓储与基础设施。
"""

from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.commands.deletion import DeletePersonCommand
from photo_archiver.application.services import ListPersonsService
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.ui_text import (
    PERSON_DELETE_BUTTON,
    PERSON_DELETE_CONFIRM,
    PERSON_DELETE_DIALOG_TITLE,
    PERSON_DELETE_EMPTY,
    PERSON_DELETE_SELECTOR_LABEL,
)
from photo_archiver.presentation.visual_style import ROLE_DANGER, assign_role

if TYPE_CHECKING:
    from uuid import UUID

    from photo_archiver.application.dtos import PersonDeletionPreview
    from photo_archiver.application.use_cases import DeletePersonUseCase
    from photo_archiver.domain import Person


class PersonDeletionDialog(QDialog):
    """Select a person, preview the deletion cascade, confirm removal."""

    def __init__(
        self,
        list_persons: ListPersonsService,
        delete_person: "DeletePersonUseCase",
        parent: QWidget | None = None,
        preselect_id: "UUID | None" = None,
    ) -> None:
        """Initialize the dialog with the catalog reader and the deletion use case.

        Args:
            list_persons: Read-only person catalog source (filter axis reuse).
            delete_person: The deletion use case whose ``preview`` drives the
                live cascade counters and whose ``execute`` runs on confirm.
            parent: Optional parent widget.
            preselect_id: Optional person to select on open (stage B lets the
                people page open this dialog for an already-chosen row).
        """
        super().__init__(parent)
        self.setWindowTitle(PERSON_DELETE_DIALOG_TITLE)
        self.setMinimumWidth(440)
        self._list_persons = list_persons
        self._delete_person = delete_person
        self._persons: list[Person] = []
        self._build_ui()
        self._reload_persons()
        self._select_person(preselect_id)

    def _select_person(self, person_id: "UUID | None") -> None:
        """Select ``person_id`` when present (no-op otherwise).

        The combo stores the raw ``UUID`` as item data; matching the stringified
        form keeps the lookup independent of Qt's object comparison inside a
        ``QVariant`` and picks the row the page asked for (stage-B review #3).
        """
        if person_id is None:
            return
        target = str(person_id)
        for index in range(self._combo.count()):
            if str(self._combo.itemData(index)) == target:
                self._combo.setCurrentIndex(index)
                return

    def showEvent(self, event) -> None:  # noqa: ANN001  # Qt signature
        """Focus the selector on open so the preselected person is actable.

        Stage-B review #3: entering the confirm dialog must not ask for a
        second selection — the chosen person is already selected *and* focused
        (the default button stays 「取消」, so a stray Enter still cancels).
        """
        super().showEvent(event)
        self._combo.setFocus()

    def _build_ui(self) -> None:
        """Lay out the selector label, person combo, preview, and buttons."""
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(PERSON_DELETE_SELECTOR_LABEL, self))
        self._combo = QComboBox(self)
        self._combo.currentIndexChanged.connect(self._on_selection_changed)
        layout.addWidget(self._combo)

        self._preview_label = QLabel(self)
        self._preview_label.setWordWrap(True)
        layout.addWidget(self._preview_label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        ok.setText(PERSON_DELETE_BUTTON)
        # Batch 6/7: destructive confirm — danger styling and cancel owns the
        # default focus, a stray Enter must never delete a person.
        assign_role(ok, ROLE_DANGER)
        cancel.setDefault(True)
        cancel.setFocus()
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _reload_persons(self) -> None:
        """Populate the combo from the catalog; disable when empty."""
        self._persons = self._list_persons.execute()
        self._combo.blockSignals(True)
        self._combo.clear()
        for person in self._persons:
            label = person.name
            if person.department:
                label = f"{person.name}（{person.department}）"
            self._combo.addItem(label, person.id)
        self._combo.blockSignals(False)
        if not self._persons:
            self._preview_label.setText(PERSON_DELETE_EMPTY)
            self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return
        self._on_selection_changed(self._combo.currentIndex())

    def _on_selection_changed(self, index: int) -> None:
        """Refresh the cascade preview for the person under ``index``."""
        person_id = self._combo.itemData(index)
        if person_id is None:
            self._preview_label.clear()
            return
        preview: PersonDeletionPreview = self._delete_person.preview([person_id])
        self._preview_label.setText(self._preview_text(person_id, preview))

    def _preview_text(self, person_id: "UUID | None", preview: "PersonDeletionPreview") -> str:
        """Format the live preview; fall back to the name lookup for the title."""
        name = self._combo.currentText() or str(person_id)
        return PERSON_DELETE_CONFIRM.format(
            name=name,
            assignment_count=preview.assignment_count,
            sample_count=preview.sample_count,
            embedding_count=preview.embedding_count,
            recognition_count=preview.recognition_count,
        )

    def selected_person_id(self) -> "UUID | None":
        """Return the currently selected person id, or ``None`` when empty."""
        return self._combo.currentData()

    def selected_person_name(self) -> str:
        """Return the display label of the currently selected person."""
        return self._combo.currentText()

    def result_preview(self) -> "PersonDeletionPreview | None":
        """Return the last preview shown, or ``None`` when no person selected."""
        person_id = self.selected_person_id()
        if person_id is None:
            return None
        return self._delete_person.preview([person_id])


class MultiPersonDeletionDialog(QDialog):
    """P11（D5-A 最小版）：多选人员的批量删除确认流.

    「预览 → 明确二次确认 → 事务执行」，与 ``PersonDeletionDialog``（单人）
    同一 ``DeletePersonUseCase``：``preview`` 产级联计数，``execute`` 在确认后
    单事务删除（ADR-034：删除必经确认流）。照片与磁盘文件全保留（D2）。
    视图只持 Application 服务（DEP-010）。
    """

    def __init__(
        self,
        people: "list[tuple[UUID | None, str]]",
        delete_person: "DeletePersonUseCase",
        parent: QWidget | None = None,
    ) -> None:
        """Build the preview over the selected people and wire the confirm flow.

        Args:
            people: ``(person_id, name)`` pairs behind the page's multi-selection.
            delete_person: The deletion use case (preview + transactional execute).
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self.setWindowTitle(text.PEOPLE_PAGE_MULTI_DELETE_TITLE)
        self.setMinimumWidth(520)
        self._delete_person = delete_person
        self._person_ids = tuple(pid for pid, _name in people if pid is not None)
        self._result_message = ""
        self._build_ui()
        self._reload_preview(people)

    def _build_ui(self) -> None:
        """Lay out the name list, impact preview and danger confirm buttons."""
        layout = QVBoxLayout(self)

        self._people_list = QListWidget(self)
        self._people_list.setMaximumHeight(160)
        layout.addWidget(self._people_list)

        self._impact_label = QLabel(self)
        self._impact_label.setWordWrap(True)
        layout.addWidget(self._impact_label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        ok.setText(text.PEOPLE_PAGE_MULTI_DELETE_BUTTON)
        # 破坏性确认：danger 样式 + 取消持有默认焦点（误触 Enter 不得删除）。
        assign_role(ok, ROLE_DANGER)
        cancel.setDefault(True)
        cancel.setFocus()
        self._buttons.accepted.connect(self._on_confirm)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _reload_preview(self, people: "list[tuple[UUID | None, str]]") -> None:
        """Fill the name list and the cascade preview (side-effect free)."""
        for _pid, name in people:
            self._people_list.addItem(name)
        preview = self._delete_person.preview(self._person_ids)
        message = text.PEOPLE_PAGE_MULTI_DELETE_IMPACT.format(
            person_count=preview.person_count,
            names="、".join(name for _pid, name in people),
            assignment_count=preview.assignment_count,
            sample_count=preview.sample_count,
            embedding_count=preview.embedding_count,
            recognition_count=preview.recognition_count,
        )
        if preview.missing_count:
            message += "\n" + text.PEOPLE_PAGE_MULTI_DELETE_MISSING.format(
                missing_count=preview.missing_count,
            )
        self._impact_label.setText(message)

    def _on_confirm(self) -> None:
        """Execute inside the service's single transaction; report honestly."""
        try:
            result = self._delete_person.execute(
                DeletePersonCommand(person_ids=self._person_ids),
            )
        except Exception as exc:  # noqa: BLE001 - UI boundary: show, log the detail
            logger.exception("Multi-person deletion failed")
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self, text.PEOPLE_PAGE_DELETE_FAILED_TITLE,
                text.PEOPLE_PAGE_DELETE_FAILED.format(detail=exc),
            )
            return
        logger.info(
            "Multi-person deletion removed {} people (assignment_cascade={} "
            "sample_cascade={} embedding_cascade={} recognition_orphaned={})",
            result.removed, result.assignment_cascade, result.sample_cascade,
            result.embedding_cascade, result.recognition_orphaned,
        )
        self._result_message = text.PEOPLE_PAGE_MULTI_DELETE_DONE.format(
            removed=result.removed,
            assignment_cascade=result.assignment_cascade,
            sample_cascade=result.sample_cascade,
            embedding_cascade=result.embedding_cascade,
            recognition_orphaned=result.recognition_orphaned,
        )
        self.accept()

    def last_message(self) -> str:
        """Return the outcome message for the caller's status bar."""
        return self._result_message
