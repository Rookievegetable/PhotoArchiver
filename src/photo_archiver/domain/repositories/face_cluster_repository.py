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

    def get_cluster(self, cluster_id: UUID) -> FaceCluster | None:
        """Return one cluster or ``None``（Stage E 指派操作的单簇读取）。"""

    def update_cluster_status(self, cluster_id: UUID, status: str) -> int:
        """Stage E：标记陌生人/忽略组的状态迁移（status 词表由实体校验）。

        只允许生命周期字段迁移，成员关系与排序字段不动（原始聚类数据
        不被破坏）。Returns 受影响行数（0 = cluster 不存在）。
        """

    def list_all_cluster_runs(self) -> list[FaceClusterRun]:
        """S1：返回全部聚类代际（按创建序），供 projection 全量重建遍历。

        Stage D/E 的 ``list_cluster_runs`` 需要一个 recognition run id，
        而 S1 的重建必须覆盖**所有**代际——包括历史 run 的簇（它们仍可能
        持有支撑当前身份的有效 Assignment）。
        """

    def update_cluster_member_count(self, cluster_id: UUID, member_count: int) -> int:
        """Persist a recomputed cluster member count（批次删除后的计数修正）.

        ``member_count`` 是**派生统计**：成员关系行被外键级联抹掉后该列会
        失真，删除服务必须按实际成员数回写，否则簇规模显示撒谎。

        Returns:
            1 on hit, 0 when the cluster id does not exist.
        """

    def update_cluster_run_member_count(
        self, cluster_run_id: UUID, member_count: int,
    ) -> int:
        """Persist a recomputed cluster run member count（代际级计数修正）.

        与 :meth:`update_cluster_member_count` 同源：代际的成员总数是各簇
        成员数之和，照片删除后必须同步回写。

        Returns:
            1 on hit, 0 when the cluster run id does not exist.
        """

    def remove_cluster_run(self, cluster_run_id: UUID) -> int:
        """Delete one clustering generation and its cascaded rows.

        外键语义：``face_clusters`` → ``face_cluster_members`` →
        ``cluster_person_assignments`` 逐级 CASCADE——删除代际会**连带删除**
        该代际的身份决策行（"决策行只增改不删"不变量在此路径上的显式例外，
        调用方必须先向用户披露该影响）。

        Returns:
            1 when the generation row was deleted, 0 when it does not exist.
        """

    def list_clusters_of_observation(
        self, observation_id: UUID,
    ) -> list[FaceCluster]:
        """S1：返回包含该观测的全部簇（跨代际）。

        ``face_cluster_members`` 的唯一性作用域是 ``(cluster_id, observation_id)``
        且索引非唯一，因此同一观测可出现在不同代际的不同簇里——这正是
        "同一 (photo, person) 被多个 Assignment 支撑"的来源之一。
        """
