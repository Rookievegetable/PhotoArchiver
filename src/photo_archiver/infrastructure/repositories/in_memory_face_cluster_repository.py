"""In-memory implementation of the face cluster repository interface（阶段 D）.

镜像 SQLite 的约束语义：``UNIQUE(cluster_id, observation_id)`` 重复归属
即 ``ValueError``（对应 SQLite IntegrityError），排序键用 ``str(UUID)``
以对齐 SQLite TEXT 列的字典序。
"""

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


class InMemoryFaceClusterRepository(FaceClusterRepository):
    """Store cluster runs, clusters and memberships in memory（测试替身）."""

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._cluster_runs: dict[UUID, FaceClusterRun] = {}
        self._clusters: dict[UUID, FaceCluster] = {}
        self._members: dict[UUID, FaceClusterMember] = {}

    def add_cluster_run(self, run: FaceClusterRun) -> None:
        """Insert a new cluster run row（重跑 = 新行）."""
        self._cluster_runs[run.id] = run  # type: ignore[index]  # entity always has an id

    def get_cluster_run(self, run_id: UUID) -> FaceClusterRun | None:
        """Return the cluster run or ``None``."""
        return self._cluster_runs.get(run_id)

    def update_cluster_run(self, run: FaceClusterRun) -> int:
        """Persist status/统计 in place; 0 when the run does not exist."""
        if run.id not in self._cluster_runs:
            return 0
        self._cluster_runs[run.id] = run
        return 1

    def list_cluster_runs(self, recognition_run_id: UUID) -> list[FaceClusterRun]:
        """Return the recognition run's clustering executions, newest first."""
        runs = [
            run for run in self._cluster_runs.values()
            if run.recognition_run_id == recognition_run_id
        ]
        return sorted(
            runs,
            key=lambda run: (run.created_at or run.id, str(run.id)),
            reverse=True,
        )

    def add_clusters(self, clusters: Sequence[FaceCluster]) -> None:
        """批量插入 cluster；空输入 no-op。"""
        for cluster in clusters:
            self._clusters[cluster.id] = cluster  # type: ignore[index]

    def add_members(self, members: Sequence[FaceClusterMember]) -> None:
        """批量插入成员关系；唯一性冲突整体拒绝（不落半批）。"""
        existing_keys = {
            (member.cluster_id, member.observation_id)
            for member in self._members.values()
        }
        batch_keys: set[tuple[UUID, UUID]] = set()
        for member in members:
            key = (member.cluster_id, member.observation_id)
            if key in existing_keys or key in batch_keys:
                raise ValueError(
                    f"Duplicate cluster membership for (cluster_id, observation_id) = {key}"
                )
            batch_keys.add(key)
        for member in members:
            self._members[member.id] = member

    def list_clusters(self, cluster_run_id: UUID) -> list[FaceCluster]:
        """Return the cluster run's clusters ordered by ``ordinal``."""
        return sorted(
            (
                cluster for cluster in self._clusters.values()
                if cluster.cluster_run_id == cluster_run_id
            ),
            key=lambda cluster: cluster.ordinal,
        )

    def get_cluster(self, cluster_id: UUID) -> FaceCluster | None:
        return self._clusters.get(cluster_id)

    def update_cluster_status(self, cluster_id: UUID, status: str) -> int:
        """Stage E：仅迁移 status 字段（词表校验在 FaceCluster 构造器）。"""
        cluster = self._clusters.get(cluster_id)
        if cluster is None:
            return 0
        cluster.status = status  # 实体不做迁移校验——构造校验实例拒绝非法词
        FaceCluster(
            cluster_run_id=cluster.cluster_run_id,
            run_id=cluster.run_id,
            ordinal=cluster.ordinal,
            member_count=cluster.member_count,
            sort_key=cluster.sort_key,
            status=status,
            first_captured_at=cluster.first_captured_at,
            id=cluster.id,
            created_at=cluster.created_at,
        )
        return 1

    def list_all_cluster_runs(self) -> list[FaceClusterRun]:
        """S1：全部聚类代际，按创建序（与 SQLite 的 ORDER BY created_at, id 对齐）。"""
        return sorted(
            self._cluster_runs.values(),
            key=lambda run: (run.created_at or datetime.min, str(run.id)),
        )

    def list_clusters_of_observation(
        self, observation_id: UUID,
    ) -> list[FaceCluster]:
        """S1：包含该观测的全部簇（跨代际）。"""
        cluster_ids = {
            member.cluster_id
            for member in self._members.values()
            if member.observation_id == observation_id
        }
        return sorted(
            (cluster for cluster in self._clusters.values() if cluster.id in cluster_ids),
            key=lambda cluster: (cluster.created_at or datetime.min, str(cluster.id)),
        )

    def list_members(self, cluster_run_id: UUID) -> list[FaceClusterMember]:
        """Return the cluster run's memberships ordered by ``cluster ordinal, id``."""
        cluster_ordinal = {
            cluster.id: cluster.ordinal
            for cluster in self.list_clusters(cluster_run_id)
        }
        return sorted(
            (
                member for member in self._members.values()
                if member.cluster_id in cluster_ordinal
            ),
            key=lambda member: (cluster_ordinal[member.cluster_id], str(member.id)),
        )
