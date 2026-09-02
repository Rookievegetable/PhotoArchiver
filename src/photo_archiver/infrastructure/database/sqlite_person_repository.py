"""SQLite implementation of the person repository interface."""

from uuid import UUID

from photo_archiver.domain import Person, PersonIdentity, PersonRepository
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import datetime_to_text, person_from_row


class SQLitePersonRepository(PersonRepository):
    """Persist people in SQLite."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def add(self, person: Person) -> None:
        """Persist a person entity in SQLite using an idempotent upsert by id."""
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO people (id, name, identity, department, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    identity = excluded.identity,
                    department = excluded.department,
                    note = excluded.note,
                    created_at = excluded.created_at
                """,
                (
                    str(person.id),
                    person.name,
                    str(person.identity) if person.identity is not None else None,
                    person.department,
                    person.note,
                    datetime_to_text(person.created_at),  # type: ignore[arg-type]  # guaranteed non-None
                ),
            )

    def find_by_id(self, person_id: UUID) -> Person | None:
        """Find a person by its domain identifier."""
        with self._connection_provider.connect() as connection:
            row = connection.execute("SELECT * FROM people WHERE id = ?", (str(person_id),)).fetchone()
        return person_from_row(row) if row is not None else None

    def find_by_identity(self, identity: PersonIdentity) -> Person | None:
        """Find a person by its external identity."""
        with self._connection_provider.connect() as connection:
            row = connection.execute("SELECT * FROM people WHERE identity = ?", (str(identity),)).fetchone()
        return person_from_row(row) if row is not None else None

    def find_by_name_department(self, name: str, department: str | None) -> Person | None:
        """Find a person by exact normalized name and department (P0-7, D-B2).

        ``department IS ?`` is deliberately NULL-safe so a ``None`` department
        matches stored NULLs as well as any concrete value.
        """
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM people WHERE name = ? AND department IS ?",
                (name, department),
            ).fetchone()
        return person_from_row(row) if row is not None else None

    def list_all(self) -> list[Person]:
        """Return all known people."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute("SELECT * FROM people ORDER BY created_at, id").fetchall()
        return [person_from_row(row) for row in rows]
