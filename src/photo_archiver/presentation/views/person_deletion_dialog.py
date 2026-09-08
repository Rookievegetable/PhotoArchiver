"""Person deletion dialog — Phase E E-4（ADR-034 D2/D3 确认流）.

交互式人员删除：下拉选择人员 → 实时预览级联计数（嵌入将删、识别归属置空、
**照片与磁盘文件全保留**）→ 显式确认后交由 ``DeletePersonUseCase.execute``。
视图持 Application 的读取服务与 UseCase Protocol（Presentation → Application
允许，DEP-010）；不触碰仓储与基础设施。
"""

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.services import ListPersonsService
from photo_archiver.presentation.ui_text import (
    PERSON_DELETE_BUTTON,
    PERSON_DELETE_CONFIRM,
    PERSON_DELETE_DIALOG_TITLE,
    PERSON_DELETE_EMPTY,
    PERSON_DELETE_SELECTOR_LABEL,
)

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
    ) -> None:
        """Initialize the dialog with the catalog reader and the deletion use case.

        Args:
            list_persons: Read-only person catalog source (filter axis reuse).
            delete_person: The deletion use case whose ``preview`` drives the
                live cascade counters and whose ``execute`` runs on confirm.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle(PERSON_DELETE_DIALOG_TITLE)
        self.setMinimumWidth(440)
        self._list_persons = list_persons
        self._delete_person = delete_person
        self._persons: list[Person] = []
        self._build_ui()
        self._reload_persons()

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
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText(PERSON_DELETE_BUTTON)
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
