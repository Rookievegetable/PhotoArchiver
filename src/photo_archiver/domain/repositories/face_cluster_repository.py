"""Face cluster repository interface（阶段 D 第一阶段）.

写路径与 Stage C 同约定：cluster run 状态经 ``update_cluster_run`` 迁移，
``parameters`` 快照只在 ``add_cluster_run`` 落库、更新刻意不触碰；cluster
与 members 批量插入后即不可变（人工合并/拆分的追溯写入属后续阶段）。
"""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities.face_cluster import (
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
)


class FaceClusterRepository(Protocol):
    """Define persistence operations for cluster runs, clusters and members."""

    def add_cluster_run(self, run: FaceClusterRun) -> None:
        """Insert a new cluster run row；重跑 = 新行，绝不覆盖旧 cluster run。"""

    def get_cluster_run(self, run_id: UUID) -> FaceClusterRun | None:
        """Return the cluster run or ``None`` when it does not exist."""

    def update_cluster_run(self, run: FaceClusterRun) -> int:
        """Persist status/统计列/finished_at/error——刻意不更新 parameters。

        Returns:
            受影响行数（1 命中 / 0 不存在）。
        """

    def list_cluster_runs(self, recognition_run_id: UUID) -> list[FaceClusterRun]:
        """Return the recognition run's clustering executions, newest first."""

    def add_clusters(self, clusters: Sequence[FaceCluster]) -> None:
        """批量插入 cluster（单事务 executemany；空输入 no-op）。"""

    def add_members(self, members: Sequence[FaceClusterMember]) -> None:
        """批量插入成员关系；实现必须拒绝 ``(cluster_id, observation_id)`` 重复。"""

    def list_clusters(self, cluster_run_id: UUID) -> list[FaceCluster]:
        """Return the cluster run's clusters ordered by ``ordinal``."""

    def list_members(self, cluster_run_id: UUID) -> list[FaceClusterMember]:
        """Return the cluster run's memberships ordered by ``cluster ordinal, id``."""
