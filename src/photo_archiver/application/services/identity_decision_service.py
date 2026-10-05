"""审核中心身份决策的唯一入口（S1-F）。

业务语义（S0 冻结 + D-2 = B，Owner 裁决 2026-10-02）：

- **决策事实源 = ``cluster_person_assignments``**（S0 INV-3）。审核「通过并指定
  人员」是一次**人工身份决策**，必须产生 ``Assignment(source='review',
  status='confirmed')``，与人工指派同等最终（S0 INV-4）。
- **D-2 = B（冻结）**：Review 只能批准**已聚类**的照片——照片至少存在一个有效
  ``FaceObservation`` 且该观测已进入 ``face_cluster_members``。未聚类照片
  fail-closed：抛 :class:`PhotoNotClusteredError`，不创建簇、不创建 Assignment、
  不创建 projection、pending 行保持原状。
- **决策锚点（无隐式推断）**：Review 的输入是照片粒度 ``(photo, person)``，
  而 Assignment 是簇粒度 ``(cluster, person)``。锚定规则**只**依据"最新聚类代际
  中该照片落入多少个簇"：恰 1 个 → 自动锚定；≥2 个 → 抛
  :class:`ReviewAnchorAmbiguousError` fail-closed，除非命令显式携带
  ``cluster_id``。**禁止**用 det_score Top-1 之类猜测人脸归属——实测反例：
  C1→A 已确认时按 Top-1 批准 B 会把 C1 错改成 B。合影的逐簇身份决策属配对工作台
  （其 UI 本就是簇粒度）。
- **状态机复用**（不重定义既有状态，但不复用行）：
  - 最新决策已 ``confirmed`` 且指向同一人 → **幂等**：只确保投影存在，不新建；
  - 该簇存在任何 active 决策（``suggested`` 同人或他人、``confirmed`` 他人）→
    人工终态化旧行（actor=human）→ **新建** ``review`` 行；旧人样本按 E-SG-5
    停用，投影经 reconcile 按支撑重算。
  - **不复用机器建议行的原因**：``source`` 是 immutable 契约（``update_assignment``
    不写 source 列）。原地 ``suggested → confirmed`` 会产出
    ``confirmed + machine source``，落在 ``MANUAL_ASSIGNMENT_SOURCES`` 之外 ——
    人工最终身份反而可被机器撤回（INV-4 失效，已实证）。人工最终性必须由
    ``source='review'`` 的新决策行承载。
- **样本沉淀**（S0 §7.4）：人工确认沉淀整簇成员观测到 ``person_face_embeddings``
  （与配对工作台同一幂等语义）——这是冷启动「审核 → 样本 → 后续自动匹配」闭环
  的样本来源。
- **投影**：全部经 :class:`ProjectionReconciler`；pending 占位行按 D-3 复用。

所有读-改-写位于一个 ``BEGIN IMMEDIATE`` 事务（S1-F9）；注入的
``transaction_runner`` 缺省为 ``None``（纯 in-memory 测试路径裸跑，与既有
UoW-None 惯例一致）。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.identity_decision import (
    ConfirmReviewDecisionCommand,
)
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
    ReconcileOutcome,
)
from photo_archiver.domain.entities.cluster_assignment import (
    ACTIVE_ASSIGNMENT_STATUSES,
    ASSIGNMENT_SOURCE_REVIEW,
    MANUAL_ASSIGNMENT_SOURCES,
    ClusterPersonAssignment,
)
from photo_archiver.domain.entities.face_cluster import FaceCluster
from photo_archiver.domain.entities.recognition import RecognitionResult
from photo_archiver.domain.exceptions import (
    PhotoNotClusteredError,
    ReviewAnchorAmbiguousError,
    ValidationError,
)
from photo_archiver.domain.repositories.cluster_assignment_repository import (
    ClusterPersonAssignmentRepository,
    PersonFaceSampleRepository,
)
from photo_archiver.domain.repositories.face_cluster_repository import (
    FaceClusterRepository,
)
from photo_archiver.domain.repositories.face_observation_repository import (
    FaceObservationRepository,
)
from photo_archiver.domain.repositories.person_repository import PersonRepository
from photo_archiver.domain.repositories.recognition_repository import (
    RecognitionRepository,
)

_ONE_MICROSECOND = timedelta(microseconds=1)


@dataclass(frozen=True, slots=True)
class ReviewDecisionOutcome:
    """Result of one review identity confirmation."""

    assignment_id: UUID
    person_id: UUID
    cluster_id: UUID
    projection: RecognitionResult
    reused_suggestion: bool
    """True when an existing ``suggested`` row was confirmed in place."""
    retired_person_id: UUID | None = None
    """Set when a previous active decision (other person) was superseded."""


class IdentityDecisionService:
    """Create and reconcile human identity decisions for the review center."""

    def __init__(
        self,
        recognition_repository: RecognitionRepository,
        assignment_repository: ClusterPersonAssignmentRepository,
        cluster_repository: FaceClusterRepository,
        observation_repository: FaceObservationRepository,
        person_repository: PersonRepository,
        sample_repository: PersonFaceSampleRepository,
        reconciler: ProjectionReconciler,
        transaction_runner=None,
    ) -> None:
        self._recognition = recognition_repository
        self._assignments = assignment_repository
        self._clusters = cluster_repository
        self._observations = observation_repository
        self._persons = person_repository
        self._samples = sample_repository
        self._reconciler = reconciler
        self._runner = transaction_runner

    # ── D-2 = B：聚类前置（S1-F2） ────────────────────────────────────

    def is_photo_clustered(self, photo_id: UUID) -> bool:
        """D-2 = B：照片是否至少有一个**已入簇**的有效观测。

        必须证明 ``observation → face_cluster_members → cluster`` 链真实存在；
        仅"观测存在"或"run 存在"不算。
        """
        return self._clustered_observations(photo_id) != ()

    def _clustered_observations(self, photo_id: UUID) -> tuple:
        """该照片的已入簇有效观测（附其所属簇）。

        顺序仅用于保证候选集构造的确定性；**不参与锚点决策**——锚点只看最新代际
        的簇数量（见 :meth:`_require_anchor_cluster`）。
        """
        clustered = []
        for observation in self._observations.list_by_photo(photo_id):
            if not observation.embedding.vector:
                continue
            clusters = [
                cluster
                for cluster in self._clusters.list_clusters_of_observation(observation.id)
                if cluster.id is not None
            ]
            if clusters:
                clustered.append((observation, clusters))
        clustered.sort(key=lambda item: (item[0].face_index, str(item[0].id)))
        return tuple(clustered)

    def _require_anchor_cluster(
        self, photo_id: UUID, requested_cluster_id: UUID | None,
    ) -> FaceCluster:
        """决策锚点簇（S1-F 语义修正：废除 Top-1 det_score 隐藏规则）。

        规则（由多人照片反例驱动，见 ``ReviewAnchorAmbiguousError`` docstring）：

        1. 收集照片全部"已入簇有效观测"覆盖的簇，按代际分组；
        2. 锚定**最新代际**（重新聚类取代旧代际是既有语义，CL-13/RR 同源）；
        3. 最新代际中恰好一个簇含该照片 → 唯一锚点（单脸照片的绝大多数场景，
           无需 UI 改动）；
        4. 多个簇 → **fail-closed** 抛 :class:`ReviewAnchorAmbiguousError`，除非
           命令显式携带 ``cluster_id``（须属于该照片的已入簇集合）。

        禁止：用 det_score Top-1 猜测人脸归属——观测分高不代表它就是用户指的
        那个人（实测反例：C1→A 已确认，approve(P,B) 错把 C1→B）。
        """
        clustered = self._clustered_observations(photo_id)
        if not clustered:
            raise PhotoNotClusteredError(
                "photo has no clustered face observation; run clustering first"
            )
        candidates: dict[UUID, FaceCluster] = {}
        for _, clusters in clustered:
            for cluster in clusters:
                candidates[cluster.id] = cluster
        if requested_cluster_id is not None:
            anchor = candidates.get(requested_cluster_id)
            if anchor is None:
                raise ReviewAnchorAmbiguousError(
                    "requested cluster does not contain this photo's observations"
                )
            return anchor
        run_created_at: dict[UUID, datetime] = {}
        for candidate in candidates.values():
            if candidate.cluster_run_id in run_created_at:
                continue
            run = self._clusters.get_cluster_run(candidate.cluster_run_id)
            created = run.created_at if run is not None else None
            run_created_at[candidate.cluster_run_id] = created or datetime.min
        latest_run_id = max(
            run_created_at, key=lambda rid: (run_created_at[rid], str(rid))
        )
        latest_generation = [
            c for c in candidates.values() if c.cluster_run_id == latest_run_id
        ]
        if len(latest_generation) != 1:
            raise ReviewAnchorAmbiguousError(
                "photo spans multiple clusters in the latest clustering "
                "generation; decide per cluster in the pairing workbench or "
                "specify cluster_id"
            )
        return latest_generation[0]

    # ── 决策入口（S1-F3） ─────────────────────────────────────────────

    def confirm_from_review(
        self, command: ConfirmReviewDecisionCommand,
    ) -> ReviewDecisionOutcome:
        """Review「通过 + 指定人员」→ Assignment → Projection（单事务）。"""

        def operation(connection) -> ReviewDecisionOutcome:
            # connection 由 runner 注入；仓储经 thread-local 绑定自动加入本事务。
            return self._confirm_from_review_tx(command)

        if self._runner is not None:
            return self._runner(operation)
        return self._confirm_from_review_tx(command)

    def _confirm_from_review_tx(
        self, command: ConfirmReviewDecisionCommand,
    ) -> ReviewDecisionOutcome:
        person = self._persons.find_by_id(command.person_id)
        if person is None:
            raise ValidationError(f"person {command.person_id} does not exist")

        anchor = self._require_anchor_cluster(command.photo_id, command.cluster_id)
        assert anchor.id is not None  # entity guarantees after __post_init__
        latest = self._assignments.list_latest_decision(anchor.id)

        # 幂等（Case C）：当前身份已是该人 → 只确保投影存在，不新建决策行。
        # source 不限：confirmed 行无论 machine/manual/review 来源都表示
        # "该簇身份已经确立为该人"（现状中 confirmed 仅由人工动作产生）。
        if (
            latest is not None
            and latest.status == "confirmed"
            and latest.person_id == command.person_id
        ):
            outcome = self._reconciler.reconcile_pair(command.photo_id, command.person_id)
            projection = self._require_projection(command, outcome)
            if latest.id is None:  # pragma: no cover - entity guarantees
                raise ValidationError("assignment must carry an id")
            return ReviewDecisionOutcome(
                assignment_id=latest.id,
                person_id=command.person_id,
                cluster_id=anchor.id,
                projection=projection,
                reused_suggestion=False,
            )

        retired_person_id: UUID | None = None
        reused_suggestion = False
        created_at = _next_created_at(latest)

        if latest is not None and latest.status in ACTIVE_ASSIGNMENT_STATUSES:
            # 人工替换当前决策（suggested 或 confirmed，同人或他人）——**一律
            # 终态化旧行**。S1-F 语义修正：machine suggested 不得原地升格为
            # confirmed——source 是 immutable（update_assignment 契约），原地升格
            # 会产出 confirmed+machine source，落在 MANUAL_ASSIGNMENT_SOURCES 之外，
            # 人工最终身份反而可被机器撤回（INV-4 失效，已实证）。Review 的人工
            # 最终性必须体现在 source='review' 的新决策行上。
            # actor=human：INV-4 允许的唯一覆盖路径（review 是人工操作）。
            retired_person_id = latest.person_id
            latest.unassign()
            if self._assignments.update_assignment(latest) != 1:
                raise ValidationError(
                    f"assignment {latest.id} no longer exists (concurrent delete)"
                )
            if (
                retired_person_id is not None
                and latest.status == "unassigned"
                and latest.source in MANUAL_ASSIGNMENT_SOURCES
            ):
                self._disable_cluster_samples(retired_person_id, anchor)

        # Case A / B / C / D：一律新建 review 决策行（人工最终性 = source='review'）。
        decision = ClusterPersonAssignment(
            cluster_id=anchor.id,
            person_id=command.person_id,
            source=ASSIGNMENT_SOURCE_REVIEW,
            created_at=created_at,
        )
        decision.confirm(_sort_snapshot(anchor))
        self._assignments.add_assignments([decision])
        reused_suggestion = False

        self._deposit_samples(command.person_id, anchor)
        self._reconciler.reconcile_pair(command.photo_id, command.person_id)
        if retired_person_id is not None and retired_person_id != command.person_id:
            self._reconciler.reconcile_pair(command.photo_id, retired_person_id)

        if decision.id is None:  # pragma: no cover - entity guarantees
            raise ValidationError("assignment must carry an id")
        projection = self._require_projection(
            command,
            ReconcileOutcome("created", command.photo_id, command.person_id, decision.id, 1),
        )
        logger.info(
            "IdentityDecisionService: review confirmed photo {} -> {} via cluster {} "
            "(reused_suggestion={})",
            command.photo_id, command.person_id, anchor.id, reused_suggestion,
        )
        return ReviewDecisionOutcome(
            assignment_id=decision.id,
            person_id=command.person_id,
            cluster_id=anchor.id,
            projection=projection,
            reused_suggestion=reused_suggestion,
            retired_person_id=retired_person_id,
        )

    def _require_projection(
        self,
        command: ConfirmReviewDecisionCommand,
        outcome: ReconcileOutcome,
    ) -> RecognitionResult:
        projection = self._recognition.find_projection(command.photo_id, command.person_id)
        if projection is None:  # pragma: no cover - reconcile guarantees existence
            raise ValidationError(
                f"projection missing after reconcile ({outcome.action}) for "
                f"photo {command.photo_id} / person {command.person_id}"
            )
        return projection

    # ── 样本沉淀（S0 §7.4）与回收（E-SG-5） ──────────────────────────

    def _deposit_samples(self, person_id: UUID, cluster: FaceCluster) -> None:
        from photo_archiver.domain.entities.cluster_assignment import PersonFaceSample

        existing = {
            sample.observation_id for sample in self._samples.list_by_person(person_id)
        }
        new_samples = [
            PersonFaceSample(
                person_id=person_id,
                observation_id=observation.id,
                embedding=observation.embedding,
                quality_score=observation.quality_score,
            )
            for observation in self._cluster_member_observations(cluster)
            if observation.id not in existing
        ]
        if new_samples:
            self._samples.add_samples(new_samples)

    def _disable_cluster_samples(self, person_id: UUID, cluster: FaceCluster) -> None:
        """E-SG-5：改派/替换后停用旧人在该簇观测上的样本（历史保留 enabled=0）。"""
        self._samples.disable_samples(
            person_id,
            [observation.id for observation in self._cluster_member_observations(cluster)],
        )

    def _cluster_member_observations(self, cluster: FaceCluster):
        observations = {
            observation.id: observation
            for observation in self._observations.list_by_run(cluster.run_id)
        }
        return [
            observations[member.observation_id]
            for member in self._clusters.list_members(cluster.cluster_run_id)
            if member.cluster_id == cluster.id
            and member.observation_id in observations
            and observations[member.observation_id].embedding.vector
        ]


def _sort_snapshot(cluster: FaceCluster) -> dict:
    """确认时刻的排序快照（与配对工作台 confirm 同一形态）。"""
    return {
        "sort_key": cluster.sort_key,
        "first_captured_at": (
            cluster.first_captured_at.isoformat()
            if cluster.first_captured_at is not None else None
        ),
        "confirmed_at": datetime.now().isoformat(),
    }


def _next_created_at(previous: ClusterPersonAssignment | None) -> datetime:
    """严格晚于既有最新决策的时间戳（INV-1 排序必须全序，防同刻 UUID 平局）。"""
    now = datetime.now()
    if previous is None or previous.created_at is None:
        return now
    return max(now, previous.created_at + _ONE_MICROSECOND)