"""In-memory implementation of the person repository interface."""

from collections.abc import Sequence
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

    def remove(self, person_id: UUID) -> int:
        """Remove the person from memory; return 1 when removed, else 0.

        幂等：目标不存在返 0。**不模拟级联**（ADR-034 §4.4）——嵌入删除
        与识别归属置空由真实 SQLite 外键承担，级联裁判专属集成测试。
        """
        return 1 if self._people_by_id.pop(person_id, None) is not None else 0

    def find_by_id(self, person_id: UUID) -> Person | None:
        """Find a person by its domain identifier."""
        return self._people_by_id.get(person_id)

    def find_by_identity(self, identity: PersonIdentity) -> Person | None:
        """Find a person by its external identity."""
        return next(
            (person for person in self._people_by_id.values() if person.identity == identity),
            None,
        )

    def find_by_name_department(self, name: str, department: str | None) -> Person | None:
        """Find a person by exact normalized name and department (P0-7, D-B2)."""
        return next(
            (
                person
                for person in self._people_by_id.values()
                if person.name == name and person.department == department
            ),
            None,
        )

    def list_all(self) -> list[Person]:
        """Return all known people in the same roster-aware order as SQLite.

        Mirrors the SQL contract (roster_order first, legacy NULL people after,
        ties by created_at then name) so application tests observe the same
        ordering they get from the real repository.
        """
        def sort_key(person: Person) -> tuple:
            """Sortable key matching the SQLite ORDER BY contract."""
            order_key = person.roster_order if person.roster_order is not None else 0
            created = person.created_at.timestamp() if person.created_at else 0.0
            return (
                0 if person.roster_order is not None else 1,
                order_key, created, person.name,
            )
        return sorted(self._people_by_id.values(), key=sort_key)

    def max_roster_order(self) -> int | None:
        """Return the largest confirmed roster order (None when nobody has one)."""
        orders = [
            person.roster_order
            for person in self._people_by_id.values()
            if person.roster_order is not None
        ]
        return max(orders) if orders else None

    def reorder(self, orders: Sequence[tuple[UUID, int]]) -> int:
        """Persist roster positions in memory (stage B drag reorder)."""
        updated = 0
        for person_id, position in orders:
            person = self._people_by_id.get(person_id)
            if person is None:
                continue
            person.roster_order = position
            updated += 1
        return updated
