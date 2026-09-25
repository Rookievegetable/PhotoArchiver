"""Pairing suggestion service — Stage E 建议生成（方案 §6 规则①②③）.

编排一次建议生成：读取指定聚类代际的簇/成员/观测嵌入 + 人员名册 +
已确认样本库 → 构建相似度 kernel（numpy 经端口注入）→ 调用领域纯函数
``suggest_pairings`` → 以 suggested 状态落库决策行。**绝不自动确认**
（方案 §6：建议不改变正式归属）。幂等：已有有效指派的组跳过。
"""

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
    ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
    ASSIGNMENT_SOURCE_SAMPLE_MATCH,
    ASSIGNMENT_STATUS_SUGGESTED,
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
    ) -> None:
        self._cluster_repository = cluster_repository
        self._observation_repository = observation_repository
        self._person_repository = person_repository
        self._assignment_repository = assignment_repository
        self._sample_repository = sample_repository
        self._similarity_factory = similarity_factory

    def execute(self, command: StartSuggestPairingsCommand) -> "SuggestPairingsSummary":
        """Generate and persist suggestions; returns the outcome summary."""
        cluster_run = self._cluster_repository.get_cluster_run(command.cluster_run_id)
        if cluster_run is None:
            raise ValidationError(
                f"FaceClusterRun {command.cluster_run_id} does not exist"
            )
        assert cluster_run.id is not None
        clusters = self._cluster_repository.list_clusters(cluster_run.id)
        observations = {
            observation.id: observation
            for observation in self._observation_repository.list_by_run(
                cluster_run.recognition_run_id,
            )
        }
        members_by_cluster: dict[UUID, list] = {}
        for member in self._cluster_repository.list_members(cluster_run.id):
            members_by_cluster.setdefault(member.cluster_id, []).append(member)

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

        persons = [
            PairingPerson(person_id=person.id, roster_order=person.roster_order)
            for person in self._person_repository.list_all()
            if person.id is not None
        ]
        lookup = (
            self._similarity_factory.build(vectors)
            if vectors else _ZeroLookup()
        )
        outcomes = suggest_pairings(
            cluster_views,
            persons,
            sample_owners,
            lookup,
            rejected_pairs=frozenset(
                self._assignment_repository.list_rejected_pairs(cluster_run.id),
            ),
            clusters_with_active=frozenset(
                assignment.cluster_id
                for assignment in self._assignment_repository.list_active_by_cluster_run(
                    cluster_run.id,
                )
            ),
            persons_confirmed=frozenset(
                self._assignment_repository.list_confirmed_person_ids(cluster_run.id),
            ),
        )
        self._persist(cluster_run.id, cluster_run.recognition_run_id, outcomes)
        sample_matched = sum(
            1 for outcome in outcomes if outcome.source == ASSIGNMENT_SOURCE_SAMPLE_MATCH
        )
        ordered = sum(
            1 for outcome in outcomes if outcome.source == ASSIGNMENT_SOURCE_ORDERED_SUGGESTION
        )
        summary = SuggestPairingsSummary(
            cluster_run_id=cluster_run.id,
            suggestions=len(outcomes),
            sample_matched=sample_matched,
            ordered=ordered,
            unmatched_clusters=len(clusters) - len(outcomes),
            persons_without_cluster=max(0, len(persons) - len(outcomes)),
        )
        logger.info(
            "SuggestPairingsService: run {} -> {} suggestion(s) "
            "(sample_match={}, ordered={})",
            cluster_run.id, len(outcomes), sample_matched, ordered,
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
                 ordered: int, unmatched_clusters: int, persons_without_cluster: int) -> None:
        self.cluster_run_id = cluster_run_id
        self.suggestions = suggestions
        self.sample_matched = sample_matched
        self.ordered = ordered
        self.unmatched_clusters = unmatched_clusters
        self.persons_without_cluster = persons_without_cluster
