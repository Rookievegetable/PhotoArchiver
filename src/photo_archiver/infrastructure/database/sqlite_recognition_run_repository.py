"""SQLite implementation of the recognition run repository interface（阶段 C）.

``parameters`` 以 JSON 文本存储运行配置快照（C-SEM-3）：``add_run``
写入后，``update_run`` 刻意不触碰该列——运行结果统计只写独立统计列。
"""

import json
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from photo_archiver.domain.entities.recognition_run import RecognitionRun, RunPhotoSnapshot
from photo_archiver.domain.repositories.recognition_run_repository import (
    RecognitionRunRepository,
)
from photo_archiver.domain.value_objects import FaceCountRange
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import (
    datetime_to_text,
    recognition_run_from_row,
    text_to_datetime,
)


class SQLiteRecognitionRunRepository(RecognitionRunRepository):
    """Persist recognition runs with their photo snapshots and scopes in SQLite."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def add_run(self, run: RecognitionRun) -> None:
        """Insert a new run row；重跑 = 新行，绝不 UPDATE 旧 run（C-SEM-1）."""
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO recognition_runs (
                    id, status, parameters, face_count, unreadable_count, no_face_count,
                    error_count, in_scope_photo_count, out_of_scope_photo_count, error,
                    created_at, finished_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(run.id),
                    run.status,
                    json.dumps(dict(run.parameters), ensure_ascii=False, sort_keys=True),
                    run.face_count,
                    run.unreadable_count,
                    run.no_face_count,
                    run.error_count,
                    run.in_scope_photo_count,
                    run.out_of_scope_photo_count,
                    run.error,
                    datetime_to_text(self._require_created_at(run)),
                    (
                        datetime_to_text(run.finished_at)
                        if run.finished_at is not None
                        else None
                    ),
                ),
            )

    def get_run(self, run_id: UUID) -> RecognitionRun | None:
        """Return the run or ``None`` when it does not exist."""
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM recognition_runs WHERE id = ?",
                (str(run_id),),
            ).fetchone()
        return recognition_run_from_row(row) if row is not None else None

    def list_runs(self) -> list[RecognitionRun]:
        """Return all runs, newest first (``created_at`` DESC, ``id`` ASC tiebreak)."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recognition_runs ORDER BY created_at DESC, id"
            ).fetchall()
        return [recognition_run_from_row(row) for row in rows]

    def update_run(self, run: RecognitionRun) -> int:
        """Persist status/统计列/finished_at/error——刻意不更新 parameters（C-SEM-3）.

        Returns:
            受影响行数（1 命中 / 0 run 不存在，0 应视为并发删除信号）。
        """
        with self._connection_provider.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE recognition_runs SET
                    status = ?,
                    face_count = ?,
                    unreadable_count = ?,
                    no_face_count = ?,
                    error_count = ?,
                    in_scope_photo_count = ?,
                    out_of_scope_photo_count = ?,
                    error = ?,
                    finished_at = ?
                WHERE id = ?
                """,
                (
                    run.status,
                    run.face_count,
                    run.unreadable_count,
                    run.no_face_count,
                    run.error_count,
                    run.in_scope_photo_count,
                    run.out_of_scope_photo_count,
                    run.error,
                    (
                        datetime_to_text(run.finished_at)
                        if run.finished_at is not None
                        else None
                    ),
                    str(run.id),
                ),
            )
            return cursor.rowcount

    def add_run_photos(self, run_id: UUID, snapshots: Sequence[RunPhotoSnapshot]) -> None:
        """Insert the immutable photo snapshots in submission order."""
        if not snapshots:
            return
        with self._connection_provider.connect() as connection:
            connection.executemany(
                """
                INSERT INTO recognition_run_photos (
                    run_id, photo_id, raw_path_snapshot, captured_at_snapshot
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        str(run_id),
                        str(snapshot.photo_id),
                        snapshot.raw_path,
                        datetime_to_text(snapshot.captured_at)
                        if snapshot.captured_at is not None
                        else None,
                    )
                    for snapshot in snapshots
                ],
            )

    def add_run_scopes(self, run_id: UUID, ranges: Sequence[FaceCountRange]) -> None:
        """Insert the selected ranges in their explicit UI order."""
        if not ranges:
            return
        with self._connection_provider.connect() as connection:
            connection.executemany(
                """
                INSERT INTO recognition_run_scopes (run_id, ordinal, min_count, max_count)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (str(run_id), ordinal, face_range.min_count, face_range.max_count)
                    for ordinal, face_range in enumerate(ranges)
                ],
            )

    def list_run_photos(self, run_id: UUID) -> list[RunPhotoSnapshot]:
        """Return photo snapshots in their persisted submission order."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT run_id, photo_id, raw_path_snapshot, captured_at_snapshot "
                "FROM recognition_run_photos WHERE run_id = ? "
                "ORDER BY rowid",
                (str(run_id),),
            ).fetchall()
        return [
            RunPhotoSnapshot(
                run_id=UUID(row["run_id"]),
                photo_id=UUID(row["photo_id"]),
                raw_path=row["raw_path_snapshot"],
                captured_at=(
                    text_to_datetime(row["captured_at_snapshot"])
                    if row["captured_at_snapshot"] is not None
                    else None
                ),
            )
            for row in rows
        ]

    def list_run_scopes(self, run_id: UUID) -> list[FaceCountRange]:
        """Return selected ranges in their persisted ordinal order."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT min_count, max_count FROM recognition_run_scopes "
                "WHERE run_id = ? ORDER BY ordinal",
                (str(run_id),),
            ).fetchall()
        return [FaceCountRange(row["min_count"], row["max_count"]) for row in rows]

    @staticmethod
    def _require_created_at(run: RecognitionRun) -> datetime:
        """Return the generated creation timestamp with a narrow type guard."""
        if run.created_at is None:
            raise ValueError("RecognitionRun must have a creation timestamp")
        return run.created_at
