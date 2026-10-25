"""Assignment → Projection 的唯一物化入口（S1）。

业务语义（S0 冻结；ADR-044 E-SG-6 的 ``(person, photo)`` 作用域不变）：

- **决策事实源 = ``cluster_person_assignments``**。一个 Cluster 的当前身份是它的
  最新一条决策事件（S0 INV-1），该事件的状态决定当前是否有人。
- **投影 = 当前有效决策的可重建物化结果**。``recognition_results`` 的 approved 行
  只是归档兼容投影（S0 INV-3），其存在性由「该 ``(photo, person)`` 是否仍有
  **active supporting Assignment**」决定——**不是**由 ``assignment_id`` 指向的
  那一条是否 active 决定。

``active_supports(photo, person)`` 可以包含多个 Assignment：同一张照片的不同脸
可能落进不同簇（S0-5 允许），这些簇可被指派给同一人；跨聚类代际同理。因此：

- 撤掉**一个**支撑 → 投影**保留**，仅把 ``assignment_id`` 重指向剩余支撑
  （retarget），绝不因单点失效而删除；
- 撤掉**最后一个**支撑 → 投影终结（``approved`` → ``rejected``，保留审计痕迹）。

**legacy 保护（最高优先级）**：``assignment_id IS NULL AND person_id IS NOT NULL``
的行是 ADR-045 D-1 的人工裁决，S0 INV-4 要求 machine 不得撤销 manual decision。
本模块每条查询都以 ``assignment_id IS NOT NULL`` 为门槛：legacy 行既不被读取也不
被终结。照片进入 Assignment 流水线**不构成**终结它的理由——合影里其他成员的
身份同样有效。

多人照片语义未被削弱：``(photo, A)`` 与 ``(photo, B)`` 是两个独立 pair，各自独立
reconcile，归档时各生成一份归档副本。
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from loguru import logger

from photo_archiver.domain.entities.cluster_assignment import (
    PROJECTION_SUPPORT_STATUSES,
    ClusterPersonAssignment,
)
from photo_archiver.domain.entities.face_cluster import FaceCluster
from photo_archiver.domain.entities.recognition import MatchStatus, RecognitionResult
from photo_archiver.domain.repositories.cluster_assignment_repository import (
    ClusterPersonAssignmentRepository,
)
from photo_archiver.domain.repositories.face_cluster_repository import (
    FaceClusterRepository,
)
from photo_archiver.domain.repositories.face_observation_repository import (
    FaceObservationRepository,
)
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.repositories.recognition_repository import (
    RecognitionRepository,
)

_EPOCH = datetime.min


def _assignment_id(assignment: ClusterPersonAssignment) -> UUID:
    """Return the assignment id, narrowing away the entity's optional declaration.

    ``ClusterPersonAssignment.__post_init__`` always assigns an id; the optional
    annotation only reflects that the field is passed positionally by dataclass
    generation.
    """
    if assignment.id is None:  # pragma: no cover - entity guarantees this
        raise ValidationError("ClusterPersonAssignment must carry an id")
    return assignment.id


@dataclass(frozen=True, slots=True)
class ReconcileOutcome:
    """Result of reconciling one ``(photo, person)`` pair."""

    action: str
    """``created`` | ``retargeted`` | ``restored`` | ``terminated`` | ``unchanged`` | ``noop``"""

    photo_id: UUID | None = None
    person_id: UUID | None = None
    assignment_id: UUID | None = None
    supports: int = 0


@dataclass(frozen=True, slots=True)
class RebuildReport:
    """Summary of a full projection rebuild (S1 Phase E)."""

    created: int = 0
    retargeted: int = 0
    restored: int = 0
    terminated: int = 0
    unchanged: int = 0
    legacy_preserved: int = 0
    pending_preserved: int = 0
    details: tuple[ReconcileOutcome, ...] = field(default_factory=tuple)


class ProjectionReconciler:
    """Materialize and reconcile ``recognition_results`` projections.

    The **only** component allowed to create / retarget / terminate
    Assignment-derived projections. Incremental updates and :meth:`rebuild_all`
    both go through :meth:`reconcile_pair`, so the two paths cannot drift apart.

    照片级忽略（界面优化 §3.2）：注入 ``photo_ignore_repository`` 后，
    ``(cluster_run_id, photo_id)`` 被忽略的照片在该代际内的所有支撑一律
    失效——``photos_of_cluster`` 不再为忽略照片产出投影目标，
    ``active_supports`` 不再统计来自忽略代际的支撑；其他代际/其他照片
    完全不受影响。未注入时行为与历史版本逐字一致（测试与旧库兼容）。
    """

    def __init__(
        self,
        recognition_repository: RecognitionRepository,
        assignment_repository: ClusterPersonAssignmentRepository,
        cluster_repository: FaceClusterRepository,
        observation_repository: FaceObservationRepository,
        photo_ignore_repository=None,
    ) -> None:
        self._recognition = recognition_repository
        self._assignments = assignment_repository
        self._clusters = cluster_repository
        self._observations = observation_repository
        self._ignores = photo_ignore_repository

    # ── 支撑查询 ──────────────────────────────────────────────────────

    def clusters_touching(self, photo_id: UUID) -> tuple[UUID, ...]:
        """Return every cluster holding at least one observation of ``photo_id``."""
        cluster_ids: list[UUID] = []
        for observation in self._observations.list_by_photo(photo_id):
            if not observation.embedding.vector:
                continue
            for cluster in self._clusters.list_clusters_of_observation(observation.id):
                if cluster.id is not None and cluster.id not in cluster_ids:
                    cluster_ids.append(cluster.id)
        return tuple(cluster_ids)

    @staticmethod
    def _support_sort_key(assignment: ClusterPersonAssignment) -> tuple:
        """Deterministic total order over supporting Assignments.

        Earliest confirmation wins (this identity was established first), then
        creation time, then id. A full order means ``reconcile_pair`` picks the
        same support on every run and in every process.
        """
        return (
            assignment.confirmed_at or _EPOCH,
            assignment.created_at or _EPOCH,
            str(assignment.id),
        )

    def active_supports(
        self, photo_id: UUID, person_id: UUID,
    ) -> tuple[ClusterPersonAssignment, ...]:
        """Return every current active Assignment supporting ``(photo, person)``.

        S1::

            A supports (photo, person)  iff
                A.person_id == person
                and photo ∈ photos(A.cluster)
                and A is that cluster's latest decision   (S0 INV-1)
                and A.status ∈ PROJECTION_SUPPORT_STATUSES

        界面优化 §3.2：照片在支撑簇所属聚类代际内被忽略时，该簇的支撑
        失效（其他代际的支撑照常统计）——被忽略照片不会因后续 reconcile
        意外恢复投影。
        """
        ignored_runs = self._ignored_runs_for_photo(photo_id)
        supports: list[ClusterPersonAssignment] = []
        for cluster_id in self.clusters_touching(photo_id):
            if ignored_runs is not None:
                cluster = self._clusters.get_cluster(cluster_id)
                if cluster is not None and cluster.cluster_run_id in ignored_runs:
                    continue
            latest = self._assignments.list_latest_decision(cluster_id)
            if latest is None or latest.person_id != person_id:
                continue
            if latest.status not in PROJECTION_SUPPORT_STATUSES:
                continue
            supports.append(latest)
        return tuple(sorted(supports, key=self._support_sort_key))

    def photos_of_cluster(self, cluster: FaceCluster) -> tuple[UUID, ...]:
        """Return the cluster's distinct photo ids, in stable order.

        Deduplicating by photo (not by observation) is what keeps a multi-face
        group photo from producing one projection per face — S0-5.

        界面优化 §3.2：该簇所属代际内被忽略的照片不产出——确认终审不会
        为忽略照片创建投影。
        """
        ignored = self._ignored_photo_ids(cluster.cluster_run_id)
        observations = {
            observation.id: observation
            for observation in self._observations.list_by_run(cluster.run_id)
        }
        photo_ids: list[UUID] = []
        for member in self._clusters.list_members(cluster.cluster_run_id):
            if member.cluster_id != cluster.id:
                continue
            observation = observations.get(member.observation_id)
            if observation is None or not observation.embedding.vector:
                continue
            if observation.photo_id in ignored:
                continue
            if observation.photo_id not in photo_ids:
                photo_ids.append(observation.photo_id)
        return tuple(photo_ids)

    # ── 物化 ──────────────────────────────────────────────────────────

    def reconcile_pair(self, photo_id: UUID, person_id: UUID) -> ReconcileOutcome:
        """Reconcile exactly one ``(photo, person)`` pair.

        ``supports > 0`` → the projection must exist and reference a live
        support. ``supports == 0`` → an Assignment-derived projection, if any,
        is terminated. Legacy rows are invisible here by construction.
        """
        supports = self.active_supports(photo_id, person_id)
        projection = self._recognition.find_projection(photo_id, person_id)

        if not supports:
            if projection is None:
                return ReconcileOutcome("noop", photo_id, person_id, None, 0)
            if projection.status is not MatchStatus.APPROVED:
                # Already terminated. The row keeps its assignment_id so that a
                # later re-confirmation restores it instead of losing the audit
                # trail; repeating the reconcile must be a no-op.
                return ReconcileOutcome(
                    "unchanged", photo_id, person_id, projection.assignment_id, 0
                )
            self._recognition.terminate_projection(projection.id)
            return ReconcileOutcome("terminated", photo_id, person_id, None, 0)

        chosen = _assignment_id(supports[0])
        if projection is None:
            self._recognition.create_projection(photo_id, person_id, chosen)
            return ReconcileOutcome("created", photo_id, person_id, chosen, len(supports))
        if projection.assignment_id not in {a.id for a in supports}:
            self._recognition.retarget_projection(projection.id, chosen)
            return ReconcileOutcome(
                "retargeted", photo_id, person_id, chosen, len(supports)
            )
        if projection.status is not MatchStatus.APPROVED:
            self._recognition.update_status(
                projection.id,
                MatchStatus.APPROVED,
                person_id=projection.person_id,
                assignment_id=projection.assignment_id,
            )
            return ReconcileOutcome("restored", photo_id, person_id, chosen, len(supports))
        return ReconcileOutcome("unchanged", photo_id, person_id, chosen, len(supports))

    def reconcile_cluster(self, cluster: FaceCluster) -> tuple[ReconcileOutcome, ...]:
        """Reconcile every ``(photo, person)`` pair this cluster's decision supports."""
        if cluster.id is None:  # pragma: no cover - entity guarantees this
            return ()
        latest = self._assignments.list_latest_decision(cluster.id)
        if latest is None or latest.person_id is None:
            return ()
        return tuple(
            self.reconcile_pair(photo_id, latest.person_id)
            for photo_id in self.photos_of_cluster(cluster)
        )

    def reconcile_person(
        self, person_id: UUID, photo_ids: Sequence[UUID],
    ) -> tuple[ReconcileOutcome, ...]:
        """Reconcile the given photos against one person (reassignment path)."""
        return tuple(self.reconcile_pair(photo_id, person_id) for photo_id in photo_ids)

    # ── 全量重建（S1 Phase E） ────────────────────────────────────────

    def expected_pairs(self) -> set[tuple[UUID, UUID]]:
        """Every ``(photo, person)`` pair supported by a current decision."""
        pairs: set[tuple[UUID, UUID]] = set()
        for cluster_run in self._clusters.list_all_cluster_runs():
            if cluster_run.id is None:  # pragma: no cover - entity guarantees
                continue
            for cluster in self._clusters.list_clusters(cluster_run.id):
                if cluster.id is None:  # pragma: no cover - entity guarantees
                    continue
                latest = self._assignments.list_latest_decision(cluster.id)
                if latest is None or latest.person_id is None:
                    continue
                if latest.status not in PROJECTION_SUPPORT_STATUSES:
                    continue
                for photo_id in self.photos_of_cluster(cluster):
                    pairs.add((photo_id, latest.person_id))
        return pairs

    def rebuild_all(self) -> RebuildReport:
        """Rebuild every Assignment-derived projection from Assignment state.

        Delegates each pair to :meth:`reconcile_pair`, so incremental and full
        rebuild are the same logic. Legacy (``assignment_id IS NULL``), pending
        and rejected rows are never read or written.
        """
        expected = self.expected_pairs()
        counters = {
            "created": 0, "retargeted": 0, "restored": 0,
            "terminated": 0, "unchanged": 0,
        }
        details: list[ReconcileOutcome] = []

        ordered = sorted(expected, key=lambda pair: (str(pair[0]), str(pair[1])))
        for photo_id, person_id in ordered:
            outcome = self.reconcile_pair(photo_id, person_id)
            counters[outcome.action] = counters.get(outcome.action, 0) + 1
            details.append(outcome)

        for projection in self._recognition.list_projections():
            if projection.person_id is None:
                continue
            pair = (projection.photo_id, projection.person_id)
            if pair in expected:
                continue
            outcome = self.reconcile_pair(pair[0], pair[1])
            counters[outcome.action] = counters.get(outcome.action, 0) + 1
            details.append(outcome)

        all_approved = self._recognition.list_all_approved()
        legacy_preserved = sum(1 for row in all_approved if row.assignment_id is None)
        pending_preserved = len(self._recognition.list_pending())

        logger.info(
            "ProjectionReconciler.rebuild_all: created={} retargeted={} restored={} "
            "terminated={} unchanged={} legacy_preserved={} pending_preserved={}",
            counters["created"], counters["retargeted"], counters["restored"],
            counters["terminated"], counters["unchanged"],
            legacy_preserved, pending_preserved,
        )
        return RebuildReport(
            created=counters["created"],
            retargeted=counters["retargeted"],
            restored=counters["restored"],
            terminated=counters["terminated"],
            unchanged=counters["unchanged"],
            legacy_preserved=legacy_preserved,
            pending_preserved=pending_preserved,
            details=tuple(details),
        )

    # ── 内部 ──────────────────────────────────────────────────────────

    def _ignored_photo_ids(self, cluster_run_id: UUID) -> set[UUID]:
        """Ignored photo ids of one generation; empty set when the port is absent."""
        if self._ignores is None:
            return set()
        return set(self._ignores.list_photo_ids(cluster_run_id))

    def _ignored_runs_for_photo(self, photo_id: UUID) -> set[UUID] | None:
        """Cluster-run ids where ``photo_id`` is ignored, or ``None`` when the
        ignore port is absent (keeps the historical no-filter behaviour)."""
        if self._ignores is None:
            return None
        return self._ignores.list_ignore_run_ids(photo_id)

    def _projection_or_none(
        self, photo_id: UUID, person_id: UUID,
    ) -> RecognitionResult | None:
        return self._recognition.find_projection(photo_id, person_id)