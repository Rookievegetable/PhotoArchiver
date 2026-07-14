"""SQLite implementation of the recognition result repository interface."""

from uuid import UUID

from photo_archiver.domain import MatchStatus, RecognitionResult, RecognitionRepository
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import (
    datetime_to_text,
    recognition_result_from_row,
)


class SQLiteRecognitionRepository(RecognitionRepository):
    """Persist recognition results in SQLite."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def add(self, result: RecognitionResult) -> None:
        """Persist a recognition result using an idempotent upsert by id."""
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO recognition_results (
                    id, photo_id, person_id, status, confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    photo_id = excluded.photo_id,
                    person_id = excluded.person_id,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    created_at = excluded.created_at
                """,
                (
                    str(result.id),
                    str(result.photo_id),
                    str(result.person_id) if result.person_id is not None else None,
                    result.status.value,
                    result.confidence,
                    datetime_to_text(result.created_at),  # type: ignore[arg-type]  # see RecognitionResult.__post_init__
                ),
            )

    def find_by_id(self, result_id: UUID) -> RecognitionResult | None:
        """Find a recognition result by its domain identifier."""
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM recognition_results WHERE id = ?",
                (str(result_id),),
            ).fetchone()
        return recognition_result_from_row(row) if row is not None else None

    def list_by_photo(self, photo_id: UUID) -> list[RecognitionResult]:
        """Return all recognition results for the given photo."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recognition_results WHERE photo_id = ? ORDER BY created_at, id",
                (str(photo_id),),
            ).fetchall()
        return [recognition_result_from_row(row) for row in rows]

    def list_pending(self) -> list[RecognitionResult]:
        """Return all recognition results awaiting user review."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recognition_results WHERE status = ? ORDER BY created_at, id",
                (MatchStatus.PENDING.value,),
            ).fetchall()
        return [recognition_result_from_row(row) for row in rows]

    def update_status(self, result_id: UUID, status: MatchStatus) -> None:
        """Transition a recognition result's review status."""
        with self._connection_provider.connect() as connection:
            connection.execute(
                "UPDATE recognition_results SET status = ? WHERE id = ?",
                (status.value, str(result_id)),
            )
