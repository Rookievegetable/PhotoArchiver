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
        # datetime.now() is tz-naive, matching RecognitionResult.__post_init__
        # convention; the project has no tz mandate yet so we stay consistent
        # with the existing entity timestamps rather than introducing tz here.
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

    def list_all(
        self,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[UUID, FaceEmbedding]:
        """Return a ``person_id → embedding`` mapping for known persons.

        Args:
            limit: Maximum number of embeddings to return. ``None`` (default)
                returns every persisted row — original full-scan behavior kept
                for backward compatibility. Pass a positive int to cap memory
                when person volume is large.
            offset: Number of embeddings to skip before collecting rows.
                Defaults to ``0``; combine with ``limit`` for page-style access.

        Returns:
            A dict covering the requested slice of persisted embeddings.
            Empty when no row falls in the ``[offset, offset+limit)`` range.

        Raises:
            ValueError: When ``limit`` is non-positive or ``offset`` is negative.

        Implementation note: ``LIMIT -1`` is SQLite's sentinel meaning "no
        limit" — we bind it when ``limit is None`` so the SQL shape stays
        uniform and the offset-only path still works.
        """
        if limit is not None and limit <= 0:
            raise ValueError(f"limit must be positive or None, got {limit}")
        if offset < 0:
            raise ValueError(f"offset must be non-negative, got {offset}")
        bound_limit = -1 if limit is None else limit
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT person_id, embedding FROM person_embeddings LIMIT ? OFFSET ?",
                (bound_limit, offset),
            ).fetchall()
        return {
            UUID(row["person_id"]): FaceEmbedding(tuple(json.loads(row["embedding"])))
            for row in rows
        }

