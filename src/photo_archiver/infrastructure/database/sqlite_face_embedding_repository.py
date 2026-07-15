"""SQLite implementation of the face embedding repository interface."""

import pickle
from datetime import datetime
from uuid import UUID

from photo_archiver.domain import FaceEmbedding, FaceEmbeddingRepository
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import datetime_to_text


class SQLiteFaceEmbeddingRepository(FaceEmbeddingRepository):
    """Persist per-person face embeddings in SQLite."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def save(self, person_id: UUID, embedding: FaceEmbedding) -> None:
        """Persist or replace the canonical embedding for a person via upsert."""
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
                    pickle.dumps(embedding.vector),
                    datetime_to_text(datetime.now()),
                ),
            )

    def find_by_person(self, person_id: UUID) -> FaceEmbedding | None:
        """Return the canonical embedding for a person, or ``None``."""
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT embedding FROM person_embeddings WHERE person_id = ?",
                (str(person_id),),
            ).fetchone()
        if row is None:
            return None
        return FaceEmbedding(pickle.loads(row["embedding"]))

    def list_all(self) -> dict[UUID, FaceEmbedding]:
        """Return a ``person_id → embedding`` mapping for all known persons."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT person_id, embedding FROM person_embeddings"
            ).fetchall()
        return {
            UUID(row["person_id"]): FaceEmbedding(pickle.loads(row["embedding"]))
            for row in rows
        }
