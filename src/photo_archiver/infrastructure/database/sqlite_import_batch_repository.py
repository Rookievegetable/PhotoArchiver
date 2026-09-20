"""SQLite implementation of the import batch repository interface."""

import json
from datetime import datetime
from uuid import UUID

from photo_archiver.domain.entities import ImportBatch, ImportDraftRow
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import datetime_to_text, text_to_datetime


def _batch_from_row(row) -> ImportBatch:  # noqa: ANN001
    """Convert a SQLite row to an ImportBatch entity."""
    confirmed_at = row["confirmed_at"]
    return ImportBatch(
        id=UUID(row["id"]),
        file_name=row["file_name"],
        file_hash=row["file_hash"],
        source_type=row["source_type"],
        encoding=row["encoding"],
        delimiter=row["delimiter"],
        has_header=bool(row["has_header"]),
        sheet_name=row["sheet_name"],
        status=row["status"],
        created_at=text_to_datetime(row["created_at"]),
        confirmed_at=text_to_datetime(confirmed_at) if confirmed_at else None,
    )


def _row_from_row(row) -> ImportDraftRow:  # noqa: ANN001
    """Convert a SQLite row to an ImportDraftRow entity."""
    return ImportDraftRow(
        id=UUID(row["id"]),
        batch_id=UUID(row["batch_id"]),
        source_row=row["source_row"],
        raw_values=json.loads(row["raw_values"]),
        parsed_name=row["parsed_name"] or "",
        parsed_identity=row["parsed_identity"],
        parsed_department=row["parsed_department"],
        parsed_note=row["parsed_note"],
        parsed_group=row["parsed_group"],
        warnings=tuple(json.loads(row["warnings"])),
        action=row["action"],
        merge_target_id=UUID(row["merge_target_id"]) if row["merge_target_id"] else None,
        order_index=row["order_index"],
    )


class SQLiteImportBatchRepository:
    """Persist import batches and their editable draft rows in SQLite."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def add_batch(self, batch: ImportBatch) -> None:
        """Persist a new import batch (draft status)."""
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO import_batches (id, file_name, file_hash, source_type,
                                            encoding, delimiter, has_header, sheet_name,
                                            status, created_at, confirmed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(batch.id),
                    batch.file_name,
                    batch.file_hash,
                    batch.source_type,
                    batch.encoding,
                    batch.delimiter,
                    1 if batch.has_header else 0,
                    batch.sheet_name,
                    batch.status,
                    datetime_to_text(batch.created_at),  # type: ignore[arg-type]  # set in __post_init__
                    None,
                ),
            )

    def get_batch(self, batch_id: UUID) -> ImportBatch | None:
        """Return the batch or ``None`` when it does not exist."""
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM import_batches WHERE id = ?", (str(batch_id),)
            ).fetchone()
        return _batch_from_row(row) if row is not None else None

    def set_batch_status(
        self, batch_id: UUID, status: str, confirmed_at: datetime | None = None,
    ) -> None:
        """Move a batch through its lifecycle (draft → confirmed/cancelled)."""
        with self._connection_provider.connect() as connection:
            connection.execute(
                "UPDATE import_batches SET status = ?, confirmed_at = ? WHERE id = ?",
                (status, datetime_to_text(confirmed_at) if confirmed_at else None, str(batch_id)),
            )

    def replace_draft_rows(self, batch_id: UUID, rows: list[ImportDraftRow]) -> None:
        """Replace all draft rows of a batch (used by re-parse and edits)."""
        with self._connection_provider.connect() as connection:
            connection.execute("DELETE FROM import_draft_rows WHERE batch_id = ?", (str(batch_id),))
            connection.executemany(
                """
                INSERT INTO import_draft_rows (id, batch_id, source_row, raw_values,
                                               parsed_name, parsed_identity,
                                               parsed_department, parsed_note,
                                               parsed_group, warnings, action,
                                               merge_target_id, order_index)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(row.id),
                        str(batch_id),
                        row.source_row,
                        json.dumps(row.raw_values, ensure_ascii=False),
                        row.parsed_name or None,
                        row.parsed_identity,
                        row.parsed_department,
                        row.parsed_note,
                        row.parsed_group,
                        json.dumps(list(row.warnings), ensure_ascii=False),
                        row.action,
                        str(row.merge_target_id) if row.merge_target_id else None,
                        row.order_index,
                    )
                    for row in rows
                ],
            )

    def list_draft_rows(self, batch_id: UUID) -> list[ImportDraftRow]:
        """Return the batch's draft rows ordered by ``order_index``."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM import_draft_rows WHERE batch_id = ? ORDER BY order_index, source_row",
                (str(batch_id),),
            ).fetchall()
        return [_row_from_row(row) for row in rows]

    def list_batches(self) -> list[ImportBatch]:
        """Return all batches, newest first (batch source review)."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM import_batches ORDER BY created_at DESC, id"
            ).fetchall()
        return [_batch_from_row(row) for row in rows]
