"""S4 C-2 — 位置自动确认批次准入纯函数单元测试（BD-2；D2/D4/D5=A）.

覆盖：准入成功、数量不一致、空集合、时间缺失（首/中/末）、严格位置对
被拒（首/中/末/多对/非严格对不阻断）、纯函数性质（确定性、输入不可变、
原因优先级）与输入顺序语义。全部使用独立构造的最小领域实体，不接入
生产服务或数据库。
"""

import copy
from datetime import datetime
from uuid import UUID, uuid4

from photo_archiver.domain.entities.face_cluster import FaceCluster
from photo_archiver.domain.entities.person import Person
from photo_archiver.domain.services.positional_auto_confirm import (
    ADMISSION_REASON_COUNT_MISMATCH,
    ADMISSION_REASON_EMPTY_INPUT,
    ADMISSION_REASON_MISSING_CAPTURE_TIME,
    ADMISSION_REASON_REJECTED_POSITIONAL_PAIR,
    evaluate_positional_auto_confirm,
)

_BASE = datetime(2026, 1, 1, 8, 0, 0)


def _cluster(*, captured: datetime | None = _BASE, sort_key: str = "k") -> FaceCluster:
    return FaceCluster(
        cluster_run_id=uuid4(),
        run_id=uuid4(),
        ordinal=0,
        member_count=1,
        sort_key=sort_key,
        first_captured_at=captured,
    )


def _clusters(count: int, *, missing_index: int | None = None) -> list[FaceCluster]:
    return [
        _cluster(captured=None if i == missing_index else _BASE, sort_key=f"k{i}")
        for i in range(count)
    ]


def _persons(count: int) -> list[Person]:
    return [Person(name=f"人员 {i}") for i in range(count)]


def _pair_ids(clusters, persons, index: int) -> tuple[UUID, UUID]:
    return (clusters[index].id, persons[index].id)


# ── C1 准入成功 ─────────────────────────────────────────────────────────────


def test_admitted_returns_true_without_reason_when_all_conditions_hold():
    clusters, persons = _clusters(3), _persons(3)
    result = evaluate_positional_auto_confirm(clusters, persons)

    assert result.admitted is True
    assert result.reason is None
    assert (result.cluster_count, result.person_count) == (3, 3)
    assert result.missing_time_index is None
    assert result.rejected_positional_index is None
    assert result.rejected_positional_pair is None


def test_single_pair_batch_is_admitted():
    result = evaluate_positional_auto_confirm(_clusters(1), _persons(1))
    assert result.admitted is True and result.reason is None


def test_strict_positional_semantics_ignores_non_positional_rejections():
    """拒绝对 (E_c[1],E_p[0]) 与 (E_c[2],E_p[1]) 均非严格位置对——不得阻断。

    同时证明配对按**输入下标**（E_c[i],E_p[i]）进行：若实现做了重排或
    交叉匹配，这两条拒绝对就会被命中。
    """
    clusters, persons = _clusters(3), _persons(3)
    rejected = frozenset({
        (clusters[1].id, persons[0].id),
        (clusters[2].id, persons[1].id),
    })
    result = evaluate_positional_auto_confirm(clusters, persons, rejected)

    assert result.admitted is True
    assert result.reason is None
    assert result.rejected_positional_pair is None


def test_strict_pairing_uses_input_order_not_sort_key():
    """输入顺序得到原样尊重：即使 sort_key 顺序与列表顺序不同，
    严格位置对仍按传入下标判定（第一个输入簇被拒 → 整批阻断）。"""
    clusters = [
        _cluster(sort_key="z"),
        _cluster(sort_key="a"),
        _cluster(sort_key="m"),
    ]
    persons = _persons(3)
    rejected = frozenset({_pair_ids(clusters, persons, 0)})

    result = evaluate_positional_auto_confirm(clusters, persons, rejected)

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_REJECTED_POSITIONAL_PAIR
    assert result.rejected_positional_pair == _pair_ids(clusters, persons, 0)


# ── C2 数量不一致 ───────────────────────────────────────────────────────────


def test_clusters_more_than_persons_blocks_with_count_mismatch():
    result = evaluate_positional_auto_confirm(_clusters(3), _persons(2))

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_COUNT_MISMATCH
    assert (result.cluster_count, result.person_count) == (3, 2)


def test_persons_more_than_clusters_blocks_with_count_mismatch():
    result = evaluate_positional_auto_confirm(_clusters(2), _persons(3))

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_COUNT_MISMATCH
    assert (result.cluster_count, result.person_count) == (2, 3)


def test_empty_clusters_with_nonempty_persons_blocks_with_count_mismatch():
    """数量不等优先于 EMPTY_INPUT（优先级 1），不得静默通过。"""
    result = evaluate_positional_auto_confirm(_clusters(0), _persons(2))

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_COUNT_MISMATCH
    assert (result.cluster_count, result.person_count) == (0, 2)


def test_nonempty_clusters_with_empty_persons_blocks_with_count_mismatch():
    result = evaluate_positional_auto_confirm(_clusters(2), _persons(0))

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_COUNT_MISMATCH
    assert (result.cluster_count, result.person_count) == (2, 0)


# ── C3 空集合 ───────────────────────────────────────────────────────────────


def test_both_empty_blocks_with_empty_input_despite_equal_counts():
    result = evaluate_positional_auto_confirm(_clusters(0), _persons(0))

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_EMPTY_INPUT
    assert (result.cluster_count, result.person_count) == (0, 0)


# ── C4 时间缺失（首/中/末，均整批阻断）─────────────────────────────────────


def test_missing_time_on_first_cluster_blocks_whole_batch():
    result = evaluate_positional_auto_confirm(
        _clusters(3, missing_index=0), _persons(3))

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_MISSING_CAPTURE_TIME
    assert result.missing_time_index == 0


def test_missing_time_on_middle_cluster_blocks_whole_batch():
    result = evaluate_positional_auto_confirm(
        _clusters(3, missing_index=1), _persons(3))

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_MISSING_CAPTURE_TIME
    assert result.missing_time_index == 1


def test_missing_time_on_last_cluster_blocks_whole_batch():
    result = evaluate_positional_auto_confirm(
        _clusters(3, missing_index=2), _persons(3))

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_MISSING_CAPTURE_TIME
    assert result.missing_time_index == 2


# ── C5 拒绝的严格位置对 ─────────────────────────────────────────────────────


def test_rejected_first_positional_pair_blocks_whole_batch():
    clusters, persons = _clusters(3), _persons(3)
    result = evaluate_positional_auto_confirm(
        clusters, persons, frozenset({_pair_ids(clusters, persons, 0)}))

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_REJECTED_POSITIONAL_PAIR
    assert result.rejected_positional_index == 0
    assert result.rejected_positional_pair == _pair_ids(clusters, persons, 0)


def test_rejected_middle_positional_pair_blocks_whole_batch():
    clusters, persons = _clusters(3), _persons(3)
    result = evaluate_positional_auto_confirm(
        clusters, persons, frozenset({_pair_ids(clusters, persons, 1)}))

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_REJECTED_POSITIONAL_PAIR
    assert result.rejected_positional_index == 1
    assert result.rejected_positional_pair == _pair_ids(clusters, persons, 1)


def test_rejected_last_positional_pair_blocks_whole_batch():
    clusters, persons = _clusters(3), _persons(3)
    result = evaluate_positional_auto_confirm(
        clusters, persons, frozenset({_pair_ids(clusters, persons, 2)}))

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_REJECTED_POSITIONAL_PAIR
    assert result.rejected_positional_index == 2
    assert result.rejected_positional_pair == _pair_ids(clusters, persons, 2)


def test_multiple_rejected_positional_pairs_report_lowest_index_deterministically():
    clusters, persons = _clusters(3), _persons(3)
    rejected = frozenset({
        _pair_ids(clusters, persons, 2),
        _pair_ids(clusters, persons, 0),
    })
    result = evaluate_positional_auto_confirm(clusters, persons, rejected)

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_REJECTED_POSITIONAL_PAIR
    assert result.rejected_positional_index == 0
    assert result.rejected_positional_pair == _pair_ids(clusters, persons, 0)


def test_non_positional_rejections_never_block_positional_pairing():
    """交叉拒绝对（c0↔p1、c1↔p0）存在但严格位置对全部未被拒 → 不阻断，
    也不得通过跳过或顺延去规避。"""
    clusters, persons = _clusters(2), _persons(2)
    swapped = frozenset({
        (clusters[0].id, persons[1].id),
        (clusters[1].id, persons[0].id),
    })
    positional = frozenset({
        _pair_ids(clusters, persons, 0),
        _pair_ids(clusters, persons, 1),
    })
    assert swapped.isdisjoint(positional)

    result = evaluate_positional_auto_confirm(clusters, persons, swapped)

    assert result.admitted is True
    assert result.reason is None


# ── C6 纯函数性质与确定性 ───────────────────────────────────────────────────


def test_same_input_always_returns_identical_result():
    clusters, persons = _clusters(3), _persons(3)
    rejected = frozenset({_pair_ids(clusters, persons, 1)})

    first = evaluate_positional_auto_confirm(clusters, persons, rejected)
    second = evaluate_positional_auto_confirm(clusters, persons, rejected)

    assert first == second
    assert hash(first) == hash(second)


def test_inputs_are_not_mutated_by_evaluation():
    """缺失时间分支：调用后输入整体（全字段）保持不变。"""
    clusters, persons = _clusters(3, missing_index=1), _persons(3)
    rejected = frozenset({_pair_ids(clusters, persons, 0)})
    clusters_snapshot = copy.deepcopy(clusters)
    persons_snapshot = copy.deepcopy(persons)

    evaluate_positional_auto_confirm(clusters, persons, rejected)

    assert clusters == clusters_snapshot
    assert persons == persons_snapshot


def test_rejected_branch_does_not_mutate_inputs():
    """拒绝位置对分支：调用后输入整体（全字段）保持不变（F-C2-1 强化）。"""
    clusters, persons = _clusters(3), _persons(3)
    rejected = frozenset({_pair_ids(clusters, persons, 1)})
    clusters_snapshot = copy.deepcopy(clusters)
    persons_snapshot = copy.deepcopy(persons)

    evaluate_positional_auto_confirm(clusters, persons, rejected)

    assert clusters == clusters_snapshot
    assert persons == persons_snapshot


def test_count_mismatch_has_highest_priority_over_other_blockers():
    """数量不一致 + 时间缺失 + 严格位置对被拒同时成立 → COUNT_MISMATCH。"""
    clusters, persons = _clusters(3, missing_index=1), _persons(2)
    rejected = frozenset({_pair_ids(clusters, persons, 0)})

    result = evaluate_positional_auto_confirm(clusters, persons, rejected)

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_COUNT_MISMATCH


def test_missing_time_has_priority_over_rejected_positional_pair():
    clusters, persons = _clusters(3, missing_index=1), _persons(3)
    rejected = frozenset({_pair_ids(clusters, persons, 1)})

    result = evaluate_positional_auto_confirm(clusters, persons, rejected)

    assert result.admitted is False
    assert result.reason == ADMISSION_REASON_MISSING_CAPTURE_TIME
    assert result.rejected_positional_pair is None
