"""SQLite implementation of the assignment/sample repositories（阶段 E）.

决策行 ``update_assignment`` 只更新状态/证据/确认列——历史行不删；
UNIQUE(person_id, observation_id) 从存储层杜绝重复沉淀样本。
"""

import json
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from photo_archiver.domain.entities.cluster_assignment import (
    ClusterPersonAssignment,
    PersonFaceSample,
    validate_status_source_combination,
)
from photo_archiver.domain.repositories.cluster_assignment_repository import (
    ClusterPersonAssignmentRepository,
    PersonFaceSampleRepository,
)
from photo_archiver.domain.value_objects import FaceEmbedding
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import (
    datetime_to_text,
    text_to_datetime,
)


def _assignment_from_row(row) -> ClusterPersonAssignment:
    """Rebuild a decision row via the normal constructor（重验不变量）."""
    confirmed_at = row["confirmed_at"]
    return ClusterPersonAssignment(
        id=UUID(row["id"]),
        cluster_id=UUID(row["cluster_id"]),
        person_id=UUID(row["person_id"]) if row["person_id"] is not None else None,
        status=row["status"],
        source=row["source"],
        score=row["score"],
        sort_snapshot=json.loads(row["sort_snapshot"]),
        created_at=text_to_datetime(row["created_at"]),
        confirmed_at=text_to_datetime(confirmed_at) if confirmed_at is not None else None,
    )


class SQLiteClusterPersonAssignmentRepository(ClusterPersonAssignmentRepository):
    """Persist identity decisions in SQLite."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        self._connection_provider = connection_provider

    def add_assignments(self, assignments: Sequence[ClusterPersonAssignment]) -> None:
        """批量 INSERT 决策行（空输入 no-op）。

        AUD-027 方案 B：整批**先校验后写入**——任一实体跨字段组合非法时在
        第一条 INSERT 之前拒绝，数据库零新增。
        """
        if not assignments:
            return
        for assignment in assignments:
            validate_status_source_combination(
                assignment.status, assignment.source, assignment.score)
        with self._connection_provider.connect() as connection:
            connection.executemany(
                """
                INSERT INTO cluster_person_assignments (
                    id, cluster_id, person_id, status, source, score,
                    sort_snapshot, created_at, confirmed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(assignment.id),
                        str(assignment.cluster_id),
                        str(assignment.person_id) if assignment.person_id is not None else None,
                        assignment.status,
                        assignment.source,
                        assignment.score,
                        json.dumps(dict(assignment.sort_snapshot), ensure_ascii=False,
                                   sort_keys=True),
                        datetime_to_text(self._require_created_at(assignment)),
                        (
                            datetime_to_text(assignment.confirmed_at)
                            if assignment.confirmed_at is not None
                            else None
                        ),
                    )
                    for assignment in assignments
                ],
            )

    def get_assignment(self, assignment_id: UUID) -> ClusterPersonAssignment | None:
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM cluster_person_assignments WHERE id = ?",
                (str(assignment_id),),
            ).fetchone()
        return _assignment_from_row(row) if row is not None else None

    def update_assignment(self, assignment: ClusterPersonAssignment) -> int:
        """Persist status/score/confirmed_at/sort_snapshot（created_at 不动）。

        AUD-027 方案 B：UPDATE 不写 ``source``——最终落库组合由**数据库中
        持久化的 source** × 本次写入的 status/score 决定，守卫在同一连接内
        先读后验；同时对内存实体的 source 组合同验，防止改内存 source 绕过
        （水合实体两者恒等，合法路径零影响）。目标行不存在时保持既有语义
        （UPDATE 照常执行 → rowcount=0 → 调用方并发删除路径失败），无行可
        损坏、不视作校验通过。
        """
        with self._connection_provider.connect() as connection:
            persisted = connection.execute(
                "SELECT source FROM cluster_person_assignments WHERE id = ?",
                (str(assignment.id),),
            ).fetchone()
            if persisted is not None:
                # 有效落库组合：DB 持久化 source × 本次写入的 status/score。
                validate_status_source_combination(
                    assignment.status, persisted["source"], assignment.score)
                # 内存组合同验：内存 source 被改也绕不过（双组合任一非法即拒）。
                validate_status_source_combination(
                    assignment.status, assignment.source, assignment.score)
            cursor = connection.execute(
                """
                UPDATE cluster_person_assignments SET
                    status = ?,
                    score = ?,
                    sort_snapshot = ?,
                    confirmed_at = ?
                WHERE id = ?
                """,
                (
                    assignment.status,
                    assignment.score,
                    json.dumps(dict(assignment.sort_snapshot), ensure_ascii=False,
                               sort_keys=True),
                    (
                        datetime_to_text(assignment.confirmed_at)
                        if assignment.confirmed_at is not None
                        else None
                    ),
                    str(assignment.id),
                ),
            )
            return cursor.rowcount

    def list_by_cluster(self, cluster_id: UUID) -> list[ClusterPersonAssignment]:
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM cluster_person_assignments WHERE cluster_id = ? "
                "ORDER BY created_at DESC, id",
                (str(cluster_id),),
            ).fetchall()
        return [_assignment_from_row(row) for row in rows]

    def list_latest_decision(self, cluster_id: UUID) -> ClusterPersonAssignment | None:
        """S0 INV-1：取最新一条决策事件，**与 status 无关**。

        先过滤 ACTIVE 再取首行会让 ``confirmed → unassigned`` 之后重新读出已终态化
        的旧 confirmed（已实证）。``idx_cpa_cluster_latest``（migration 009）覆盖
        ``(cluster_id, created_at DESC, id DESC)``，本查询无需额外排序。
        """
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM cluster_person_assignments WHERE cluster_id = ? "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (str(cluster_id),),
            ).fetchone()
        return _assignment_from_row(row) if row is not None else None

    def list_by_cluster_run(self, cluster_run_id: UUID) -> list[ClusterPersonAssignment]:
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                """
                SELECT cluster_person_assignments.* FROM cluster_person_assignments
                JOIN face_clusters ON face_clusters.id =
                    cluster_person_assignments.cluster_id
                WHERE face_clusters.cluster_run_id = ?
                ORDER BY cluster_person_assignments.created_at DESC,
                    cluster_person_assignments.id
                """,
                (str(cluster_run_id),),
            ).fetchall()
        return [_assignment_from_row(row) for row in rows]

    def list_active_by_cluster_run(self, cluster_run_id: UUID) -> list[ClusterPersonAssignment]:
        return [
            assignment for assignment in self.list_by_cluster_run(cluster_run_id)
            if assignment.status in ("suggested", "confirmed", "auto_confirmed")
        ]

    def list_rejected_pairs(self, cluster_run_id: UUID) -> list[tuple[UUID, UUID]]:
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                """
                SELECT cluster_person_assignments.cluster_id,
                    cluster_person_assignments.person_id
                FROM cluster_person_assignments
                JOIN face_clusters ON face_clusters.id =
                    cluster_person_assignments.cluster_id
                WHERE face_clusters.cluster_run_id = ?
                    AND cluster_person_assignments.status = 'rejected'
                """,
                (str(cluster_run_id),),
            ).fetchall()
        return [
            (UUID(row["cluster_id"]), UUID(row["person_id"]))
            for row in rows if row["person_id"] is not None
        ]

    def list_confirmed_person_ids(self, cluster_run_id: UUID) -> list[UUID]:
        """该代际中身份已被占用的人员（confirmed 与 auto_confirmed 决策）。"""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT cluster_person_assignments.person_id
                FROM cluster_person_assignments
                JOIN face_clusters ON face_clusters.id =
                    cluster_person_assignments.cluster_id
                WHERE face_clusters.cluster_run_id = ?
                    AND cluster_person_assignments.status IN ('confirmed', 'auto_confirmed')
                    AND cluster_person_assignments.person_id IS NOT NULL
                """,
                (str(cluster_run_id),),
            ).fetchall()
        return [UUID(row["person_id"]) for row in rows]

    @staticmethod
    def _require_created_at(assignment: ClusterPersonAssignment) -> datetime:
        if assignment.created_at is None:
            raise ValueError("assignment must have a creation timestamp")
        return assignment.created_at


class SQLitePersonFaceSampleRepository(PersonFaceSampleRepository):
    """Persist the person sample library in SQLite."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        self._connection_provider = connection_provider

    def add_samples(self, samples: Sequence[PersonFaceSample]) -> None:
        """批量 INSERT 样本；UNIQUE(person_id, observation_id) 冲突即抛。"""
        if not samples:
            return
        with self._connection_provider.connect() as connection:
            connection.executemany(
                """
                INSERT INTO person_face_embeddings (
                    id, person_id, observation_id, embedding, quality_score,
                    enabled, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(sample.id),
                        str(sample.person_id),
                        str(sample.observation_id),
                        json.dumps(list(sample.embedding.vector)),
                        sample.quality_score,
                        1 if sample.enabled else 0,
                        datetime_to_text(
                            sample.created_at if sample.created_at is not None
                            else datetime.now(),
                        ),
                    )
                    for sample in samples
                ],
            )

    def list_enabled(self) -> list[PersonFaceSample]:
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM person_face_embeddings WHERE enabled = 1 "
                "ORDER BY person_id, created_at, id",
            ).fetchall()
        return [_sample_from_row(row) for row in rows]

    def list_by_person(self, person_id: UUID) -> list[PersonFaceSample]:
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM person_face_embeddings WHERE person_id = ? "
                "ORDER BY created_at, id",
                (str(person_id),),
            ).fetchall()
        return [_sample_from_row(row) for row in rows]

    def disable_samples(
        self, person_id: UUID, observation_ids: Sequence[UUID],
    ) -> int:
        """Stage E（E-SG-5）：停用旧人员样本（历史保留，enabled=0）。"""
        unique_ids = list(dict.fromkeys(observation_ids))
        if not unique_ids:
            return 0
        placeholders = ", ".join("?" for _ in unique_ids)
        with self._connection_provider.connect() as connection:
            cursor = connection.execute(
                "UPDATE person_face_embeddings SET enabled = 0 "
                "WHERE person_id = ? AND enabled = 1 "
                f"AND observation_id IN ({placeholders})",
                (str(person_id), *(str(observation_id) for observation_id in unique_ids)),
            )
            return cursor.rowcount


def _sample_from_row(row) -> PersonFaceSample:
    return PersonFaceSample(
        id=UUID(row["id"]),
        person_id=UUID(row["person_id"]),
        observation_id=UUID(row["observation_id"]),
        embedding=FaceEmbedding(tuple(json.loads(row["embedding"]))),
        quality_score=row["quality_score"],
        enabled=bool(row["enabled"]),
        created_at=text_to_datetime(row["created_at"]),
    )
