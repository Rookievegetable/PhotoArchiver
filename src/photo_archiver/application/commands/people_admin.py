"""People-administration commands (people-import redesign stage B).

Stage B exposes the roster as an editable list: add, edit and reorder. The
commands carry raw user input; validation stays in the ``Person`` entity and
in :class:`~photo_archiver.application.services.manage_people_service.ManagePeopleService`.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AddPersonCommand:
    """Create one person manually (outside the import preview)."""

    name: str
    identity: str | None = None
    department: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class EditPersonCommand:
    """Replace the editable fields of one existing person."""

    person_id: UUID
    name: str
    identity: str | None = None
    department: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ReorderPeopleCommand:
    """Assign the full roster order, position N meaning place N (1-based)."""

    ordered_ids: tuple[UUID, ...]
