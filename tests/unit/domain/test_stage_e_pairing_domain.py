"""Stage E domain tests — assignment state machine + pairing suggestion rules."""

import math
from uuid import uuid4

import pytest

from photo_archiver.domain import (
    ClusterPersonAssignment,
    FaceEmbedding,
    PairingCluster,
    PairingPerson,
    ValidationError,
    suggest_pairings,
)


class _ExactLookup:
    """Pure-python cosine lookup over an explicit vector list（量化 6 位）。"""

    def __init__(self, vectors):
        self._vectors = vectors

    def size(self):
        return len(self._vectors)

    def similarity(self, left, right):
        dot = sum(a * b for a, b in zip(self._vectors[left], self._vectors[right]))
        norm_l = math.sqrt(sum(a * a for a in self._vectors[left]))
        norm_r = math.sqrt(sum(a * a for a in self._vectors[right]))
        if norm_l == 0.0 or norm_r == 0.0:
            return 0.0
        return round(dot / (norm_l * norm_r), 6)

    def centroid_similarity(self, members, index):  # pragma: no cover - 建议不使用
        raise AssertionError("pairing suggestions never call centroid_similarity")


# ── 状态机 ──────────────────────────────────────────────────────────────────


def test_suggested_confirms_with_snapshot_and_timestamp():
    assignment = ClusterPersonAssignment(cluster_id=uuid4(), person_id=uuid4())
    assignment.confirm({"sort_key": "k"})

    assert assignment.status == "confirmed"
    assert assignment.confirmed_at is not None
    assert assignment.sort_snapshot["sort_key"] == "k"


def test_suggested_rejects_and_unassigns():
    assignment = ClusterPersonAssignment(cluster_id=uuid4(), person_id=uuid4())
    assignment.reject()
    assert assignment.status == "rejected"
    assignment.unassign()
    assert assignment.status == "unassigned"


def test_confirmed_cannot_reconfirm_or_reject():
    assignment = ClusterPersonAssignment(cluster_id=uuid4(), person_id=uuid4())
    assignment.confirm()
    with pytest.raises(ValidationError):
        assignment.confirm()
    with pytest.raises(ValidationError):
        assignment.reject()


def test_rejected_can_only_be_unassigned():
    assignment = ClusterPersonAssignment(cluster_id=uuid4(), person_id=uuid4())
    assignment.reject()
    with pytest.raises(ValidationError):
        assignment.confirm()
    assignment.unassign()
    with pytest.raises(ValidationError):
        assignment.confirm()  # unassigned 行不再迁移（新建议 = 新行）


def test_unassigned_row_requires_no_person_and_is_frozen():
    assignment = ClusterPersonAssignment(
        cluster_id=uuid4(), person_id=None, status="unassigned",
    )
    with pytest.raises(ValidationError):
        assignment.confirm()
    with pytest.raises(ValidationError):
        ClusterPersonAssignment(
            cluster_id=uuid4(), person_id=None, status="suggested",
        )


def test_score_must_be_cosine_domain():
    with pytest.raises(ValidationError):
        ClusterPersonAssignment(cluster_id=uuid4(), person_id=uuid4(), score=1.5)


# ── 建议生成（方案 §6 规则①②③） ────────────────────────────────────────────


def _unit(angle: float):
    radians = math.radians(angle)
    return (math.cos(radians), math.sin(radians))


def _scenario(vectors, clusters, persons, samples, **kwargs):
    lookup = _ExactLookup(vectors)
    return suggest_pairings(clusters, persons, samples, lookup, **kwargs)


def _unit_vector(cosine_to_x_axis: float):
    """Unit 2-D vector whose cosine with the x-axis equals the argument.

    D-2 boundary tests need exact, reproducible similarity values instead of
    angle-derived cosines (which only approximate the threshold).
    """
    return (cosine_to_x_axis, math.sqrt(1.0 - cosine_to_x_axis ** 2))


def test_sample_match_generates_suggested_with_score():
    """规则①：已确认样本高置信（≥0.40）→ sample_match 建议。"""
    cluster_id, person_id = uuid4(), uuid4()
    vectors = [_unit(0.0), _unit(5.0), _unit(3.0)]
    # 成员向量 idx0/idx1（簇），样本向量 idx2 属 person。
    outcomes = _scenario(
        vectors,
        [PairingCluster(cluster_id, "k|a|000000", (0, 1))],
        [PairingPerson(person_id, 1)],
        [person_id],
        sample_match_threshold=0.40,
    )

    assert len(outcomes) == 1
    assert outcomes[0].cluster_id == cluster_id
    assert outcomes[0].person_id == person_id
    assert outcomes[0].source == "sample_match"
    # 最大余弦 = max(cos(0°-3°), cos(5°-3°)) = cos2°。
    assert outcomes[0].score == pytest.approx(math.cos(math.radians(2.0)), abs=1e-5)


# ── D-2：样本匹配阈值边界统一为 score >= 0.40 ────────────────────────────────


def test_score_exactly_at_threshold_matches():
    """D-2：score **恰等于**阈值 0.40 时命中（``>=`` 而非 ``>``）。"""
    cluster_id, person_id = uuid4(), uuid4()
    # 成员向量在 x 轴，样本向量与之夹角使余弦精确为 0.40。
    vectors = [(1.0, 0.0), _unit_vector(0.40)]
    outcomes = _scenario(
        vectors,
        [PairingCluster(cluster_id, "k|a|000000", (0,))],
        [PairingPerson(person_id, 1)],
        [person_id],
        sample_match_threshold=0.40,
    )
    assert len(outcomes) == 1
    assert outcomes[0].source == "sample_match"
    assert outcomes[0].score == pytest.approx(0.40, abs=1e-6)


def test_score_just_below_threshold_does_not_match():
    """D-2：score 略低于阈值（0.39）不触发 sample_match。"""
    cluster_id, person_id = uuid4(), uuid4()
    vectors = [(1.0, 0.0), _unit_vector(0.39)]
    outcomes = _scenario(
        vectors,
        [PairingCluster(cluster_id, "k|a|000000", (0,))],
        [PairingPerson(person_id, 1)],
        [person_id],
        sample_match_threshold=0.40,
    )
    assert all(o.source != "sample_match" for o in outcomes)


def test_score_just_above_threshold_matches():
    """D-2：score 略高于阈值（0.41）命中。"""
    cluster_id, person_id = uuid4(), uuid4()
    vectors = [(1.0, 0.0), _unit_vector(0.41)]
    outcomes = _scenario(
        vectors,
        [PairingCluster(cluster_id, "k|a|000000", (0,))],
        [PairingPerson(person_id, 1)],
        [person_id],
        sample_match_threshold=0.40,
    )
    assert len(outcomes) == 1
    assert outcomes[0].source == "sample_match"
    assert outcomes[0].score == pytest.approx(0.41, abs=1e-6)


def test_below_sample_threshold_falls_back_to_ordered():
    """样本相似度 < 0.40 → 不触发 sample_match，走规则③顺序配对。"""
    cluster_id, person_id = uuid4(), uuid4()
    vectors = [_unit(0.0), _unit(70.0)]  # cos70≈0.342 < 0.40
    outcomes = _scenario(
        vectors,
        [PairingCluster(cluster_id, "k|a|000000", (0,))],
        [PairingPerson(person_id, 1)],
        [person_id],
        sample_match_threshold=0.40,
    )

    assert len(outcomes) == 1
    assert outcomes[0].source == "ordered_suggestion"
    assert outcomes[0].score is None


def test_rejected_pair_is_excluded_from_both_passes():
    """规则②：被拒绝的 (组, 人) 对在样本匹配与顺序配对中都被跳过。"""
    cluster_id, person_id, other_id = uuid4(), uuid4(), uuid4()
    # 成员 idx0=0°；样本 person idx1=3°（高相似但被拒绝）；other idx2=70°
    # （<0.40 → 不触发 sample_match，落到规则③顺序配对）。
    vectors = [_unit(0.0), _unit(3.0), _unit(70.0)]
    outcomes = _scenario(
        vectors,
        [PairingCluster(cluster_id, "k|a|000000", (0,))],
        [PairingPerson(person_id, 1), PairingPerson(other_id, 2)],
        [person_id, other_id],
        rejected_pairs=frozenset({(cluster_id, person_id)}),
    )

    assert len(outcomes) == 1
    assert outcomes[0].person_id == other_id
    assert outcomes[0].source == "ordered_suggestion"


def test_ordered_pairing_is_one_to_one_by_sort_key_and_roster_order():
    """规则③：组按 sort_key、人按 roster_order，一对一 min(组数, 人数)。"""
    c1, c2, c3 = uuid4(), uuid4(), uuid4()
    p1, p2 = uuid4(), uuid4()
    vectors = [_unit(0.0)] * 3
    outcomes = _scenario(
        vectors,
        [
            PairingCluster(c3, "k|c|000000", (2,)),   # sort_key 最大
            PairingCluster(c1, "k|a|000000", (0,)),   # sort_key 最小
            PairingCluster(c2, "k|b|000000", (1,)),
        ],
        [
            PairingPerson(p2, 2),                     # roster_order 大
            PairingPerson(p1, 1),                     # roster_order 小
        ],
        [],
    )

    by_cluster = {o.cluster_id: o for o in outcomes}
    assert set(by_cluster) == {c1, c2}  # 组 3 > 人数 2 → 未获建议
    assert by_cluster[c1].person_id == p1  # 首组 × roster 首位
    assert by_cluster[c2].person_id == p2
    assert all(o.source == "ordered_suggestion" for o in outcomes)


def test_confirmed_persons_and_active_clusters_are_skipped():
    """已有确认的人员、已有有效指派的组不重复进入建议。"""
    c1, c2 = uuid4(), uuid4()
    p1, p2 = uuid4(), uuid4()
    vectors = [_unit(0.0), _unit(0.0)]
    outcomes = _scenario(
        vectors,
        [PairingCluster(c1, "k|a|000000", (0,)), PairingCluster(c2, "k|b|000000", (1,))],
        [PairingPerson(p1, 1), PairingPerson(p2, 2)],
        [],
        clusters_with_active=frozenset({c1}),
        persons_confirmed=frozenset({p1}),
    )

    assert [(o.cluster_id, o.person_id) for o in outcomes] == [(c2, p2)]


def test_no_persons_yields_no_suggestions():
    cluster_id = uuid4()
    outcomes = _scenario(
        [_unit(0.0)],
        [PairingCluster(cluster_id, "k|a|000000", (0,))],
        [],
        [],
    )
    assert outcomes == ()


def test_lookup_size_mismatch_rejected():
    with pytest.raises(ValueError, match="size"):
        suggest_pairings(
            [PairingCluster(uuid4(), "k", (0,))],
            [PairingPerson(uuid4(), 1)],
            [],
            _ExactLookup([_unit(0.0), _unit(1.0)]),
        )


def test_face_embedding_sample_entity_rejects_bad_quality():
    from photo_archiver.domain import PersonFaceSample

    sample = PersonFaceSample(
        person_id=uuid4(), observation_id=uuid4(),
        embedding=FaceEmbedding((1.0, 0.0)),
    )
    assert sample.enabled is True
    with pytest.raises(ValidationError):
        PersonFaceSample(
            person_id=uuid4(), observation_id=uuid4(),
            embedding=FaceEmbedding((1.0, 0.0)), quality_score=1.5,
        )
