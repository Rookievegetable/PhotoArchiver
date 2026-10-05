"""SQLite implementation of the recognition result repository interface."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from photo_archiver.domain import (
    MatchStatus,
    RecognitionResult,
    RecognitionRepository,
)
from photo_archiver.domain.repositories.recognition_repository import WorkspaceCounts
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
                    id, photo_id, person_id, status, confidence, created_at,
                    assignment_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    photo_id = excluded.photo_id,
                    person_id = excluded.person_id,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    created_at = excluded.created_at,
                    assignment_id = excluded.assignment_id
                """,
                (
                    str(result.id),
                    str(result.photo_id),
                    str(result.person_id) if result.person_id is not None else None,
                    result.status.value,
                    result.confidence,
                    datetime_to_text(self._require_created_at(result)),
                    str(result.assignment_id) if result.assignment_id is not None else None,
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
                str(result.assignment_id) if result.assignment_id is not None else None,
            )
            for result in results
        ]
        with self._connection_provider.connect() as connection:
            connection.executemany(
                """
                INSERT INTO recognition_results (
                    id, photo_id, person_id, status, confidence, created_at,
                    assignment_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    photo_id = excluded.photo_id,
                    person_id = excluded.person_id,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    created_at = excluded.created_at,
                    assignment_id = excluded.assignment_id
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

    def find_projection(
        self, photo_id: UUID, person_id: UUID,
    ) -> RecognitionResult | None:
        """Return the **live** Assignment-derived projection for ``(photo, person)``.

        S1：``assignment_id IS NOT NULL`` 是硬门槛——legacy 人工决策
        （D-1 审核批准行）永不在此返回，因S0 INV-4 它们不受 reconcile 管理。

        只返回 ``status='approved'`` 的行：已终结（rejected）的投影保留
        ``assignment_id`` 以维持审计痕迹与可恢复性，但不算作「当前存在的投影」。
        """
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM recognition_results "
                "WHERE photo_id = ? AND person_id = ? AND assignment_id IS NOT NULL "
                "AND status = ? ORDER BY created_at, id LIMIT 1",
                (str(photo_id), str(person_id), MatchStatus.APPROVED.value),
            ).fetchone()
        return recognition_result_from_row(row) if row is not None else None

    def list_projections(self) -> list[RecognitionResult]:
        """Return every Assignment-derived projection (``assignment_id IS NOT NULL``)."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recognition_results WHERE assignment_id IS NOT NULL "
                "ORDER BY created_at, id",
            ).fetchall()
        return [recognition_result_from_row(row) for row in rows]

    def list_all_approved(self) -> list[RecognitionResult]:
        """S1：全部 approved 行（含 legacy 与 projection），供 rebuild 统计与审计。"""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recognition_results WHERE status = ? "
                "ORDER BY created_at, id",
                (MatchStatus.APPROVED.value,),
            ).fetchall()
        return [recognition_result_from_row(row) for row in rows]

    def list_projections_of_assignment(
        self, assignment_id: UUID,
    ) -> list[RecognitionResult]:
        """Return all projections currently referencing ``assignment_id``.

        S1：可以返回多行——一个 Assignment 覆盖一个簇的多张照片时每个 photo 一行。
        """
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recognition_results WHERE assignment_id = ? "
                "ORDER BY created_at, id",
                (str(assignment_id),),
            ).fetchall()
        return [recognition_result_from_row(row) for row in rows]

    def create_projection(
        self, photo_id: UUID, person_id: UUID, assignment_id: UUID,
    ) -> RecognitionResult:
        """Create an approved projection owned by ``assignment_id``.

        S1 D-3：若该 ``(photo, person)`` 上已有 pending 占位行（识别期写入，
        ``person_id IS NULL``），**复用**该行就地翻转为 approved——避免产生第二条
        行，也避免遗留 pending 行继续留在审核队列。
        """
        now = datetime.now()
        with self._connection_provider.connect() as connection:
            pending = connection.execute(
                "SELECT * FROM recognition_results "
                "WHERE photo_id = ? AND status = ? AND person_id IS NULL "
                "ORDER BY created_at, id LIMIT 1",
                (str(photo_id), MatchStatus.PENDING.value),
            ).fetchone()
            if pending is not None:
                connection.execute(
                    "UPDATE recognition_results "
                    "SET status = ?, person_id = ?, assignment_id = ? WHERE id = ?",
                    (
                        MatchStatus.APPROVED.value,
                        str(person_id),
                        str(assignment_id),
                        pending["id"],
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM recognition_results WHERE id = ?",
                    (pending["id"],),
                ).fetchone()
                return recognition_result_from_row(row)
            result = RecognitionResult(
                photo_id=photo_id,
                person_id=person_id,
                confidence=None,  # BLK-5：位次配对/人工指派无相似度证据
                status=MatchStatus.APPROVED,
                created_at=now,
                assignment_id=assignment_id,
            )
            connection.execute(
                """
                INSERT INTO recognition_results (
                    id, photo_id, person_id, status, confidence, created_at,
                    assignment_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(result.id),
                    str(photo_id),
                    str(person_id),
                    MatchStatus.APPROVED.value,
                    None,
                    datetime_to_text(now),
                    str(assignment_id),
                ),
            )
            row = connection.execute(
                "SELECT * FROM recognition_results WHERE id = ?",
                (str(result.id),),
            ).fetchone()
            return recognition_result_from_row(row)

    def retarget_projection(self, result_id: UUID, assignment_id: UUID) -> int:
        """Point an existing projection at another supporting Assignment.

        S1：支撑引用改变**不改变**投影存在性——只要 active_supports 非空就保留。
        """
        with self._connection_provider.connect() as connection:
            cursor = connection.execute(
                "UPDATE recognition_results SET assignment_id = ? WHERE id = ?",
                (str(assignment_id), str(result_id)),
            )
            return cursor.rowcount

    def terminate_projection(self, result_id: UUID) -> int:
        """Terminate a projection: ``approved`` → ``rejected``（不 DELETE）。

        仅当该 ``(photo, person)`` 已无任何 active supporting Assignment 时调用。
        转 rejected 保留审计痕迹；DELETE 会破坏归档去重的历史可查性。
        """
        with self._connection_provider.connect() as connection:
            cursor = connection.execute(
                "UPDATE recognition_results SET status = ? "
                "WHERE id = ? AND status = ?",
                (MatchStatus.REJECTED.value, str(result_id), MatchStatus.APPROVED.value),
            )
            return cursor.rowcount

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

    def list_by_photo_ids(
        self, photo_ids: Sequence[UUID],
    ) -> list[RecognitionResult]:
        """Return ALL recognition results for the supplied photos in one round trip.

        FILTERED-export query (FEATURE-004 contract §3/F4): every result — any
        status — whose ``photo_id`` is in ``photo_ids`` (unlike the
        earliest-per-photo ``list_first_by_photo_ids``). Ordered by
        ``created_at`` then ``id``, mirroring ``list_by_photo``. Empty input
        returns ``[]`` without opening a connection.
        """
        if not photo_ids:
            return []
        results: list[RecognitionResult] = []
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
                results.extend(recognition_result_from_row(row) for row in rows)
        # Chunked IN queries each order by created_at, id; re-sort the combined
        # result so the global order matches the documented contract (and the
        # Protocol default implementation) regardless of how photo_ids spans
        # chunk boundaries.
        results.sort(
            key=lambda result: (
                result.created_at if result.created_at is not None else datetime.min,
                result.id,
            ),
        )
        return results

    def read_workspace_counts(self) -> WorkspaceCounts:
        """Read readiness counts in ONE aggregate query — zero entity materialization.

        Batch2 工作台就绪服务要求大库上不得全量物化实体列表，因此本方法把
        一次性 SQL 推到存储层：

        - has_persons / has_photos：EXISTS 全表任一行（不做状态过滤）。
        - pending_match_count：无任何识别行的照片数（NOT EXISTS）。
        - pending_review_count：status=pending 的结果行数——ReviewDialog 按
          结果行展示（同一照片可有多张待审人脸），故意不去重。
        - archivable_count：与 ArchivePlanner 同语义的可归档 (person, photo)
          对数（E-SG-6 多 attribution）——绝对路径
          照片（path_base='absolute'，planner 的 ``is_absolute`` 过滤对应列）、
          APPROVED 结果且 person 仍在库内（FK ON DELETE SET NULL 保证
          person_id NULL 即人员已删）、且没有成功态归档记录（ARCHIVED /
          SKIPPED / RENAMED / OVERWRITTEN；FAILED/PLANNED/DRY_RUN 不拦重试，
          与 find_by_photo / planner 的 review M-2 语义一致）。
          Stage 4 BLK-1：成功态归档去重与 planner 一样**按 person_id 稳定身份**
          判定（``a.person_id = r.person_id``），``a.person_id IS NULL`` 的存量行
          回退按姓名匹配——与 ``has_successful_for_person`` 保持同一口径，
          否则计数会与实际可归档项脱节。
        """
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    EXISTS(SELECT 1 FROM people) AS has_persons,
                    EXISTS(SELECT 1 FROM photos) AS has_photos,
                    (
                        SELECT COUNT(*) FROM photos p
                        WHERE NOT EXISTS (
                            SELECT 1 FROM recognition_results r WHERE r.photo_id = p.id
                        )
                    ) AS pending_match_count,
                    (
                        SELECT COUNT(*) FROM recognition_results
                        WHERE status = :pending
                    ) AS pending_review_count,
                    (
                        -- E-SG-6：归档去重作用域 (person, photo)——同一照片可
                        -- 同时归属多个 Person，各自计入可归档数。
                        SELECT COUNT(*) FROM (
                            SELECT DISTINCT r.person_id, r.photo_id
                            FROM recognition_results r
                            JOIN photos p ON p.id = r.photo_id
                            JOIN people person ON person.id = r.person_id
                            WHERE r.status = :approved
                              AND p.path_base = 'absolute'
                              AND r.person_id IS NOT NULL
                              AND NOT EXISTS (
                                  SELECT 1 FROM archive_records a
                                  WHERE a.photo_id = r.photo_id
                                    AND a.status IN ('archived', 'skipped', 'renamed', 'overwritten')
                                    AND (
                                        a.person_id = r.person_id
                                        OR (a.person_id IS NULL
                                            AND a.target_person_name = person.name)
                                    )
                              )
                        )
                    ) AS archivable_count
                """,
                {
                    "pending": MatchStatus.PENDING.value,
                    "approved": MatchStatus.APPROVED.value,
                },
            ).fetchone()
        assert row is not None  # aggregate SELECT always returns exactly one row
        return WorkspaceCounts(
            has_persons=bool(row["has_persons"]),
            has_photos=bool(row["has_photos"]),
            pending_match_count=int(row["pending_match_count"]),
            pending_review_count=int(row["pending_review_count"]),
            archivable_count=int(row["archivable_count"]),
        )

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

    def remove_results_for_person_photos(
        self, person_id: UUID, photo_ids: Sequence[UUID],
    ) -> int:
        """Stage E（E-SG-6）：回收 (person, photo) 的 APPROVED 兼容归属。"""
        unique_ids = list(dict.fromkeys(photo_ids))
        if not unique_ids:
            return 0
        placeholders = ", ".join("?" for _ in unique_ids)
        with self._connection_provider.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM recognition_results WHERE person_id = ? "
                f"AND status = 'approved' AND photo_id IN ({placeholders})",
                (str(person_id), *(str(photo_id) for photo_id in unique_ids)),
            )
            return cursor.rowcount

    def update_status(
        self,
        result_id: UUID,
        status: MatchStatus,
        person_id: UUID | None = None,
        assignment_id: UUID | None = None,
    ) -> int:
        """Transition a recognition result's review status (and optionally identity).

        ``person_id`` (Stage 4 D-1) is written **alongside** the status when
        supplied, so a manual approval can also record the decided identity —
        otherwise the approved row keeps ``person_id IS NULL`` and the archive
        planner (``WHERE person_id = ? AND status = 'approved'``) can never
        consume it. ``None`` leaves the column untouched (reject path).

        ``assignment_id`` (S1) is written only when supplied, and is used by
        :class:`ProjectionReconciler` to restore/retarget a projection. It is
        never used to *create* an unowned approved row.

        Returns:
            The number of rows affected (1 on hit, 0 when the result id is
            missing). A 0 signals concurrent deletion rather than silent success.
        """
        assignments: list[str] = []
        person_param: str | None = None
        if person_id is not None:
            person_param = str(person_id)
            assignments.append("person_id = ?")
        if assignment_id is not None:
            assignments.append("assignment_id = ?")
        extra: tuple[str | None, ...] = ()
        if person_param is not None:
            extra += (person_param,)
        if assignment_id is not None:
            extra += (str(assignment_id),)

        statement = "UPDATE recognition_results SET status = ?"
        if assignments:
            statement += ", " + ", ".join(assignments)
        statement += " WHERE id = ?"

        with self._connection_provider.connect() as connection:
            cursor = connection.execute(
                statement,
                (status.value, *extra, str(result_id)),
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
