"""SQLite implementation of the archive record repository interface."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from photo_archiver.domain import ArchiveRecord, ArchiveRecordRepository
from photo_archiver.domain.entities.archive import ArchiveStatus
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import (
    archive_record_from_row,
    datetime_to_text,
)

# Bound parameters per IN-clause chunk — stays well under SQLite's compiled
# SQLITE_MAX_VARIABLE_NUMBER on every supported build (COD-023 named constant;
# same value as sqlite_recognition_repository._SQLITE_PARAMETER_CHUNK).
_SQLITE_PARAMETER_CHUNK = 500


class SQLiteArchiveRecordRepository(ArchiveRecordRepository):
    """Persist archive records in SQLite."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def add(self, record: ArchiveRecord) -> None:
        """Persist an archive record using an idempotent upsert by id.

        ``archived_at`` 与 ``error`` 均可为 None（PLANNED 状态时尚未落盘），
        与 ArchiveRecord 实体的可选字段语义一致，落 SQLite NULL 列。
        """
        archived_at_text = (
            datetime_to_text(record.archived_at)
            if record.archived_at is not None
            else None
        )
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO archive_records (
                    id, photo_id,
                    target_archive_root, target_person_name,
                    target_event_or_date, target_original_name,
                    status, archived_at, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    photo_id = excluded.photo_id,
                    target_archive_root = excluded.target_archive_root,
                    target_person_name = excluded.target_person_name,
                    target_event_or_date = excluded.target_event_or_date,
                    target_original_name = excluded.target_original_name,
                    status = excluded.status,
                    archived_at = excluded.archived_at,
                    error = excluded.error
                """,
                (
                    str(record.id),
                    str(record.photo_id),
                    record.target_archive_root,
                    record.target_person_name,
                    record.target_event_or_date,
                    record.target_original_name,
                    record.status.value,
                    archived_at_text,
                    record.error,
                ),
            )

    def find_by_id(self, record_id: UUID) -> ArchiveRecord | None:
        """Find an archive record by its domain identifier."""
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM archive_records WHERE id = ?",
                (str(record_id),),
            ).fetchone()
        return archive_record_from_row(row) if row is not None else None

    def find_by_photo(self, photo_id: UUID) -> ArchiveRecord | None:
        """Return the most recent SUCCESS archive record for the given photo.

        review M-2 fix: filter to success states (ARCHIVED/SKIPPED/RENAMED/OVERWRITTEN)
        so historical FAILED / PLANNED / DRY_RUN rows don't block retries — the
        planner checks this to decide "already archived?" and FAILED should be
        re-attemptable. Ordered by archived_at DESC, id DESC for recency.
        """
        success_states = (
            ArchiveStatus.ARCHIVED.value,
            ArchiveStatus.SKIPPED.value,
            ArchiveStatus.RENAMED.value,
            ArchiveStatus.OVERWRITTEN.value,
        )
        placeholders = ",".join("?" for _ in success_states)
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                f"SELECT * FROM archive_records WHERE photo_id = ? "
                f"AND status IN ({placeholders}) "
                f"ORDER BY archived_at DESC, id DESC LIMIT 1",
                (str(photo_id), *success_states),
            ).fetchone()
        return archive_record_from_row(row) if row is not None else None

    def list_by_status(self, status: ArchiveStatus) -> list[ArchiveRecord]:
        """Return all archive records in the given lifecycle state."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM archive_records WHERE status = ? "
                "ORDER BY archived_at DESC, id DESC",
                (status.value,),
            ).fetchall()
        return [archive_record_from_row(row) for row in rows]

    def list_all(self) -> list[ArchiveRecord]:
        """Return all archive records ordered by recency."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM archive_records ORDER BY archived_at DESC, id DESC"
            ).fetchall()
        return [archive_record_from_row(row) for row in rows]

    def list_by_photo_ids(
        self, photo_ids: Sequence[UUID],
    ) -> list[ArchiveRecord]:
        """Return all archive records for the supplied photos in one round trip.

        FILTERED-export query (FEATURE-004 contract §3/F4): every record — any
        status — whose ``photo_id`` is in ``photo_ids`` (unlike
        ``find_by_photo``, which returns only the latest success for one
        photo). Ordering matches ``list_all`` (``archived_at DESC, id DESC``;
        NULL ``archived_at`` — PLANNED — sorts last under DESC). Empty input
        returns ``[]`` without opening a connection.
        """
        if not photo_ids:
            return []
        records: list[ArchiveRecord] = []
        with self._connection_provider.connect() as connection:
            for chunk_start in range(0, len(photo_ids), _SQLITE_PARAMETER_CHUNK):
                chunk = [
                    str(pid)
                    for pid in photo_ids[chunk_start : chunk_start + _SQLITE_PARAMETER_CHUNK]
                ]
                placeholders = ", ".join("?" for _ in chunk)
                rows = connection.execute(
                    f"SELECT * FROM archive_records "
                    f"WHERE photo_id IN ({placeholders}) "
                    f"ORDER BY archived_at DESC, id DESC",
                    chunk,
                ).fetchall()
                records.extend(archive_record_from_row(row) for row in rows)
        # Chunked IN queries each order within their chunk; re-sort the combined
        # result so the global order matches list_all (archived_at DESC, id DESC,
        # PLANNED/NULL archived_at last) and the Protocol default implementation.
        records.sort(
            key=lambda record: (
                record.archived_at is not None,
                record.archived_at if record.archived_at is not None else datetime.min,
                record.id,
            ),
            reverse=True,
        )
        return records
