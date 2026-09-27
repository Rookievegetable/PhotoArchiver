"""Pure pairing-suggestion generation — Stage E 建议规则（owner 批准方案 §6）.

规则全文（方案 §6 建议生成顺序，逐条落点）：

1. **已确认样本高置信匹配优先**：对每个尚无有效指派的组，用该组成员
   观测嵌入 vs 已确认人员样本（启用态）的最大余弦（D4：多样本取最大）
   匹配；``>= sample_match_threshold``（0.40，F 校准；**恰等于阈值即命中**，
   Stage 4 D-2 裁决）→ source=``sample_match`` 的 suggested 建议。
   被该组拒绝过的人员不参与。
2. **排除已明确拒绝的映射**：全程跳过 rejected (cluster, person) 对。
3. **剩余按排序位置一对一**：剩余组（sort_key 升序）× 剩余人员
   （roster_order 升序，排除已被①消耗/已在别处确认的人员）取
   min(组数, 人数) 一对一生成 source=``ordered_suggestion``（score=NULL）；
   同一对 (组, 人) 被拒绝则顺延下一位人员。
4. **建议状态均为 suggested**——本函数从不产生 confirmed。

组数 < 人数 → 仅前 min 个组获建议（其余人员"尚无照片组"）；组数 > 人数
→ 仅可配数量的建议（剩余组"未知/待处理"）；无名单 → 无建议（允许先
聚类）。纯函数、零 I/O，相似度经 ``SimilarityLookup`` 端口注入。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from photo_archiver.domain.services.face_clustering import SimilarityLookup

SAMPLE_MATCH_THRESHOLD_DEFAULT = 0.40

_NO_EVIDENCE = float("-inf")


@dataclass(frozen=True, slots=True)
class PairingCluster:
    """One cluster entering suggestion: sort key + member vector indices."""

    cluster_id: UUID
    sort_key: str
    member_vector_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PairingPerson:
    """One roster person entering suggestion with their roster order."""

    person_id: UUID
    roster_order: int | None


@dataclass(frozen=True, slots=True)
class SuggestionOutcome:
    """One generated suggestion (always status=suggested at persistence)."""

    cluster_id: UUID
    person_id: UUID
    source: str
    score: float | None


def suggest_pairings(
    clusters: Sequence[PairingCluster],
    persons: Sequence[PairingPerson],
    sample_person_ids: Sequence[UUID | None],
    similarity: SimilarityLookup,
    *,
    rejected_pairs: frozenset[tuple[UUID, UUID]] = frozenset(),
    clusters_with_active: frozenset[UUID] = frozenset(),
    persons_confirmed: frozenset[UUID] = frozenset(),
    sample_match_threshold: float = SAMPLE_MATCH_THRESHOLD_DEFAULT,
) -> tuple[SuggestionOutcome, ...]:
    """Generate suggestions per plan §6; empty inputs yield no suggestions."""
    member_count = sum(len(cluster.member_vector_indices) for cluster in clusters)
    if similarity.size() != member_count + len(sample_person_ids):
        raise ValueError("similarity lookup size must cover member + sample vectors")

    available = [
        person for person in persons
        if person.person_id not in persons_confirmed
    ]
    # roster_order 升序；无顺序人员排有顺序人员之后（PersonRepository 同约定），
    # 仍无顺序的按 person_id 兜底全序。
    available.sort(key=lambda person: (
        person.roster_order is None,
        person.roster_order if person.roster_order is not None else 0,
        str(person.person_id),
    ))
    ordered_clusters = sorted(clusters, key=lambda cluster: cluster.sort_key)

    outcomes: list[SuggestionOutcome] = []
    consumed_persons: set[UUID] = set()

    # ① sample match（优先）。D-2（Stage 4 裁决）：命中边界统一为
    # score >= sample_match_threshold——恰等于阈值（0.40）**命中**。
    # 阈值与"当前最优"分离，避免用 best_score 兼任阈值时把 > 与 >= 混淆。
    sample_offset = member_count
    for cluster in ordered_clusters:
        if cluster.cluster_id in clusters_with_active:
            continue
        best_person: UUID | None = None
        best_score: float | None = None
        for sample_index_offset, owner in enumerate(sample_person_ids):
            if owner is None or owner in consumed_persons:
                continue
            if (cluster.cluster_id, owner) in rejected_pairs:
                continue
            score = _max_member_sample_similarity(
                cluster.member_vector_indices, sample_offset + sample_index_offset, similarity,
            )
            if score is None or score < sample_match_threshold:
                continue
            if best_score is None or score > best_score:
                best_person, best_score = owner, score
        if best_person is not None:
            outcomes.append(SuggestionOutcome(
                cluster_id=cluster.cluster_id,
                person_id=best_person,
                source="sample_match",
                score=best_score,
            ))
            consumed_persons.add(best_person)

    # ③ ordered one-to-one（剩余组 × 剩余人员）。
    matched_clusters = {outcome.cluster_id for outcome in outcomes}
    person_queue = [
        person for person in available if person.person_id not in consumed_persons
    ]
    for cluster in ordered_clusters:
        if not person_queue:
            break
        if cluster.cluster_id in clusters_with_active or cluster.cluster_id in matched_clusters:
            continue
        person_index = next(
            (i for i, person in enumerate(person_queue)
             if (cluster.cluster_id, person.person_id) not in rejected_pairs),
            None,
        )
        if person_index is None:
            continue
        person = person_queue.pop(person_index)
        outcomes.append(SuggestionOutcome(
            cluster_id=cluster.cluster_id,
            person_id=person.person_id,
            source="ordered_suggestion",
            score=None,
        ))
    return tuple(outcomes)


def _max_member_sample_similarity(
    member_indices: Sequence[int], sample_index: int, similarity: SimilarityLookup,
) -> float | None:
    """D4：多样本 × 多成员取最大余弦；无成员对返回 None。"""
    if not member_indices:
        return None
    return max(similarity.similarity(member, sample_index) for member in member_indices)
