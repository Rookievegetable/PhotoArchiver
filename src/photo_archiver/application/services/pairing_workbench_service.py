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
from datetime import datetime, timedelta
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
    ManualDecisionProtectedError,
    FaceClusterRepository,
    FaceObservationRepository,
    PersonFaceSample,
    PersonRepository,
    ValidationError,
)
from photo_archiver.domain.entities.cluster_assignment import (
    ASSIGNMENT_SOURCE_MANUAL,
    ASSIGNMENT_STATUS_CONFIRMED,
    ACTIVE_ASSIGNMENT_STATUSES,
    HUMAN_ACTOR,
    MANUAL_ASSIGNMENT_SOURCES,
)
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
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

_ONE_MICROSECOND = timedelta(microseconds=1)


def _assert_mutable_by_machine(
    assignment: ClusterPersonAssignment, actor: str, operation: str,
) -> None:
    """S0 INV-4（P0-5）：机器操作不得修改/撤销人工身份决策。

    - ``actor == HUMAN_ACTOR`` → 放行：人工可以改派/解除任何来源的行，这是 INV-4
      允许的唯一覆盖路径（全部既有 UI 路径的缺省值）。
    - **其余一律按机器处理**（含 ``MACHINE_ACTOR`` 与任何拼错的字符串）——
      **fail-closed**：只有显式的 ``HUMAN_ACTOR`` 才获得人工权限。S4 的机器调用
      若忘记/写错 actor，会被当作机器而非被误当作人工。
    - 机器遇到 ``MANUAL_ASSIGNMENT_SOURCES``（manual / review）的行 → 拒绝。
    - **无论 source**：机器撤销 ``confirmed`` 行一律拒绝——confirmed 只能由人工
      动作产生（工作台原地确认产生 confirmed+machine source，见 PR-15；INV-6
      下无自动确认），其最终性来自"人工确认过"这一事实，不由 source 承载。
      决策历史一旦被机器改成 terminal，reconcile 重算支撑就会发现"无 active
      Assignment"并连带删除投影——INV-4 无法在投影层补救（运行时已实证），
      守卫必须在 mutation 层。机器可撤回的只有自己的 ``suggested`` 行。
    """
    if actor == HUMAN_ACTOR:
        return
    if assignment.source in MANUAL_ASSIGNMENT_SOURCES or (
        assignment.status == ASSIGNMENT_STATUS_CONFIRMED
    ):
        raise ManualDecisionProtectedError(
            f"{operation} refused: assignment {assignment.id} is a human-final "
            f"decision (source={assignment.source}, status={assignment.status})"
        )


def _next_created_at(previous: ClusterPersonAssignment | None) -> datetime:
    """Return a creation timestamp strictly after ``previous``.

    S0 INV-1 identifies the cluster's current identity by its **latest** decision
    row, ordered by ``(created_at DESC, id DESC)``. When two decisions land in the
    same clock tick the tie-break falls to the random UUID and the "latest" row
    becomes arbitrary — which silently made a retraction skip the row it was meant
    to retract. Bumping by one microsecond keeps the order total without needing
    a sequence column.
    """
    now = datetime.now()
    if previous is None or previous.created_at is None:
        return now
    return max(now, previous.created_at + _ONE_MICROSECOND)


def clamp_unit(score: float) -> float:
    """Clamp a similarity score into the ``[0.0, 1.0]`` recognition band.

    ``RecognitionResult.confidence`` stores *similarity evidence*; cosine may
    land slightly outside the unit range, so it is clamped. Callers pass
    ``None`` through untouched to mean "no similarity evidence" (Stage 4
    BLK-5) rather than fabricating a ``0.0``.
    """
    return max(0.0, min(1.0, score))


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
        reconciler: ProjectionReconciler | None = None,
    ) -> None:
        self._assignment_repository = assignment_repository
        self._cluster_repository = cluster_repository
        self._observation_repository = observation_repository
        self._person_repository = person_repository
        self._recognition_repository = recognition_repository
        self._sample_repository = sample_repository
        # S1：投影的唯一物化出口。缺省构造让纯服务层测试与既有装配保持兼容。
        self._reconciler = reconciler or ProjectionReconciler(
            recognition_repository=recognition_repository,
            assignment_repository=assignment_repository,
            cluster_repository=cluster_repository,
            observation_repository=observation_repository,
        )

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

    def unassign(
        self, command: UnassignClusterCommand, actor: str = HUMAN_ACTOR,
    ) -> PairingOperationResult:
        """解除映射/撤销：最新一条未 unassigned 行 → unassigned（历史保留）。

        覆盖 suggested（撤回建议）、confirmed（解除映射）与 rejected
        （撤销拒绝）三种入口——全部是该行状态机的合法迁移。

        ``actor``（S0 INV-4 / P0-5）：默认 :data:`HUMAN_ACTOR`（UI 按钮路径）。
        机器侧调用**必须**显式传 :data:`MACHINE_ACTOR`——任何非 human 值都被
        守卫当作机器（fail-closed），机器不得撤销人工最终决策。
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
        _assert_mutable_by_machine(target, actor, "unassign")
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

    def assign_person(
        self, command: AssignClusterPersonCommand, actor: str = HUMAN_ACTOR,
    ) -> PairingOperationResult:
        """Manually assign a person; the explicit choice is a confirmation.

        ``actor``（S0 INV-4 / P0-5）：改派会**终态化**当前有效行——机器 actor
        遇到人工最终决策必须拒绝；human 不受限（人工再修改是 INV-4 允许的唯一
        覆盖路径）。机器调用**必须**显式传 :data:`MACHINE_ACTOR`。
        """
        cluster = self._require_cluster(command.cluster_id)
        person = self._require_person(command.person_id)
        # S0 INV-1：先取**最新决策事件**（不论状态）。它既是替换目标（若仍active），
        # 也是新行时间戳的基准——用 latest 而非 active：撤回后 latest 已是terminal，
        # 只看 active 会退回 datetime.now()，可能与既有行同刻，tie-break 于是退化为
        # 随机 UUID，"最新决策"变成任意行。
        latest = self._assignment_repository.list_latest_decision(command.cluster_id)
        active = latest
        if active is not None and active.status not in ACTIVE_ASSIGNMENT_STATUSES:
            active = None
        if active is not None:
            _assert_mutable_by_machine(active, actor, "assign_person(retire)")
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
            created_at=_next_created_at(latest),
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
        """S0 INV-1：当前身份 = 最新一条决策事件；若其状态非 ACTIVE 则视为无人。

        S1 修复 P0-3：旧实现先按 ``ORDER BY created_at DESC`` 取历史、再过滤
        ACTIVE，因此 ``confirmed → unassigned`` 之后会跳过新的 unassigned 行、
        重新读出已终态化的旧 confirmed。``list_latest_decision`` 与 status 无关地
        先取最新行，语义才正确。
        """
        latest = self._assignment_repository.list_latest_decision(cluster_id)
        if latest is None or latest.status not in ACTIVE_ASSIGNMENT_STATUSES:
            return None
        return latest

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

        # D3 兼容适配（S1）：投影改由 ProjectionReconciler 物化。
        # 与旧的 ``already_current`` 幂等判断语义等价，但判定依据从「该照片是否已有
        # 该 person 的 APPROVED 行」换成「该 (photo, person) 是否仍有 active
        # supporting Assignment」——后者才能正确处理「多 Assignment 支撑同一 pair」
        # （撤掉一个支撑不得删除投影）。
        # Stage 4 BLK-5：confidence 语义不变——reconciler 为 sample_match 保留
        # 真实余弦，为位次配对/人工指派写 NULL（无相似度证据，不是 0.0）。
        compat_written = sum(
            1
            for photo_id in self._reconciler.photos_of_cluster(cluster)
            if self._reconciler.reconcile_pair(photo_id, person_id).action == "created"
        )
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
        photo_ids = list(self._reconciler.photos_of_cluster(cluster))
        # S1：不再按 (person_id, photo_id) 毯式 DELETE。撤销一个 Assignment 只代表
        # 少了一个支撑；该 pair 若仍被其他 active Assignment 支撑（例如同一照片的
        # 另一张脸落进另一个簇且同指此人），投影必须保留——这正是 P0-1 的成因。
        # legacy 行（assignment_id IS NULL）被 reconciler 完全排除，S0 INV-4 保护
        # 的人工决策不受解除映射影响。
        retracted = sum(
            1
            for photo_id in photo_ids
            if self._reconciler.reconcile_pair(photo_id, person_id).action == "terminated"
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
