"""Cluster person assignment + person face sample repository interfaces（阶段 E）.

决策行只增改状态不删（历史可追溯）；样本库 UNIQUE(person_id,
observation_id) 由实现强制。
"""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities.cluster_assignment import (
    ClusterPersonAssignment,
    PersonFaceSample,
)


class ClusterPersonAssignmentRepository(Protocol):
    """Define persistence operations for identity decisions."""

    def add_assignments(self, assignments: Sequence[ClusterPersonAssignment]) -> None:
        """批量插入决策行（空输入 no-op）。"""

    def get_assignment(self, assignment_id: UUID) -> ClusterPersonAssignment | None:
        """Return the decision row or ``None``."""

    def update_assignment(self, assignment: ClusterPersonAssignment) -> int:
        """Persist status/score/confirmed_at/sort_snapshot——身份历史不删行。

        Returns:
            受影响行数（1 命中 / 0 不存在）。
        """

    def list_by_cluster(self, cluster_id: UUID) -> list[ClusterPersonAssignment]:
        """Return the cluster's decision history, newest first."""

    def list_by_cluster_run(self, cluster_run_id: UUID) -> list[ClusterPersonAssignment]:
        """Return every decision of one clustering generation, newest first."""

    def list_active_by_cluster_run(self, cluster_run_id: UUID) -> list[ClusterPersonAssignment]:
        """Return rows with status ∈ {suggested, confirmed}（当前有效行）。"""

    def list_rejected_pairs(self, cluster_run_id: UUID) -> list[tuple[UUID, UUID]]:
        """Return (cluster_id, person_id) pairs rejected within the generation."""

    def list_confirmed_person_ids(self, cluster_run_id: UUID) -> list[UUID]:
        """Return persons with a confirmed assignment in the generation."""


class PersonFaceSampleRepository(Protocol):
    """Define persistence operations for the person sample library."""

    def add_samples(self, samples: Sequence[PersonFaceSample]) -> None:
        """批量插入样本；实现必须拒绝 UNIQUE(person_id, observation_id) 重复。"""

    def list_enabled(self) -> list[PersonFaceSample]:
        """Return enabled samples（D4 匹配候选集）——确定性顺序。"""

    def disable_samples(
        self, person_id: UUID, observation_ids: Sequence[UUID],
    ) -> int:
        """Stage E（E-SG-5）：改派/解除后停用旧人员样本（历史保留 enabled=0）。

        停用样本不参与未来候选建议。Returns 停用行数（已停用的不重复计）。
        """

    def list_by_person(self, person_id: UUID) -> list[PersonFaceSample]:
        """Return one person's samples（含停用），确定性顺序。"""
