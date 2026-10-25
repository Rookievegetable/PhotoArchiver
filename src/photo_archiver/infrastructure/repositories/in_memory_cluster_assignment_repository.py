"""In-memory implementation of the assignment/sample repositories（阶段 E）.

镜像 SQLite 约束：UNIQUE(person_id, observation_id) 重复沉淀即
``ValueError``；排序键用 ``str(UUID)`` 对齐 TEXT 列字典序。cluster-run
范围解析经构造注入的 ``cluster_scope`` 委托（测试接线到 cluster 仓储的
``list_clusters``），不跨仓储实例偷看内部状态。
"""

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from uuid import UUID

from photo_archiver.domain.entities.cluster_assignment import (
    ClusterPersonAssignment,
    PersonFaceSample,
)
from photo_archiver.domain.entities.face_cluster import FaceCluster
from photo_archiver.domain.repositories.cluster_assignment_repository import (
    ClusterPersonAssignmentRepository,
    PersonFaceSampleRepository,
)


class InMemoryClusterPersonAssignmentRepository(ClusterPersonAssignmentRepository):
    """Store identity decisions in memory（测试替身）."""

    def __init__(
        self,
        cluster_scope: Callable[[UUID], Iterable[FaceCluster]] | None = None,
    ) -> None:
        """``cluster_scope(cluster_run_id)`` resolves a run's cluster ids."""
        self._assignments: dict[UUID, ClusterPersonAssignment] = {}
        self._cluster_scope = cluster_scope

    def add_assignments(self, assignments: Sequence[ClusterPersonAssignment]) -> None:
        for assignment in assignments:
            self._assignments[assignment.id] = assignment  # type: ignore[index]

    def get_assignment(self, assignment_id: UUID) -> ClusterPersonAssignment | None:
        return self._assignments.get(assignment_id)

    def update_assignment(self, assignment: ClusterPersonAssignment) -> int:
        if assignment.id not in self._assignments:
            return 0
        self._assignments[assignment.id] = assignment
        return 1

    def list_by_cluster(self, cluster_id: UUID) -> list[ClusterPersonAssignment]:
        rows = [
            assignment for assignment in self._assignments.values()
            if assignment.cluster_id == cluster_id
        ]
        return sorted(rows, key=lambda a: (a.created_at or a.id, str(a.id)), reverse=True)

    def list_latest_decision(self, cluster_id: UUID) -> ClusterPersonAssignment | None:
        """S0 INV-1：与 SQLite 实现同语义——取最新一条，与 status 无关。

        tie-break 必须与 SQLite 的 ``ORDER BY created_at DESC, id DESC`` 一致：
        ``created_at`` 相同则按 ``id`` 字符串序降序。
        """
        rows = [
            assignment for assignment in self._assignments.values()
            if assignment.cluster_id == cluster_id
        ]
        if not rows:
            return None
        return max(rows, key=lambda a: (a.created_at or datetime.min, str(a.id)))

    def list_by_cluster_run(self, cluster_run_id: UUID) -> list[ClusterPersonAssignment]:
        cluster_ids = self._cluster_ids_of_run(cluster_run_id)
        rows = [
            assignment for assignment in self._assignments.values()
            if assignment.cluster_id in cluster_ids
        ]
        return sorted(rows, key=lambda a: (a.created_at or a.id, str(a.id)), reverse=True)

    def list_active_by_cluster_run(self, cluster_run_id: UUID) -> list[ClusterPersonAssignment]:
        return [
            assignment for assignment in self.list_by_cluster_run(cluster_run_id)
            if assignment.status in ("suggested", "confirmed", "auto_confirmed")
        ]

    def list_rejected_pairs(self, cluster_run_id: UUID) -> list[tuple[UUID, UUID]]:
        cluster_ids = self._cluster_ids_of_run(cluster_run_id)
        return [
            (assignment.cluster_id, assignment.person_id)
            for assignment in self._assignments.values()
            if assignment.status == "rejected" and assignment.cluster_id in cluster_ids
            and assignment.person_id is not None
        ]

    def list_confirmed_person_ids(self, cluster_run_id: UUID) -> list[UUID]:
        cluster_ids = self._cluster_ids_of_run(cluster_run_id)
        return list({
            assignment.person_id
            for assignment in self._assignments.values()
            if assignment.status in ("confirmed", "auto_confirmed")
            and assignment.cluster_id in cluster_ids
            and assignment.person_id is not None
        })

    def _cluster_ids_of_run(self, cluster_run_id: UUID) -> set[UUID]:
        if self._cluster_scope is None:
            return set()
        return {
            cluster.id for cluster in self._cluster_scope(cluster_run_id)
            if cluster.id is not None
        }


class InMemoryPersonFaceSampleRepository(PersonFaceSampleRepository):
    """Store the person sample library in memory（测试替身）."""

    def __init__(self) -> None:
        self._samples: dict[UUID, PersonFaceSample] = {}

    def add_samples(self, samples: Sequence[PersonFaceSample]) -> None:
        existing = {
            (sample.person_id, sample.observation_id)
            for sample in self._samples.values()
        }
        batch_keys: set[tuple[UUID, UUID]] = set()
        for sample in samples:
            key = (sample.person_id, sample.observation_id)
            if key in existing or key in batch_keys:
                raise ValueError(
                    f"Duplicate person face sample for (person_id, observation_id) = {key}"
                )
            batch_keys.add(key)
        for sample in samples:
            self._samples[sample.id] = sample

    def list_enabled(self) -> list[PersonFaceSample]:
        return sorted(
            (sample for sample in self._samples.values() if sample.enabled),
            key=lambda sample: (str(sample.person_id), sample.created_at or sample.id,
                                str(sample.id)),
        )

    def list_by_person(self, person_id: UUID) -> list[PersonFaceSample]:
        return sorted(
            (sample for sample in self._samples.values() if sample.person_id == person_id),
            key=lambda sample: (sample.created_at or sample.id, str(sample.id)),
        )

    def disable_samples(
        self, person_id: UUID, observation_ids: Sequence[UUID],
    ) -> int:
        """Stage E（E-SG-5）：停用旧人员样本（历史保留，enabled=0）。"""
        targets = set(observation_ids)
        disabled = 0
        for sample in self._samples.values():
            if sample.person_id == person_id and sample.enabled and sample.observation_id in targets:
                replacement = PersonFaceSample(
                    person_id=sample.person_id,
                    observation_id=sample.observation_id,
                    embedding=sample.embedding,
                    quality_score=sample.quality_score,
                    enabled=False,
                    id=sample.id,
                    created_at=sample.created_at,
                )
                self._samples[sample.id] = replacement
                disabled += 1
        return disabled

    def enable_samples(
        self, person_id: UUID, observation_ids: Sequence[UUID],
    ) -> int:
        """界面优化 §7：恢复此前停用的样本（enabled 0 → 1，不产生新行）。"""
        targets = set(observation_ids)
        enabled = 0
        for sample in self._samples.values():
            if (
                sample.person_id == person_id
                and not sample.enabled
                and sample.observation_id in targets
            ):
                replacement = PersonFaceSample(
                    person_id=sample.person_id,
                    observation_id=sample.observation_id,
                    embedding=sample.embedding,
                    quality_score=sample.quality_score,
                    enabled=True,
                    id=sample.id,
                    created_at=sample.created_at,
                )
                self._samples[sample.id] = replacement
                enabled += 1
        return enabled
