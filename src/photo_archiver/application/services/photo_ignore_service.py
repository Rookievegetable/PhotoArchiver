"""Photo-level ignore/restore service — 界面优化 §3.1/§3.2/§3.3.

语义（Owner 冻结基线）：

- 忽略作用域 = ``(FaceClusterRun, photo_id)``：一张照片在一个聚类代际内
  的参与资格。忽略不是异常，也不是拒绝某个人员配对；同簇其他照片、
  Assignment 历史、其他代际完全不受影响。
- 忽略时同步撤销该照片在作用域内的既有归属投影：走
  :class:`ProjectionReconciler`（照片级忽略口径已内置于其支撑计算）——
  无其他代际支撑 → ``terminate_projection``（approved→rejected，保留审计）；
  仍有外部代际支撑 → retarget 保留投影。Assignment 决策行一律不改写。
- **逐项提交，允许部分成功**：每个照片项在独立事务（注入 UoW 时）内完成
  "状态写入 + 投影处理"，逐项报告成功/跳过/失败，不把部分成功报成整批。
- 恢复只删除忽略状态行（恢复参与后续归类的资格），**不**自动恢复此前
  撤销的投影；后续归属通过现有确认流程重新建立。
"""

from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.photo_ignore import (
    IgnorePhotosCommand,
    RestorePhotosCommand,
)
from photo_archiver.application.dtos.photo_ignore import (
    OUTCOME_FAILED,
    OUTCOME_IGNORED,
    OUTCOME_RESTORED,
    OUTCOME_SKIPPED,
    PhotoIgnoreOutcome,
    PhotoIgnoreResult,
)
from photo_archiver.application.ports import UnitOfWork
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
)
from photo_archiver.domain.entities.photo_ignore_state import PhotoIgnoreState
from photo_archiver.domain.repositories.cluster_assignment_repository import (
    ClusterPersonAssignmentRepository,
)
from photo_archiver.domain.repositories.face_cluster_repository import (
    FaceClusterRepository,
)
from photo_archiver.domain.repositories.face_observation_repository import (
    FaceObservationRepository,
)
from photo_archiver.domain.repositories.photo_ignore_state_repository import (
    PhotoIgnoreStateRepository,
)


class PhotoIgnoreService:
    """Ignore/restore photos per clustering generation with projection sync."""

    def __init__(
        self,
        photo_ignore_repository: PhotoIgnoreStateRepository,
        cluster_repository: FaceClusterRepository,
        observation_repository: FaceObservationRepository,
        assignment_repository: ClusterPersonAssignmentRepository,
        reconciler: ProjectionReconciler,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize the service with its ports.

        Args:
            photo_ignore_repository: The scoped ignore-state store.
            cluster_repository: Cluster run / cluster / member reads.
            observation_repository: Observation reads for photo↔run validation.
            assignment_repository: Latest-decision reads for projection persons.
            reconciler: The projection materialization outlet (ignore-aware).
            unit_of_work: Per-item transaction scope; ``None`` runs bare (tests).
        """
        self._ignores = photo_ignore_repository
        self._clusters = cluster_repository
        self._observations = observation_repository
        self._assignments = assignment_repository
        self._reconciler = reconciler
        self._unit_of_work = unit_of_work

    def ignore_photos(self, command: IgnorePhotosCommand) -> PhotoIgnoreResult:
        """Ignore photos one by one; each item commits independently."""
        outcomes = [
            self._ignore_one(command.cluster_run_id, photo_id)
            for photo_id in dict.fromkeys(command.photo_ids)
        ]
        result = PhotoIgnoreResult(
            cluster_run_id=command.cluster_run_id, outcomes=tuple(outcomes),
        )
        logger.info(
            "PhotoIgnoreService: run {} ignored={} skipped={} failed={} revoked={}",
            command.cluster_run_id, result.succeeded_count,
            result.skipped_count, result.failed_count, result.revoked_projections,
        )
        return result

    def restore_photos(self, command: RestorePhotosCommand) -> PhotoIgnoreResult:
        """Restore photos one by one; restores never touch projections."""
        outcomes = [
            self._restore_one(command.cluster_run_id, photo_id)
            for photo_id in dict.fromkeys(command.photo_ids)
        ]
        result = PhotoIgnoreResult(
            cluster_run_id=command.cluster_run_id, outcomes=tuple(outcomes),
        )
        logger.info(
            "PhotoIgnoreService: run {} restored={} skipped={} failed={}",
            command.cluster_run_id, result.succeeded_count,
            result.skipped_count, result.failed_count,
        )
        return result

    # ── 单项（逐项提交边界） ────────────────────────────────────────────

    def _ignore_one(self, cluster_run_id: UUID, photo_id: UUID) -> PhotoIgnoreOutcome:
        """One ignore item: state insert + scoped projection revocation."""
        def _operation() -> PhotoIgnoreOutcome:
            member_photo_ids = self._member_photo_ids(cluster_run_id)
            if photo_id not in member_photo_ids:
                return PhotoIgnoreOutcome(
                    photo_id, OUTCOME_SKIPPED, reason="photo has no cluster membership in this run",
                )
            if self._ignores.find(cluster_run_id, photo_id) is not None:
                return PhotoIgnoreOutcome(
                    photo_id, OUTCOME_SKIPPED, reason="already ignored",
                )
            self._ignores.add(PhotoIgnoreState(
                cluster_run_id=cluster_run_id, photo_id=photo_id,
            ))
            revoked = self._revoke_in_scope_projections(cluster_run_id, photo_id)
            return PhotoIgnoreOutcome(
                photo_id, OUTCOME_IGNORED, revoked_projections=revoked,
            )

        return self._run_item(photo_id, _operation)

    def _restore_one(self, cluster_run_id: UUID, photo_id: UUID) -> PhotoIgnoreOutcome:
        """One restore item: delete the state row; projections stay untouched."""
        def _operation() -> PhotoIgnoreOutcome:
            if self._ignores.find(cluster_run_id, photo_id) is None:
                return PhotoIgnoreOutcome(
                    photo_id, OUTCOME_SKIPPED, reason="not ignored",
                )
            self._ignores.remove(cluster_run_id, photo_id)
            return PhotoIgnoreOutcome(photo_id, OUTCOME_RESTORED)

        return self._run_item(photo_id, _operation)

    def _run_item(self, photo_id: UUID, operation) -> PhotoIgnoreOutcome:  # noqa: ANN001 - closure
        """Run one item inside its own transaction; failures stay per-item."""
        if self._unit_of_work is not None:
            try:
                with self._unit_of_work:
                    return operation()
            except Exception as exc:  # noqa: BLE001 - per-item boundary
                logger.warning("PhotoIgnoreService: photo {} item failed: {}", photo_id, exc)
                return PhotoIgnoreOutcome(photo_id, OUTCOME_FAILED, reason=str(exc))
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001 - per-item boundary
            logger.warning("PhotoIgnoreService: photo {} item failed: {}", photo_id, exc)
            return PhotoIgnoreOutcome(photo_id, OUTCOME_FAILED, reason=str(exc))

    # ── 作用域内支撑枚举与投影撤销 ──────────────────────────────────────

    def _member_photo_ids(self, cluster_run_id: UUID) -> set[UUID]:
        """Photo ids with at least one cluster membership in this run."""
        observations = {
            observation.id: observation
            for observation in self._observations.list_by_run(
                self._run_id_of(cluster_run_id),
            )
        }
        photo_ids: set[UUID] = set()
        for member in self._clusters.list_members(cluster_run_id):
            observation = observations.get(member.observation_id)
            if observation is not None and observation.embedding.vector:
                photo_ids.add(observation.photo_id)
        return photo_ids

    def _revoke_in_scope_projections(
        self, cluster_run_id: UUID, photo_id: UUID,
    ) -> int:
        """Reconcile ``(photo, person)`` pairs supported from this run only.

        忽略状态行已先行写入，reconciler 的支撑计算会跳过本代际——
        无外部支撑 → 终结投影（审计保留）；有外部代际支撑 → retarget。
        其他照片、其他人员的投影与全部 Assignment 行不受影响。
        """
        clusters_of_photo = self._clusters_of_photo(cluster_run_id, photo_id)
        persons: list[UUID] = []
        for cluster_id in clusters_of_photo:
            latest = self._assignments.list_latest_decision(cluster_id)
            if (
                latest is not None
                and latest.status == "confirmed"
                and latest.person_id is not None
                and latest.person_id not in persons
            ):
                persons.append(latest.person_id)
        return sum(
            1
            for person_id in persons
            if self._reconciler.reconcile_pair(photo_id, person_id).action == "terminated"
        )

    def _run_id_of(self, cluster_run_id: UUID) -> UUID:
        """Resolve the owning recognition run of one clustering generation."""
        cluster_run = self._clusters.get_cluster_run(cluster_run_id)
        if cluster_run is None:
            raise ValueError(f"FaceClusterRun {cluster_run_id} does not exist")
        return cluster_run.recognition_run_id

    def _clusters_of_photo(self, cluster_run_id: UUID, photo_id: UUID) -> list[UUID]:
        """Clusters of this run holding at least one observation of the photo."""
        observations = {
            observation.id: observation
            for observation in self._observations.list_by_run(
                self._run_id_of(cluster_run_id),
            )
        }
        run_observation_ids = {
            observation_id
            for observation_id, observation in observations.items()
            if observation.photo_id == photo_id
        }
        cluster_ids: list[UUID] = []
        for member in self._clusters.list_members(cluster_run_id):
            if (
                member.observation_id in run_observation_ids
                and member.cluster_id not in cluster_ids
            ):
                cluster_ids.append(member.cluster_id)
        return cluster_ids
