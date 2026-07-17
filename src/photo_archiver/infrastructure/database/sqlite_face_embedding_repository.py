"""SQLite implementation of the face embedding repository interface.

Embeddings are serialized as JSON arrays (``tuple[float, ...]`` → list) in
a TEXT column. JSON is used rather than pickle because pickle deserialization
is an arbitrary-code-execution vector (SEC-030): the SQLite database is not
inside the project's trust boundary — a malicious model pack, backup tampering
or disk access could otherwise craft a pickle payload that ``pickle.loads``
would execute. JSON deserialization is data-only and cannot run code.
"""

import json
from datetime import datetime
from uuid import UUID

from photo_archiver.domain import FaceEmbedding, FaceEmbeddingRepository
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import datetime_to_text


class SQLiteFaceEmbeddingRepository(FaceEmbeddingRepository):
    """Persist per-person face embeddings in SQLite as JSON arrays."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def save(self, person_id: UUID, embedding: FaceEmbedding) -> None:
        """Persist or replace the canonical embedding for a person via upsert.

        Args:
            person_id: The person identifier.
            embedding: The face embedding to store; its tuple is serialized as
                a JSON array so the column stays human-readable and safe to
                deserialize.
        """
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO person_embeddings (person_id, embedding, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(person_id) DO UPDATE SET
                    embedding = excluded.embedding,
                    created_at = excluded.created_at
                """,
                (
                    str(person_id),
                    json.dumps(list(embedding.vector)),
                    datetime_to_text(datetime.now()),
                ),
            )

    def find_by_person(self, person_id: UUID) -> FaceEmbedding | None:
        """Return the canonical embedding for a person, or ``None``.

        Args:
            person_id: The person identifier.

        Returns:
            A :class:`FaceEmbedding` rebuilt from the stored JSON array, or
            ``None`` when no row exists.
        """
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT embedding FROM person_embeddings WHERE person_id = ?",
                (str(person_id),),
            ).fetchone()
        if row is None:
            return None
        return FaceEmbedding(tuple(json.loads(row["embedding"])))

    def list_all(self) -> dict[UUID, FaceEmbedding]:
        """Return a ``person_id → embedding`` mapping for all known persons.

        Returns:
            A dict covering every persisted embedding. Empty when no person
            has a stored embedding.
        """
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT person_id, embedding FROM person_embeddings"
            ).fetchall()
        return {
            UUID(row["person_id"]): FaceEmbedding(tuple(json.loads(row["embedding"])))
            for row in rows
        }

