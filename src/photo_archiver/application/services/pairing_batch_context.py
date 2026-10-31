"""批量终审会话快照（Owner 2026-10-31 卡顿修复·B）。

诊断结论（同日只读排查）：批量 confirm/assign 每确认一个簇，
``_sink_confirmation`` 与 ``photos_of_cluster`` 各自全量重载整代际的簇成员
与观测（观测行携带嵌入向量的 JSON 反序列化），N 个簇即 2N 次全代际加载——
O(簇数×代际规模) 的无效放大（Owner 实机 36 簇 ≈ 5.8 万行实体化 + 5.8 万次
向量 JSON 解析，全部在 UI 线程同步执行）。

而这三类读在本批操作下**不变**：簇成员、观测（扫描期数据）、忽略照片名单
（confirm/assign 不触碰）。:class:`PairingBatchContext` 据此把三者做成本批
一次加载的懒缓存，由调用方（任务层/对话框同步回退路径）在整批范围共享；
样本与投影的读写仍走各仓储实时路径，逐项事务边界不变。

``context=None``（缺省）保持逐项原行为——单簇操作与既有测试零变化。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from photo_archiver.domain.entities.face_cluster import FaceClusterMember
    from photo_archiver.domain.entities.face_observation import FaceObservation
    from photo_archiver.domain.repositories.face_cluster_repository import (
        FaceClusterRepository,
    )
    from photo_archiver.domain.repositories.face_observation_repository import (
        FaceObservationRepository,
    )


@dataclass
class PairingBatchContext:
    """One batch's read-only shared snapshot (lazy, per-generation caches)."""

    cluster_repository: "FaceClusterRepository"
    observation_repository: "FaceObservationRepository"
    ignored_provider: Callable[[UUID], "set[UUID] | frozenset[UUID]"]
    _members: dict[UUID, list["FaceClusterMember"]] = field(
        default_factory=dict, init=False, repr=False,
    )
    _observations: dict[UUID, dict[UUID, "FaceObservation"]] = field(
        default_factory=dict, init=False, repr=False,
    )
    _ignored: dict[UUID, frozenset[UUID]] = field(
        default_factory=dict, init=False, repr=False,
    )

    def members_of_run(self, cluster_run_id: UUID) -> list["FaceClusterMember"]:
        """All cluster members of the generation (loaded once per batch)."""
        if cluster_run_id not in self._members:
            self._members[cluster_run_id] = self.cluster_repository.list_members(
                cluster_run_id,
            )
        return self._members[cluster_run_id]

    def observations_by_id(self, run_id: UUID) -> dict[UUID, "FaceObservation"]:
        """The generation's observations keyed by id (loaded once per batch)."""
        if run_id not in self._observations:
            self._observations[run_id] = {
                observation.id: observation
                for observation in self.observation_repository.list_by_run(run_id)
            }
        return self._observations[run_id]

    def ignored_photo_ids(self, cluster_run_id: UUID) -> frozenset[UUID]:
        """The generation's ignored photo ids (loaded once per batch)."""
        if cluster_run_id not in self._ignored:
            self._ignored[cluster_run_id] = frozenset(
                self.ignored_provider(cluster_run_id),
            )
        return self._ignored[cluster_run_id]
