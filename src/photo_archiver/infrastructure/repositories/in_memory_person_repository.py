"""In-memory implementation of the person repository interface."""

from uuid import UUID

from photo_archiver.domain import Person, PersonIdentity, PersonRepository


class InMemoryPersonRepository(PersonRepository):
    """Store people in memory for tests and early application wiring."""

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._people_by_id: dict[UUID, Person] = {}

    def add(self, person: Person) -> None:
        """Persist a person entity in memory."""
        self._people_by_id[person.id] = person  # type: ignore[index]  # UUID | None guarantee

    def find_by_id(self, person_id: UUID) -> Person | None:
        """Find a person by its domain identifier."""
        return self._people_by_id.get(person_id)

    def find_by_identity(self, identity: PersonIdentity) -> Person | None:
        """Find a person by its external identity."""
        return next(
            (person for person in self._people_by_id.values() if person.identity == identity),
            None,
        )

    def list_all(self) -> list[Person]:
        """Return all known people."""
        return list(self._people_by_id.values())