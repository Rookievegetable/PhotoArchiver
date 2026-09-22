"""Person add/edit dialog — stage B of the people-import redesign.

A minimal form over the ``Person`` editable fields. The dialog only collects
input; validation stays in the ``Person`` entity and ``ManagePeopleService``,
so a rejected save surfaces the domain message unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import ROLE_PRIMARY, assign_role

if TYPE_CHECKING:
    from photo_archiver.domain import Person


class PersonEditDialog(QDialog):
    """Collect the editable person fields for an add or an edit."""

    def __init__(self, person: Person | None = None, parent: QWidget | None = None) -> None:
        """Build the form; ``person=None`` means "add", otherwise "edit"."""
        super().__init__(parent)
        self.setWindowTitle(
            text.PEOPLE_PAGE_DIALOG_EDIT_TITLE if person is not None
            else text.PEOPLE_PAGE_DIALOG_ADD_TITLE
        )
        self.setMinimumWidth(420)
        self._build_ui(person)

    def _build_ui(self, person: Person | None) -> None:
        """Lay out the form fields and the save/cancel row."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name_edit = QLineEdit(self)
        self._identity_edit = QLineEdit(self)
        self._department_edit = QLineEdit(self)
        self._note_edit = QPlainTextEdit(self)
        self._note_edit.setFixedHeight(64)
        if person is not None:
            self._name_edit.setText(person.name)
            self._identity_edit.setText(person.identity.value if person.identity else "")
            self._department_edit.setText(person.department or "")
            self._note_edit.setPlainText(person.note or "")
        form.addRow(text.PEOPLE_PAGE_NAME_LABEL, self._name_edit)
        form.addRow(text.PEOPLE_PAGE_IDENTITY_LABEL, self._identity_edit)
        form.addRow(text.PEOPLE_PAGE_DEPARTMENT_LABEL, self._department_edit)
        form.addRow(text.PEOPLE_PAGE_NOTE_LABEL, self._note_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        ok.setText(text.PEOPLE_PAGE_SAVE_BUTTON)
        cancel.setText(text.PEOPLE_PAGE_CANCEL_BUTTON)
        assign_role(ok, ROLE_PRIMARY)
        ok.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict[str, str]:
        """Return the raw field values (stripped), keyed by command field name."""
        return {
            "name": self._name_edit.text().strip(),
            "identity": self._identity_edit.text().strip(),
            "department": self._department_edit.text().strip(),
            "note": self._note_edit.toPlainText().strip(),
        }
