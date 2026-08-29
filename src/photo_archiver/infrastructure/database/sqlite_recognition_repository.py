"""SQLite implementation of the recognition result repository interface."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from photo_archiver.domain import MatchStatus, RecognitionResult, RecognitionRepository
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import (
    datetime_to_text,
    recognition_result_from_row,
)

# Bound parameters per IN-clause chunk — stays well under SQLite's compiled
# SQLITE_MAX_VARIABLE_NUMBER on every supported build (COD-023 named constant).
_SQLITE_PARAMETER_CHUNK = 500


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
                    datetime_to_text(self._require_created_at(result)),
                ),
            )

    def add_many(self, results: Sequence[RecognitionResult]) -> None:
        """Persist a batch of recognition results in one executemany upsert.

        Single-connection push-down (phase6 裁决 A-3): one transaction and one
        ``executemany`` round trip instead of per-result ``add`` calls. Empty
        input is a no-op that does not open a connection.
        """
        if not results:
            return
        rows = [
            (
                str(result.id),
                str(result.photo_id),
                str(result.person_id) if result.person_id is not None else None,
                result.status.value,
                result.confidence,
                datetime_to_text(self._require_created_at(result)),
            )
            for result in results
        ]
        with self._connection_provider.connect() as connection:
            connection.executemany(
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
                rows,
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

    def list_first_by_photo_ids(
        self, photo_ids: Sequence[UUID]
    ) -> dict[UUID, RecognitionResult]:
        """Return the earliest recognition result per photo via IN-clause chunks.

        Ordering mirrors ``list_by_photo`` (``created_at`` then ``id``), so the
        first row encountered per photo equals ``list_by_photo(id)[0]``.
        """
        if not photo_ids:
            return {}
        results: dict[UUID, RecognitionResult] = {}
        with self._connection_provider.connect() as connection:
            for chunk_start in range(0, len(photo_ids), _SQLITE_PARAMETER_CHUNK):
                chunk = [
                    str(pid)
                    for pid in photo_ids[chunk_start : chunk_start + _SQLITE_PARAMETER_CHUNK]
                ]
                placeholders = ", ".join("?" for _ in chunk)
                rows = connection.execute(
                    f"SELECT * FROM recognition_results "
                    f"WHERE photo_id IN ({placeholders}) "
                    f"ORDER BY created_at, id",
                    chunk,
                ).fetchall()
                for row in rows:
                    result = recognition_result_from_row(row)
                    results.setdefault(result.photo_id, result)
        return results

    def list_pending(self) -> list[RecognitionResult]:
        """Return all recognition results awaiting user review."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recognition_results WHERE status = ? ORDER BY created_at, id",
                (MatchStatus.PENDING.value,),
            ).fetchall()
        return [recognition_result_from_row(row) for row in rows]

    def list_approved_by_person(self, person_id: UUID) -> list[RecognitionResult]:
        """Return all APPROVED recognition results for the given person.

        Used by Step 11 ArchivePlanner to gather a person's approved photos
        for归档组织。Ordered by ``created_at`` then ``id`` so the planner
        produces a stable archive ordering under re-invocation.
        """
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recognition_results "
                "WHERE person_id = ? AND status = ? "
                "ORDER BY created_at, id",
                (str(person_id), MatchStatus.APPROVED.value),
            ).fetchall()
        return [recognition_result_from_row(row) for row in rows]

    def update_status(self, result_id: UUID, status: MatchStatus) -> int:
        """Transition a recognition result's review status.

        Returns:
            The number of rows affected (1 on hit, 0 when the result id is
            missing). A 0 signals concurrent deletion rather than silent success.
        """
        with self._connection_provider.connect() as connection:
            cursor = connection.execute(
                "UPDATE recognition_results SET status = ? WHERE id = ?",
                (status.value, str(result_id)),
            )
            return cursor.rowcount

    @staticmethod
    def _require_created_at(result: RecognitionResult) -> datetime:
        """Return the result's created_at, asserting it is set.

        RecognitionResult.__post_init__ guarantees created_at is populated on
        construction, but the type signature is ``datetime | None``. This
        helper makes the invariant explicit at the persistence boundary so a
        future refactor that bypasses __post_init__ cannot silently pass
        ``None`` into SQLite serialization.
        """
        assert result.created_at is not None, "RecognitionResult.created_at must be set"
        return result.created_at  # type: ignore[return-value]
