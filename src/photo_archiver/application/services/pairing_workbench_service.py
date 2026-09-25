"""Pairing workbench service — Stage E 身份指派操作与确认链路.

操作集（方案 §6 工作台动作的身份子集；合并/拆分组属 Stage D 后续）：

- **确认建议**：suggested → confirmed + sort_snapshot（§5.3 排序快照）
  + 兼容适配（D3 裁决：向 ``recognition_results`` 写 APPROVED，确认即可
  归档）+ 样本沉淀（从组成员观测写 ``person_face_embeddings``，D4 匹配
  候选集）。
- **人工拒绝**：suggested → rejected（后续建议排除该 (组, 人) 对）。
- **解除映射**：有效行 → unassigned（改派/撤销的前置），历史行保留。
- **人工改派/新增指派**：人工明确选择即确认（source=manual, status=
  confirmed），旧有效行转 unassigned。
- **标记陌生人 / 忽略组**：cluster 状态 → unknown / ignored（Stage D
  实体词表内迁移，成员关系与排序不动）。

原始 Cluster/Observation 数据（成员关系、排序、观测）在任何操作下都不
被修改——只有 decision 行、cluster 生命周期字段与派生数据（兼容结果、
样本库）变化。
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.pairing import (
    AssignClusterPersonCommand,
    ConfirmAssignmentCommand,
    RejectAssignmentCommand,
    SetClusterStateCommand,
    UnassignClusterCommand,
)
from photo_archiver.domain import (
    ClusterPersonAssignment,
    FaceClusterRepository,
    FaceObservationRepository,
    MatchStatus,
    PersonFaceSample,
    PersonRepository,
    RecognitionResult,
    ValidationError,
)
from photo_archiver.domain.entities.cluster_assignment import (
    ASSIGNMENT_SOURCE_MANUAL,
    ACTIVE_ASSIGNMENT_STATUSES,
)
from photo_archiver.domain.entities.face_cluster import (
    CLUSTER_STATUS_IGNORED,
    CLUSTER_STATUS_UNKNOWN,
)
from photo_archiver.domain.repositories.cluster_assignment_repository import (
    ClusterPersonAssignmentRepository,
    PersonFaceSampleRepository,
)
from photo_archiver.domain.repositories.recognition_repository import RecognitionRepository


@dataclass(frozen=True, slots=True)
class PairingOperationResult:
    """Outcome of one workbench operation（追溯用）。"""

    assignment_id: UUID | None
    status: str
    compat_results_written: int = 0
    samples_written: int = 0


class PairingWorkbenchService:
    """Execute identity-assignment decisions over cluster generations."""

    def __init__(
        self,
        assignment_repository: ClusterPersonAssignmentRepository,
        cluster_repository: FaceClusterRepository,
        observation_repository: FaceObservationRepository,
        person_repository: PersonRepository,
        recognition_repository: RecognitionRepository,
        sample_repository: PersonFaceSampleRepository,
    ) -> None:
        self._assignment_repository = assignment_repository
        self._cluster_repository = cluster_repository
        self._observation_repository = observation_repository
        self._person_repository = person_repository
        self._recognition_repository = recognition_repository
        self._sample_repository = sample_repository

    def get_assignment(self, assignment_id: UUID) -> ClusterPersonAssignment | None:
        """Read one decision row（UI 追溯展示用）。"""
        return self._assignment_repository.get_assignment(assignment_id)

    # ── 确认建议 ────────────────────────────────────────────────────────

    def confirm(self, command: ConfirmAssignmentCommand) -> PairingOperationResult:
        """Confirm one suggested assignment; sinks samples + compat results."""
        assignment = self._require_assignment(command.assignment_id)
        if assignment.status != "suggested":
            raise ValidationError(
                f"Only suggested assignments can be confirmed, got {assignment.status}"
            )
        cluster = self._require_cluster(assignment.cluster_id)
        person = self._require_person(assignment.person_id)
        snapshot = {
            "sort_key": cluster.sort_key,
            "first_captured_at": (
                cluster.first_captured_at.isoformat()
                if cluster.first_captured_at is not None else None
            ),
            "confirmed_at": datetime.now().isoformat(),
        }
        assignment.confirm(snapshot)
        if self._assignment_repository.update_assignment(assignment) != 1:
            raise ValidationError(
                f"Assignment {assignment.id} no longer exists (concurrent delete)"
            )
        result = self._sink_confirmation(assignment, cluster, person.id)
        logger.info(
            "PairingWorkbenchService: assignment {} confirmed to person {}",
            assignment.id, person.id,
        )
        return PairingOperationResult(
            assignment_id=assignment.id,
            status=assignment.status,
            compat_results_written=result[0],
            samples_written=result[1],
        )

    # ── 拒绝 / 解除 ─────────────────────────────────────────────────────

    def reject(self, command: RejectAssignmentCommand) -> PairingOperationResult:
        """Reject one suggested assignment（后续建议排除该对）。"""
        assignment = self._require_assignment(command.assignment_id)
        assignment.reject()
        if self._assignment_repository.update_assignment(assignment) != 1:
            raise ValidationError(
                f"Assignment {assignment.id} no longer exists (concurrent delete)"
            )
        return PairingOperationResult(assignment_id=assignment.id, status=assignment.status)

    def unassign(self, command: UnassignClusterCommand) -> PairingOperationResult:
        """解除映射/撤销：最新一条未 unassigned 行 → unassigned（历史保留）。

        覆盖 suggested（撤回建议）、confirmed（解除映射）与 rejected
        （撤销拒绝）三种入口——全部是该行状态机的合法迁移。
        """
        history = self._assignment_repository.list_by_cluster(command.cluster_id)
        target = next(
            (assignment for assignment in history
             if assignment.status != "unassigned"),
            None,
        )
        if target is None:
            raise ValidationError(
                f"Cluster {command.cluster_id} has no assignable decision"
            )
        target.unassign()
        if self._assignment_repository.update_assignment(target) != 1:
            raise ValidationError(
                f"Assignment {target.id} no longer exists (concurrent delete)"
            )
        retracted = 0
        if target.person_id is not None:
            cluster = self._cluster_repository.get_cluster(target.cluster_id)
            if cluster is not None:
                retracted = self._retract_confirmation(cluster, target.person_id)
        return PairingOperationResult(
            assignment_id=target.id,
            status=target.status,
            compat_results_written=retracted,
        )

    # ── 人工改派 / 新增指派 ─────────────────────────────────────────────

    def assign_person(self, command: AssignClusterPersonCommand) -> PairingOperationResult:
        """Manually assign a person; the explicit choice is a confirmation."""
        cluster = self._require_cluster(command.cluster_id)
        person = self._require_person(command.person_id)
        active = self._active_assignment(command.cluster_id)
        if active is not None:
            active.unassign()
            if self._assignment_repository.update_assignment(active) != 1:
                raise ValidationError(
                    f"Assignment {active.id} no longer exists (concurrent delete)"
                )
            # E-P1-2（E-SG-6 #7）：旧身份的兼容投影与样本随改派同步回收，
            # 不影响其他 (person, photo) 归属（E-SG-6 #4/#7）。
            if active.person_id is not None:
                self._retract_confirmation(cluster, active.person_id)
        assignment = ClusterPersonAssignment(
            cluster_id=command.cluster_id,
            person_id=command.person_id,
            source=ASSIGNMENT_SOURCE_MANUAL,
        )
        self._assignment_repository.add_assignments([assignment])
        snapshot = {
            "sort_key": cluster.sort_key,
            "first_captured_at": (
                cluster.first_captured_at.isoformat()
                if cluster.first_captured_at is not None else None
            ),
            "confirmed_at": datetime.now().isoformat(),
        }
        assignment.confirm(snapshot)
        if self._assignment_repository.update_assignment(assignment) != 1:
            raise ValidationError(
                f"Assignment {assignment.id} no longer exists (concurrent delete)"
            )
        compat, samples = self._sink_confirmation(assignment, cluster, person.id)
        logger.info(
            "PairingWorkbenchService: cluster {} manually assigned to person {}",
            command.cluster_id, person.id,
        )
        return PairingOperationResult(
            assignment_id=assignment.id,
            status=assignment.status,
            compat_results_written=compat,
            samples_written=samples,
        )

    # ── 标记陌生人 / 忽略 ───────────────────────────────────────────────

    def set_cluster_state(self, command: SetClusterStateCommand) -> PairingOperationResult:
        """Mark a cluster unknown (陌生人) or ignored, via the Stage D vocabulary."""
        if command.state not in (CLUSTER_STATUS_UNKNOWN, CLUSTER_STATUS_IGNORED):
            raise ValidationError(
                f"Cluster state must be '{CLUSTER_STATUS_UNKNOWN}' or "
                f"'{CLUSTER_STATUS_IGNORED}', got {command.state!r}"
            )
        if self._cluster_repository.update_cluster_status(
            command.cluster_id, command.state,
        ) != 1:
            raise ValidationError(f"Cluster {command.cluster_id} does not exist")
        return PairingOperationResult(assignment_id=None, status=command.state)

    # ── 内部 ────────────────────────────────────────────────────────────

    def _require_assignment(self, assignment_id: UUID) -> ClusterPersonAssignment:
        assignment = self._assignment_repository.get_assignment(assignment_id)
        if assignment is None:
            raise ValidationError(f"Assignment {assignment_id} does not exist")
        return assignment

    def _require_cluster(self, cluster_id: UUID):
        cluster = self._cluster_repository.get_cluster(cluster_id)
        if cluster is None:
            raise ValidationError(f"Cluster {cluster_id} does not exist")
        return cluster

    def _require_person(self, person_id: UUID | None):
        if person_id is None:
            raise ValidationError("Assignment has no person to confirm")
        person = self._person_repository.find_by_id(person_id)
        if person is None:
            raise ValidationError(f"Person {person_id} does not exist")
        return person

    def _active_assignment(self, cluster_id: UUID) -> ClusterPersonAssignment | None:
        history = self._assignment_repository.list_by_cluster(cluster_id)
        return next(
            (assignment for assignment in history
             if assignment.status in ACTIVE_ASSIGNMENT_STATUSES),
            None,
        )

    def _sink_confirmation(self, assignment, cluster, person_id: UUID) -> tuple[int, int]:
        """D3 兼容适配 + D4 样本沉淀；返回 (compat_results, samples) 计数。"""
        members = [
            member for member in self._cluster_repository.list_members(
                cluster.cluster_run_id,
            )
            if member.cluster_id == cluster.id
        ]
        observations = {
            observation.id: observation
            for observation in self._observation_repository.list_by_run(
                cluster.run_id,
            )
        }
        member_observations = [
            observations[member.observation_id]
            for member in members
            if member.observation_id in observations
            and observations[member.observation_id].embedding.vector
        ]

        # D4 样本沉淀：成员观测 → person_face_embeddings（跳过已沉淀对）。
        existing = {
            sample.observation_id
            for sample in self._sample_repository.list_by_person(person_id)
        }
        new_samples = [
            PersonFaceSample(
                person_id=person_id,
                observation_id=observation.id,
                embedding=observation.embedding,
                quality_score=observation.quality_score,
            )
            for observation in member_observations
            if observation.id not in existing
        ]
        self._sample_repository.add_samples(new_samples)

        # D3 兼容适配（E-SG-6）：同一 (person, photo) 至多一条当前有效
        # APPROVED 归属；不同 person 的同照片归属互不覆盖（E-P1-1）。
        compat_written = 0
        seen_photos: set[UUID] = set()
        confidence = max(0.0, min(1.0, assignment.score or 0.0))
        for observation in member_observations:
            if observation.photo_id in seen_photos:
                continue
            seen_photos.add(observation.photo_id)
            existing_results = self._recognition_repository.list_by_photo(
                observation.photo_id,
            )
            already_current = any(
                result.status == MatchStatus.APPROVED
                and result.person_id == person_id
                for result in existing_results
            )
            if already_current:
                continue
            self._recognition_repository.add(RecognitionResult(
                photo_id=observation.photo_id,
                person_id=person_id,
                confidence=confidence,
                status=MatchStatus.APPROVED,
            ))
            compat_written += 1
        return compat_written, len(new_samples)

    def _retract_confirmation(self, cluster, person_id: UUID) -> int:
        """E-P1-2（E-SG-6 #7）：回收 (person, 簇成员照片) 的兼容投影并停用样本.

        兼容层是当前指派的投影（主事实原则）：改派/解除时移除旧 person 的
        APPROVED 行、停用其样本（历史保留 enabled=0）。其他 (person,
        photo) 归属不受影响。
        """
        observations = self._observations_by_run(cluster.run_id)
        member_observations = [
            observations[member.observation_id]
            for member in self._cluster_repository.list_members(cluster.cluster_run_id)
            if member.cluster_id == cluster.id
            and member.observation_id in observations
            and observations[member.observation_id].embedding.vector
        ]
        photo_ids = list(dict.fromkeys(o.photo_id for o in member_observations))
        retracted = self._recognition_repository.remove_results_for_person_photos(
            person_id, photo_ids,
        )
        self._sample_repository.disable_samples(
            person_id, [o.id for o in member_observations],
        )
        logger.info(
            "PairingWorkbenchService: retracted compat for person {} over {} photo(s) "
            "of cluster {}",
            person_id, len(photo_ids), cluster.id,
        )
        return retracted

    def _observations_by_run(self, run_id: UUID) -> dict:
        return {
            observation.id: observation
            for observation in self._observation_repository.list_by_run(run_id)
        }
