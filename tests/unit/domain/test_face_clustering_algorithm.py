"""Pure two-phase clustering algorithm tests — Stage D owner 裁决的精确行为.

用 2D 单位向量 + 纯 python 相似度 kernel（真实簇心余弦语义）手造角度，
使阈值边界可精确控制：cos(角差)。覆盖任务书要求的全部算法边界。
"""

import math
from uuid import uuid4

import pytest

from photo_archiver.domain import (
    ClusteringCancelled,
    ClusteringItem,
    cluster_items,
)


def _unit_vector(angle_degrees: float) -> tuple[float, float]:
    radians = math.radians(angle_degrees)
    return (math.cos(radians), math.sin(radians))


class _ExactLookup:
    """Pure-python SimilarityLookup：真实簇心余弦 + 6 位量化（对齐生产 kernel）."""

    def __init__(self, vectors: list[tuple[float, ...]]) -> None:
        self._vectors = vectors

    def size(self) -> int:
        return len(self._vectors)

    @staticmethod
    def _cosine(left, right) -> float:
        dot = sum(a * b for a, b in zip(left, right))
        norm_left = math.sqrt(sum(a * a for a in left))
        norm_right = math.sqrt(sum(a * a for a in right))
        if norm_left == 0.0 or norm_right == 0.0:
            return 0.0
        return round(dot / (norm_left * norm_right), 6)

    def similarity(self, left: int, right: int) -> float:
        return self._cosine(self._vectors[left], self._vectors[right])

    def centroid_similarity(self, members, index: int) -> float:
        centroid = [
            sum(vector[axis] for vector in (self._vectors[i] for i in members))
            / len(members)
            for axis in range(len(self._vectors[0]))
        ]
        return self._cosine(centroid, self._vectors[index])


def _items(count: int, quality: float | None = 1.0) -> list[ClusteringItem]:
    return [ClusteringItem(observation_id=uuid4(), quality_score=quality) for _ in range(count)]


def _lookup_vectors(*angles: float) -> _ExactLookup:
    return _ExactLookup([_unit_vector(angle) for angle in angles])


def _cluster_of(assignments, item_index: int) -> int:
    for ordinal, assignment in enumerate(assignments):
        if item_index in assignment.members:
            return ordinal
    raise AssertionError(f"item {item_index} not assigned")


def test_single_observation_forms_singleton_cluster() -> None:
    items = _items(1)
    assignments = cluster_items(items, _ExactLookup([_unit_vector(0.0)]))

    assert len(assignments) == 1
    assert assignments[0].members == (0,)
    assert assignments[0].confidences == (1.0,)  # seed 自证


def test_similar_faces_cluster_and_dissimilar_separate() -> None:
    items = _items(3)
    # 0° 与 10° 同人（cos10≈0.985），80° 另一人。
    assignments = cluster_items(items, _lookup_vectors(0.0, 10.0, 80.0))

    assert len(assignments) == 2
    assert _cluster_of(assignments, 0) == _cluster_of(assignments, 1)
    assert _cluster_of(assignments, 2) != _cluster_of(assignments, 0)


def test_candidate_threshold_boundary_inclusive() -> None:
    """cos(60°)=0.5 恰在 cluster_sim_threshold 上 → 入簇（≥ 语义）。"""
    items = _items(2)
    assignments = cluster_items(items, _lookup_vectors(0.0, 60.0))

    assert len(assignments) == 1
    assert assignments[0].members == (0, 1)


def test_below_candidate_threshold_can_still_merge_via_consistency() -> None:
    """两段式语义：阶段① 未入候选（cos60.1≈0.498 < 0.5）的项，阶段② 仍按
    一致性阈值 0.4 合并（0.498 ≥ 0.4）——候选门不是最终归属边界。"""
    items = _items(2)
    assignments = cluster_items(items, _lookup_vectors(0.0, 60.1))

    assert len(assignments) == 1
    assert assignments[0].members == (0, 1)


def test_candidate_gate_separates_when_consistency_also_fails() -> None:
    """阶段① 候选门生效：75° 对簇心(10°) cos65≈0.423 < 0.5 未入候选，
    且跨簇两两最小 cos75≈0.259 < 0.4 → 保持分离。"""
    items = _items(3)
    assignments = cluster_items(items, _lookup_vectors(0.0, 20.0, 75.0))

    assert len(assignments) == 2
    assert _cluster_of(assignments, 0) == _cluster_of(assignments, 1)
    assert _cluster_of(assignments, 2) != _cluster_of(assignments, 0)


def test_chain_counterexample_never_merges() -> None:
    """方案 §D-5 反例：A~B~C 相似但 A~C 不达一致性阈值 → 不并。

    0°/40°/85°：A~B=cos40≈0.766 ≥ 0.5 同候选；C 对簇心 cos65≈0.42 < 0.5
    另立候选；跨簇两两最小 = min(cos85, cos45) = cos85≈0.087 < 0.4 → 不并。
    """
    items = _items(3)
    assignments = cluster_items(items, _lookup_vectors(0.0, 40.0, 85.0))

    assert len(assignments) == 2
    assert _cluster_of(assignments, 0) == _cluster_of(assignments, 1)
    assert _cluster_of(assignments, 2) != _cluster_of(assignments, 0)


def test_complete_linkage_merges_when_consistency_holds() -> None:
    """组内两两最小相似度 ≥ 0.4 的候选簇并为一簇。

    0°/25°/45°：0°→{A}；25° cos25≈0.906 ≥ 0.5 → {A,B}；45° 对簇心(12.5°)
    cos32.5≈0.843 ≥ 0.5 → 同候选，两两最小 cos45≈0.707 ≥ 0.4。
    """
    items = _items(3)
    assignments = cluster_items(items, _lookup_vectors(0.0, 25.0, 45.0))

    assert len(assignments) == 1
    assert assignments[0].members == (0, 1, 2)


def test_multiple_clusters_partition_independently() -> None:
    items = _items(4)
    # 两对同人：0°/10° 与 90°/100°，互不相似。
    assignments = cluster_items(items, _lookup_vectors(0.0, 10.0, 90.0, 100.0))

    assert len(assignments) == 2
    assert _cluster_of(assignments, 0) == _cluster_of(assignments, 1)
    assert _cluster_of(assignments, 2) == _cluster_of(assignments, 3)
    assert _cluster_of(assignments, 0) != _cluster_of(assignments, 2)


def test_low_quality_member_does_not_drive_merge() -> None:
    """owner 裁决：低质量成员不参与合并证据（涉低质量的对不作证据）。

    A=0°(q=1)、B=63°(q=1)、C=-20°(q=0.1)，low_quality_threshold=0.5：
    阶段① B 对 A cos63≈0.454<0.5 → 独立候选；C 对 A cos20≈0.94 ≥ 0.5
    → 并入 A 候选。阶段② 高质量证据 (A,B)=0.454 ≥ 0.4 → 合并；
    涉低质量的对 (C,B)=cos83≈0.122 不作证据。
    阈值禁用（0.0）时同输入的最小值被 (C,B) 拖到 0.122 → 不并。
    """
    items = [
        ClusteringItem(observation_id=uuid4(), quality_score=quality)
        for quality in (1.0, 1.0, 0.1)
    ]
    lookup = _lookup_vectors(0.0, 63.0, -20.0)

    merged = cluster_items(items, lookup, low_quality_threshold=0.5)
    assert len(merged) == 1  # 低质量成员的劣质相似度不阻塞高质量证据合并
    assert merged[0].members == (0, 1, 2)

    blocked = cluster_items(items, lookup, low_quality_threshold=0.0)
    assert len(blocked) == 2  # 禁用阈值：低质量对的 0.122 拖垮最小值 → 不并


def test_zero_vector_similarity_is_zero_and_stays_singleton() -> None:
    lookup = _ExactLookup([(0.0, 0.0), _unit_vector(0.0)])
    assignments = cluster_items(_items(2), lookup)

    assert len(assignments) == 2


def test_determinism_same_input_same_output() -> None:
    lookup = _lookup_vectors(0.0, 40.0, 85.0, 10.0, 95.0)
    items = _items(5)

    first = cluster_items(items, lookup)
    second = cluster_items(items, lookup)

    assert first == second


def test_absorbed_members_carry_merge_evidence_confidence() -> None:
    """并入簇的成员以跨簇两两最小相似度作为归属证据。

    收紧候选门到 0.9：0°→{A}；20° cos20≈0.94≥0.9 → {A,B}；55° 对簇心(10°)
    cos45≈0.707<0.9 → {C}。阶段② 跨簇最小 = min(cos55, cos35) = cos55
    ≥ 0.4 → 合并；被并入的 C 以 cos55 作为归属证据。
    """
    items = _items(3)
    assignments = cluster_items(
        items, _lookup_vectors(0.0, 20.0, 55.0), cluster_sim_threshold=0.9,
    )

    assert len(assignments) == 1
    index_of_third = assignments[0].members.index(2)
    assert assignments[0].confidences[index_of_third] == pytest.approx(
        math.cos(math.radians(55)), abs=1e-5,
    )
    assert assignments[0].confidences[assignments[0].members.index(0)] == 1.0


def test_cancel_hook_raises_clustering_cancelled() -> None:
    with pytest.raises(ClusteringCancelled):
        cluster_items(_items(2), _lookup_vectors(0.0, 10.0), should_cancel=lambda: True)


def test_empty_input_yields_no_clusters() -> None:
    assert cluster_items((), _ExactLookup([])) == ()


def test_lookup_size_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="size"):
        cluster_items(_items(2), _ExactLookup([_unit_vector(0.0)]))


# ── P1 边界（Stage D 核心验收裁决：合并门为包含语义 ≥） ────────────────────


def _two_item_lookup(second_x: float) -> _ExactLookup:
    """cos(两向量) 精确等于 second_x（v2 = (x, √(1-x²))，单位化）。"""
    return _ExactLookup([(1.0, 0.0), (second_x, math.sqrt(1.0 - second_x ** 2))])


def test_merge_boundary_exactly_at_threshold_merges() -> None:
    """跨簇两两最小相似度恰好 = 0.4 → 合并（规格包含语义，P1 修复回归）。"""
    items = _items(2)
    assignments = cluster_items(
        items, _two_item_lookup(0.4), consistency_threshold=0.4,
    )

    assert len(assignments) == 1
    assert assignments[0].members == (0, 1)


def test_merge_boundary_below_stricter_threshold_stays_separate() -> None:
    """同一对（恰 0.4）在 consistency_threshold=0.5 下 → 不合并。"""
    items = _items(2)
    assignments = cluster_items(
        items, _two_item_lookup(0.4), consistency_threshold=0.5,
    )

    assert len(assignments) == 2


def test_merge_boundary_just_above_threshold_merges() -> None:
    """0.400001 > 0.4 → 合并（与恰等值用例共同钉死包含边界）。"""
    items = _items(2)
    assignments = cluster_items(
        items, _two_item_lookup(0.400001), consistency_threshold=0.4,
    )

    assert len(assignments) == 1


# ── P2-a：tail-move 分支与多轮合并的常驻确定性回归（只断言最终划分） ────────


def _members_of(assignments) -> list[frozenset[int]]:
    return [frozenset(assignment.members) for assignment in assignments]


def test_multi_round_merge_with_tail_move_final_partition() -> None:
    """四单例两轮合并，首轮即触发 tail-move（right != last）并跨轮复用重键值。

    角度 0°/124°/62°/186°：阶段① 全部单例（两两最大 cos62≈0.469<0.5）；
    阶段② 首轮合并 (0,2)（right=2 != last=3 → tail-move），第二轮使用
    重键后的 (1,2)=0.469 合并 (1,3)。最终划分 {{0,2},{1,3}}。
    """
    items = _items(4)
    assignments = cluster_items(items, _lookup_vectors(0.0, 124.0, 62.0, 186.0))

    assert sorted(_members_of(assignments)) == [frozenset({0, 2}), frozenset({1, 3})]
    by_item = {
        index: assignment for assignment in assignments for index in assignment.members
    }
    expected = round(math.cos(math.radians(62.0)), 6)
    for absorbed in (2, 3):
        index = by_item[absorbed].members.index(absorbed)
        assert by_item[absorbed].confidences[index] == expected  # 并簇证据 = 跨簇最小
    for seed in (0, 1):
        index = by_item[seed].members.index(seed)
        assert by_item[seed].confidences[index] == 1.0


def test_five_point_ring_multi_round_merge_uses_rekeyed_cross_values() -> None:
    """五单例两轮合并（首轮 tail-move，次轮使用重键后的跨簇值）。

    角度 0°/62°/124°/186°/248°：两两最大 cos62≈0.469 全部 < 0.5 → 五单例。
    阶段② 首轮合并 (0,1)（right=1 != last=4 → tail-move，{4} 重键到
    idx1，其跨簇值 (3,4)=0.469 重键为 (1,3)）；次轮 (1,3) 正是重键产生
    的证据对 → 合并 {3,4}。{2} 因 (2,4)=-0.559 的完全链接约束保持单例
    （环不链式化）。最终 {{0,1},{3,4},{2}}。
    """
    items = _items(5)
    assignments = cluster_items(
        items, _lookup_vectors(0.0, 62.0, 124.0, 186.0, 248.0),
    )

    assert sorted(_members_of(assignments)) == [
        frozenset({0, 1}), frozenset({3, 4}), frozenset({2}),
    ]
    by_item = {
        index: assignment for assignment in assignments for index in assignment.members
    }
    expected = round(math.cos(math.radians(62.0)), 6)
    assert by_item[1].confidences[by_item[1].members.index(1)] == expected
    assert by_item[3].confidences[by_item[3].members.index(3)] == expected
    for seed in (0, 4, 2):
        assert by_item[seed].confidences[by_item[seed].members.index(seed)] == 1.0


# ── P2-b：同一 Observation 在同一 ClusterRun 内唯一归属（算法级对抗性） ──────


def test_every_item_assigned_exactly_once_across_clusters() -> None:
    """对抗性断言：全部输入项恰被归属一次——不重复、不遗漏。

    用五点环（多轮合并、tail-move）+ 相似对混合数据，逐簇校验成员索引
    全局唯一且并集 == 全部输入索引。
    """
    items = _items(9)
    angles = (0.0, 62.0, 124.0, 186.0, 248.0, 5.0, 57.0, 119.0, 181.0)
    assignments = cluster_items(items, _lookup_vectors(*angles))

    seen: list[int] = []
    for assignment in assignments:
        seen.extend(assignment.members)
        assert len(assignment.members) == len(set(assignment.members))
    assert len(seen) == len(set(seen)), "同一输入项被归属到多个 Cluster"
    assert sorted(seen) == list(range(len(items))), "存在未被归属的输入项"
