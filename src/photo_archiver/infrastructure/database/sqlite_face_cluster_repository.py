"""SQLite implementation of the face cluster repository interface（阶段 D）.

``parameters`` 以 JSON 文本存储聚类参数快照：``add_cluster_run`` 写入后，
``update_cluster_run`` 刻意不触碰该列（与 RecognitionRun 同约定）。
members 的 ``UNIQUE(cluster_id, observation_id)`` 从存储层杜绝重复归属；
observation / cluster / cluster run 删除均按 FK ON DELETE CASCADE 级联
（照片删除 → observations → members 逐级级联，cluster run 随 recognition
run 删除而级联）。
"""

import json
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from photo_archiver.domain.entities.face_cluster import (
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
)
from photo_archiver.domain.repositories.face_cluster_repository import (
    FaceClusterRepository,
)
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import (
    datetime_to_text,
    face_cluster_from_row,
    face_cluster_member_from_row,
    face_cluster_run_from_row,
)


class SQLiteFaceClusterRepository(FaceClusterRepository):
    """Persist cluster runs, clusters and memberships in SQLite."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def add_cluster_run(self, run: FaceClusterRun) -> None:
        """Insert a new cluster run row；重跑 = 新行，绝不覆盖旧 cluster run."""
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO face_cluster_runs (
                    id, recognition_run_id, status, algorithm_version, parameters,
                    cluster_count, member_count, excluded_count, error,
                    created_at, finished_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(run.id),
                    str(run.recognition_run_id),
                    run.status,
                    run.algorithm_version,
                    _parameters_json(run),
                    run.cluster_count,
                    run.member_count,
                    run.excluded_count,
                    run.error,
                    datetime_to_text(self._require_created_at(run)),
                    (
                        datetime_to_text(run.finished_at)
                        if run.finished_at is not None
                        else None
                    ),
                ),
            )

    def get_cluster_run(self, run_id: UUID) -> FaceClusterRun | None:
        """Return the cluster run or ``None`` when it does not exist."""
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM face_cluster_runs WHERE id = ?",
                (str(run_id),),
            ).fetchone()
        return face_cluster_run_from_row(row) if row is not None else None

    def update_cluster_run(self, run: FaceClusterRun) -> int:
        """Persist status/统计列/finished_at/error——刻意不更新 parameters."""
        with self._connection_provider.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE face_cluster_runs SET
                    status = ?,
                    cluster_count = ?,
                    member_count = ?,
                    excluded_count = ?,
                    error = ?,
                    finished_at = ?
                WHERE id = ?
                """,
                (
                    run.status,
                    run.cluster_count,
                    run.member_count,
                    run.excluded_count,
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

    def list_cluster_runs(self, recognition_run_id: UUID) -> list[FaceClusterRun]:
        """Return the recognition run's clustering executions, newest first."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM face_cluster_runs WHERE recognition_run_id = ? "
                "ORDER BY created_at DESC, id",
                (str(recognition_run_id),),
            ).fetchall()
        return [face_cluster_run_from_row(row) for row in rows]

    def add_clusters(self, clusters: Sequence[FaceCluster]) -> None:
        """批量 INSERT cluster（单连接单事务 executemany；空输入 no-op）."""
        if not clusters:
            return
        with self._connection_provider.connect() as connection:
            connection.executemany(
                """
                INSERT INTO face_clusters (
                    id, cluster_run_id, run_id, ordinal, member_count,
                    first_captured_at, sort_key, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(cluster.id),
                        str(cluster.cluster_run_id),
                        str(cluster.run_id),
                        cluster.ordinal,
                        cluster.member_count,
                        (
                            datetime_to_text(cluster.first_captured_at)
                            if cluster.first_captured_at is not None
                            else None
                        ),
                        cluster.sort_key,
                        cluster.status,
                        datetime_to_text(self._require_created_at(cluster)),
                    )
                    for cluster in clusters
                ],
            )

    def add_members(self, members: Sequence[FaceClusterMember]) -> None:
        """批量 INSERT 成员关系；唯一性违反即抛 IntegrityError（不落半批）."""
        if not members:
            return
        with self._connection_provider.connect() as connection:
            connection.executemany(
                """
                INSERT INTO face_cluster_members (
                    id, cluster_id, observation_id, source, confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(member.id),
                        str(member.cluster_id),
                        str(member.observation_id),
                        member.source,
                        member.confidence,
                        datetime_to_text(self._require_member_created_at(member)),
                    )
                    for member in members
                ],
            )

    def list_clusters(self, cluster_run_id: UUID) -> list[FaceCluster]:
        """Return the cluster run's clusters ordered by ``ordinal``."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM face_clusters WHERE cluster_run_id = ? ORDER BY ordinal",
                (str(cluster_run_id),),
            ).fetchall()
        return [face_cluster_from_row(row) for row in rows]

    def get_cluster(self, cluster_id: UUID) -> FaceCluster | None:
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM face_clusters WHERE id = ?", (str(cluster_id),),
            ).fetchone()
        return face_cluster_from_row(row) if row is not None else None

    def update_cluster_status(self, cluster_id: UUID, status: str) -> int:
        """Stage E：仅迁移 status 字段（词表校验在 FaceCluster 构造器）。"""
        # 构造器校验 status 词表——用一次读回校验，拒绝非法值。
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM face_clusters WHERE id = ?", (str(cluster_id),),
            ).fetchone()
        if row is None:
            return 0
        current = face_cluster_from_row(row)
        current.status = status  # 触发校验的位置：直接构造校验实例
        FaceCluster(
            cluster_run_id=current.cluster_run_id,
            run_id=current.run_id,
            ordinal=current.ordinal,
            member_count=current.member_count,
            sort_key=current.sort_key,
            status=status,
            first_captured_at=current.first_captured_at,
            id=current.id,
            created_at=current.created_at,
        )
        with self._connection_provider.connect() as connection:
            cursor = connection.execute(
                "UPDATE face_clusters SET status = ? WHERE id = ?",
                (status, str(cluster_id)),
            )
            return cursor.rowcount

    def list_all_cluster_runs(self) -> list[FaceClusterRun]:
        """S1：返回全部聚类代际（按创建序），供 projection 全量重建遍历。"""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM face_cluster_runs ORDER BY created_at, id",
            ).fetchall()
        return [face_cluster_run_from_row(row) for row in rows]

    def list_clusters_of_observation(
        self, observation_id: UUID,
    ) -> list[FaceCluster]:
        """S1：返回包含该观测的全部簇（跨代际，按簇序稳定排序）。"""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT face_clusters.* FROM face_clusters "
                "JOIN face_cluster_members ON face_cluster_members.cluster_id = face_clusters.id "
                "WHERE face_cluster_members.observation_id = ? "
                "ORDER BY face_clusters.created_at, face_clusters.id",
                (str(observation_id),),
            ).fetchall()
        return [face_cluster_from_row(row) for row in rows]

    def list_members(self, cluster_run_id: UUID) -> list[FaceClusterMember]:
        """Return the cluster run's memberships ordered by ``cluster ordinal, id``."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                """
                SELECT face_cluster_members.* FROM face_cluster_members
                JOIN face_clusters ON face_clusters.id = face_cluster_members.cluster_id
                WHERE face_clusters.cluster_run_id = ?
                ORDER BY face_clusters.ordinal, face_cluster_members.id
                """,
                (str(cluster_run_id),),
            ).fetchall()
        return [face_cluster_member_from_row(row) for row in rows]

    @staticmethod
    def _require_created_at(run: FaceClusterRun | FaceCluster) -> datetime:
        """Narrow type guard for the generated creation timestamp."""
        if run.created_at is None:
            raise ValueError("entity must have a creation timestamp")
        return run.created_at

    @staticmethod
    def _require_member_created_at(member: FaceClusterMember) -> datetime:
        """Narrow type guard for the generated membership timestamp."""
        if member.created_at is None:
            raise ValueError("membership must have a creation timestamp")
        return member.created_at


def _parameters_json(run: FaceClusterRun) -> str:
    """Serialize the immutable parameter snapshot (deterministic key order)."""
    return json.dumps(dict(run.parameters), ensure_ascii=False, sort_keys=True)
