"""Pairing suggestion service — Stage E 建议生成（方案 §6 规则①②③）.

编排一次建议生成：读取指定聚类代际的簇/成员/观测嵌入 + 人员名册 +
已确认样本库 → 构建相似度 kernel（numpy 经端口注入）→ 调用领域纯函数
``suggest_pairings`` → 规则① sample_match 以 suggested 落库；规则③ 剩余位置对
经 C-2 准入判定（D2/D4/D5=A）：通过则以 auto_confirmed 整批落库（score=NULL、
不沉淀样本、不写投影），未通过则整批维持 suggested（D3=A）。幂等：已有有效指派的组跳过。
"""

from datetime import datetime
from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.pairing import StartSuggestPairingsCommand
from photo_archiver.application.ports.similarity_kernel import SimilarityKernelFactory
from photo_archiver.domain import (
    ClusterPersonAssignment,
    FaceClusterRepository,
    FaceObservationRepository,
    FaceEmbedding,
    PairingCluster,
    PairingPerson,
    PersonRepository,
    SuggestionOutcome,
    ValidationError,
    suggest_pairings,
)
from photo_archiver.domain.entities.cluster_assignment import (
    ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
    ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
    ASSIGNMENT_SOURCE_SAMPLE_MATCH,
    ASSIGNMENT_STATUS_SUGGESTED,
)
from photo_archiver.domain.services.positional_auto_confirm import (
    evaluate_positional_auto_confirm,
)
from photo_archiver.domain.entities.face_cluster import (
    CLUSTER_STATUS_IGNORED,
    CLUSTER_STATUS_UNKNOWN,
)
from photo_archiver.domain.repositories.cluster_assignment_repository import (
    ClusterPersonAssignmentRepository,
    PersonFaceSampleRepository,
)


class _ZeroLookup:
    """No-vector fallback（无成员且无样本时建议生成不会触碰相似度）。"""

    def size(self) -> int:
        return 0

    def similarity(self, left: int, right: int) -> float:  # pragma: no cover
        raise AssertionError("zero lookup has no vectors")

    def centroid_similarity(self, members, index) -> float:  # pragma: no cover
        raise AssertionError("zero lookup has no vectors")


class SuggestPairingsService:
    """Generate suggested cluster-person pairings for one cluster run."""

    def __init__(
        self,
        cluster_repository: FaceClusterRepository,
        observation_repository: FaceObservationRepository,
        person_repository: PersonRepository,
        assignment_repository: ClusterPersonAssignmentRepository,
        sample_repository: PersonFaceSampleRepository,
        similarity_factory: SimilarityKernelFactory,
        transaction_runner=None,
        photo_ignore_repository=None,
    ) -> None:
        self._cluster_repository = cluster_repository
        self._observation_repository = observation_repository
        self._person_repository = person_repository
        self._assignment_repository = assignment_repository
        self._sample_repository = sample_repository
        self._similarity_factory = similarity_factory
        # S1-F 同型：注入 run_immediate 时读集合→建议→准入→落库单事务；None 裸跑（测试）。
        self._transaction_runner = transaction_runner
        # 界面优化 §3.1：注入后，被忽略照片（本代际作用域）的全部观测不进入
        # 建议输入；None 保持历史行为（测试兼容）。
        self._ignores = photo_ignore_repository

    def execute(self, command: StartSuggestPairingsCommand) -> "SuggestPairingsSummary":
        """生成建议并按准入结果落库；返回结果摘要。

        事务：注入 transaction_runner 时，读集合→sample_match→剩余集→准入→落库
        在单个 BEGIN IMMEDIATE 事务内执行（S1-F 同型；缺省 None 裸跑，单元测试路径）。
        准入通过（C-2）时规则③位置对以 auto_confirmed 落库（D2/D4/D5=A），
        否则整批维持既有 suggested 行为（D3=A）——本服务不做部分自动确认。
        """
        if self._transaction_runner is not None:
            return self._transaction_runner(
                lambda _connection: self._execute_in_scope(command))
        return self._execute_in_scope(command)

    def _execute_in_scope(self, command: StartSuggestPairingsCommand) -> "SuggestPairingsSummary":
        cluster_run = self._cluster_repository.get_cluster_run(command.cluster_run_id)
        if cluster_run is None:
            raise ValidationError(
                f"FaceClusterRun {command.cluster_run_id} does not exist"
            )
        assert cluster_run.id is not None
        # LOGIC-04（Owner 决策）：簇级 ignored/unknown 在入口一次性排除——既不进
        # 规则① sample_match 的相似度建议输入，也不进规则③ 位置自动确认候选
        # （evaluate_positional_auto_confirm 全仓唯一调用点在本服务内，无绕过
        # 入口）。照片级忽略（§3.1 观测级排除）是独立语义，不受影响。
        clusters = [
            cluster for cluster in self._cluster_repository.list_clusters(cluster_run.id)
            if cluster.status not in (CLUSTER_STATUS_IGNORED, CLUSTER_STATUS_UNKNOWN)
        ]
        observations = {
            observation.id: observation
            for observation in self._observation_repository.list_by_run(
                cluster_run.recognition_run_id,
            )
        }
        members_by_cluster: dict[UUID, list] = {}
        for member in self._cluster_repository.list_members(cluster_run.id):
            members_by_cluster.setdefault(member.cluster_id, []).append(member)
        # §3.1：本代际被忽略照片的全部观测不参与建议生成（样本匹配向量与
        # 成员索引一并排除；簇级位置配对资格不受照片级忽略影响）。
        ignored_photo_ids = (
            set(self._ignores.list_photo_ids(cluster_run.id))
            if self._ignores is not None else set()
        )

        # 向量空间：先组成员观测嵌入（簇序×成员序），再样本嵌入。
        cluster_views: list[PairingCluster] = []
        vectors: list[FaceEmbedding] = []
        observation_ids_in_order: list[UUID] = []
        for cluster in clusters:
            if cluster.id is None:  # pragma: no cover - 实体恒生成 id
                continue
            member_indices: list[int] = []
            for member in members_by_cluster.get(cluster.id, []):
                observation = observations.get(member.observation_id)
                if observation is None or not observation.embedding.vector:
                    continue  # 防御：成员观测缺失/嵌入无效不进入建议
                if observation.photo_id in ignored_photo_ids:
                    continue  # 被忽略照片：该代际内不参与建议输入
                member_indices.append(len(vectors))
                vectors.append(observation.embedding)
                observation_ids_in_order.append(observation.id)
            cluster_views.append(PairingCluster(
                cluster_id=cluster.id,
                sort_key=cluster.sort_key,
                member_vector_indices=tuple(member_indices),
            ))

        samples = self._sample_repository.list_enabled()
        sample_owners: list[UUID | None] = []
        for sample in samples:
            sample_owners.append(sample.person_id)
            vectors.append(sample.embedding)

        person_entities = [
            person for person in self._person_repository.list_all()
            if person.id is not None
        ]
        persons = [
            PairingPerson(person_id=person.id, roster_order=person.roster_order)
            for person in person_entities if person.id is not None
        ]
        lookup = (
            self._similarity_factory.build(vectors)
            if vectors else _ZeroLookup()
        )
        rejected_pairs = frozenset(
            self._assignment_repository.list_rejected_pairs(cluster_run.id),
        )
        clusters_with_active = frozenset(
            assignment.cluster_id
            for assignment in self._assignment_repository.list_active_by_cluster_run(
                cluster_run.id,
            )
        )
        persons_confirmed = frozenset(
            self._assignment_repository.list_confirmed_person_ids(cluster_run.id),
        )
        outcomes = suggest_pairings(
            cluster_views,
            persons,
            sample_owners,
            lookup,
            rejected_pairs=rejected_pairs,
            clusters_with_active=clusters_with_active,
            persons_confirmed=persons_confirmed,
        )
        sample_matched = sum(
            1 for outcome in outcomes if outcome.source == ASSIGNMENT_SOURCE_SAMPLE_MATCH
        )

        # S4 C-3：规则① 消耗后的剩余集（D2=A）→ C-2 整批准入判定。
        sample_matched_cluster_ids = {
            outcome.cluster_id for outcome in outcomes
            if outcome.source == ASSIGNMENT_SOURCE_SAMPLE_MATCH
        }
        sample_matched_person_ids = {
            outcome.person_id for outcome in outcomes
            if outcome.source == ASSIGNMENT_SOURCE_SAMPLE_MATCH
        }
        remaining_clusters = [
            cluster for cluster in sorted(clusters, key=lambda c: c.sort_key)
            if cluster.id not in clusters_with_active
            and cluster.id not in sample_matched_cluster_ids
        ]
        remaining_persons = sorted(
            (
                person for person in person_entities
                if person.id not in persons_confirmed
                and person.id not in sample_matched_person_ids
            ),
            key=lambda p: (
                p.roster_order is None,
                p.roster_order if p.roster_order is not None else 0,
                str(p.id),
            ),
        )
        admission = evaluate_positional_auto_confirm(
            remaining_clusters, remaining_persons, rejected_pairs)

        if admission.admitted:
            # 整批位置自动确认：严格位置对 (E_c[i], E_p[i]) → auto_confirmed
            # （score 恒 NULL、不沉淀样本、不写投影——BD-4/BD-5/D1=A）。
            auto_rows = []
            for cluster, person in zip(remaining_clusters, remaining_persons):
                assert cluster.id is not None and person.id is not None  # 实体 __post_init__ 保证
                row = ClusterPersonAssignment(
                    cluster_id=cluster.id,
                    person_id=person.id,
                    source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
                )
                row.auto_confirm({
                    "sort_key": cluster.sort_key,
                    "first_captured_at": (
                        cluster.first_captured_at.isoformat()
                        if cluster.first_captured_at is not None else None
                    ),
                    "auto_confirmed_at": datetime.now().isoformat(),
                })
                auto_rows.append(row)
            suggested_rows = [
                ClusterPersonAssignment(
                    cluster_id=outcome.cluster_id,
                    person_id=outcome.person_id,
                    status=ASSIGNMENT_STATUS_SUGGESTED,
                    source=ASSIGNMENT_SOURCE_SAMPLE_MATCH,
                    score=outcome.score,
                )
                for outcome in outcomes
                if outcome.source == ASSIGNMENT_SOURCE_SAMPLE_MATCH
            ]
            self._assignment_repository.add_assignments(suggested_rows + auto_rows)
            auto_confirmed = len(auto_rows)
            ordered = 0
            blocked_reason = None
        else:
            # 准入未通过（D3=A）：整批维持既有 suggested 行为，零自动确认。
            self._persist(
                cluster_run.id, cluster_run.recognition_run_id, outcomes)
            auto_confirmed = 0
            ordered = sum(
                1 for outcome in outcomes
                if outcome.source == ASSIGNMENT_SOURCE_ORDERED_SUGGESTION
            )
            blocked_reason = admission.reason

        summary = SuggestPairingsSummary(
            cluster_run_id=cluster_run.id,
            suggestions=sample_matched + ordered,
            sample_matched=sample_matched,
            ordered=ordered,
            unmatched_clusters=len(clusters) - len(outcomes),
            persons_without_cluster=max(0, len(persons) - len(outcomes)),
            auto_confirmed=auto_confirmed,
            auto_confirm_blocked_reason=blocked_reason,
        )
        logger.info(
            "SuggestPairingsService: run {} -> {} suggested, {} auto-confirmed "
            "(sample_match={}, ordered={}, blocked={})",
            cluster_run.id, sample_matched + ordered, auto_confirmed,
            sample_matched, ordered, blocked_reason,
        )
        return summary

    def _persist(self, cluster_run_id: UUID, recognition_run_id: UUID,
                 outcomes: tuple[SuggestionOutcome, ...]) -> None:
        """Persist suggestions as suggested decision rows."""
        self._assignment_repository.add_assignments([
            ClusterPersonAssignment(
                cluster_id=outcome.cluster_id,
                person_id=outcome.person_id,
                status=ASSIGNMENT_STATUS_SUGGESTED,
                source=(
                    ASSIGNMENT_SOURCE_SAMPLE_MATCH
                    if outcome.source == "sample_match"
                    else ASSIGNMENT_SOURCE_ORDERED_SUGGESTION
                ),
                score=outcome.score,
            )
            for outcome in outcomes
        ])


class SuggestPairingsSummary:
    """Outcome summary of one suggestion generation."""

    def __init__(self, cluster_run_id: UUID, suggestions: int, sample_matched: int,
                 ordered: int, unmatched_clusters: int, persons_without_cluster: int,
                 auto_confirmed: int = 0,
                 auto_confirm_blocked_reason: str | None = None) -> None:
        self.cluster_run_id = cluster_run_id
        self.suggestions = suggestions
        self.sample_matched = sample_matched
        self.ordered = ordered
        self.unmatched_clusters = unmatched_clusters
        self.persons_without_cluster = persons_without_cluster
        self.auto_confirmed = auto_confirmed
        self.auto_confirm_blocked_reason = auto_confirm_blocked_reason
