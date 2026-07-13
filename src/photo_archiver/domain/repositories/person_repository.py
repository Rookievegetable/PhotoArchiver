"""Person repository interface."""

from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities import Person
from photo_archiver.domain.value_objects import PersonIdentity


class PersonRepository(Protocol):
    """Define persistence operations for person entities."""

    def add(self, person: Person) -> None:
        """Add a person entity or replace the existing aggregate with the same id."""

    def find_by_id(self, person_id: UUID) -> Person | None:
        """Find a person by its domain identifier."""

    def find_by_identity(self, identity: PersonIdentity) -> Person | None:
        """Find a person by its external identity."""

    def list_all(self) -> list[Person]:
        """Return all known people."""