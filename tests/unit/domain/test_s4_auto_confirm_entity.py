"""S4 冷启动位置自动确认 — 领域实体契约测试（C-1B / C-1C.A/B）.

owner 裁决（2026-10-10，D1-D6）钉定：

- 新状态 ``auto_confirmed`` 与新来源 ``ordered_auto_confirm`` 的词表归属；
- score=NULL 守卫（BD-4：位置配对没有相似度证据，不得伪造）；
- ``auto_confirmed ∈ ACTIVE`` 但 ``∉ PROJECTION_SUPPORT``（D1=A：不驱动归档）；
- **人工终审必须新建 manual/review 决策行**——自动来源行禁止原地升格
  confirmed（构造、反序列化、状态转移、通用确认入口四条路径全部关闭）；
- 现有状态机语义与机器/人工来源词表不因新状态放宽。
"""

from uuid import uuid4

import pytest

from photo_archiver.domain import ClusterPersonAssignment, ValidationError
from photo_archiver.domain.entities.cluster_assignment import (
    ACTIVE_ASSIGNMENT_STATUSES,
    ASSIGNMENT_SOURCES,
    ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
    ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
    ASSIGNMENT_STATUSES,
    ASSIGNMENT_STATUS_AUTO_CONFIRMED,
    ASSIGNMENT_STATUS_CONFIRMED,
    HUMAN_ACTOR,
    MACHINE_ACTOR,
    MANUAL_ASSIGNMENT_SOURCES,
    PROJECTION_SUPPORT_STATUSES,
)

_SNAPSHOT = {
    "sort_key": "2026-01-01T00:00:00|E:/photos/a.jpg|000003",
    "first_captured_at": "2026-01-01T00:00:00",
    "auto_confirmed_at": "2026-10-10T12:00:00",
}


def _auto_suggested() -> ClusterPersonAssignment:
    """一条合法的 ordered_auto_confirm 来源 suggested 行（auto_confirm 前置态）。"""
    return ClusterPersonAssignment(
        cluster_id=uuid4(),
        person_id=uuid4(),
        source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
    )


def _auto_confirmed() -> ClusterPersonAssignment:
    """一条合法的 auto_confirmed 行（模拟仓储反序列化/服务构造产物）。"""
    assignment = _auto_suggested()
    assignment.auto_confirm(dict(_SNAPSHOT))
    return assignment


# ── 词表（C-1C.A.1） ────────────────────────────────────────────────────────


def test_new_status_and_source_are_in_vocabularies():
    assert ASSIGNMENT_STATUS_AUTO_CONFIRMED in ASSIGNMENT_STATUSES
    assert ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM in ASSIGNMENT_SOURCES
    # D6=A：auto_confirmed 是"簇当前有人"的有效态，参与 INV-1 判定与改派替换。
    assert ASSIGNMENT_STATUS_AUTO_CONFIRMED in ACTIVE_ASSIGNMENT_STATUSES


def test_auto_confirmed_is_not_projection_support():
    # D1=A：机器自动确认不进入归档投影支撑集；confirmed 仍是唯一支撑态。
    assert ASSIGNMENT_STATUS_AUTO_CONFIRMED not in PROJECTION_SUPPORT_STATUSES
    assert ASSIGNMENT_STATUS_CONFIRMED in PROJECTION_SUPPORT_STATUSES


def test_machine_source_vocabulary_not_loosened():
    # ordered_auto_confirm 是机器来源——不进 MANUAL_ASSIGNMENT_SOURCES；
    # 人工来源词表保持 {manual, review}（E-02 资格门语义的前提）。
    assert ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM not in MANUAL_ASSIGNMENT_SOURCES
    assert MANUAL_ASSIGNMENT_SOURCES == frozenset({"manual", "review"})
    assert HUMAN_ACTOR == "human" and MACHINE_ACTOR == "machine"


# ── 合法构造与 auto_confirm 入口（C-1C.A.2/3） ──────────────────────────────


def test_auto_confirm_transitions_with_required_snapshot():
    assignment = _auto_suggested()
    assignment.auto_confirm(dict(_SNAPSHOT))

    assert assignment.status == "auto_confirmed"
    assert dict(assignment.sort_snapshot) == _SNAPSHOT
    # confirmed_at 语义 = "人工最终确认时刻"——自动确认行不携带。
    assert assignment.confirmed_at is None


def test_auto_confirm_snapshot_is_required():
    assignment = _auto_suggested()
    with pytest.raises(TypeError):
        assignment.auto_confirm()  # type: ignore[call-arg]


def test_direct_construction_of_auto_confirmed_row_is_legal():
    # 仓储反序列化按构造函数重建行——合法组合必须可直接构造。
    assignment = ClusterPersonAssignment(
        cluster_id=uuid4(),
        person_id=uuid4(),
        status="auto_confirmed",
        source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
        sort_snapshot=dict(_SNAPSHOT),
    )
    assert assignment.status == "auto_confirmed"
    assert assignment.score is None


# ── score=NULL 守卫（C-1C.A.4，BD-4） ───────────────────────────────────────


def test_auto_confirm_refuses_similarity_score():
    assignment = _auto_suggested()
    assignment.score = 0.42  # 模拟服务层把样本匹配分误带到位置配对行
    with pytest.raises(ValidationError):
        assignment.auto_confirm(dict(_SNAPSHOT))


def test_auto_source_row_with_score_is_rejected_at_construction():
    with pytest.raises(ValidationError):
        ClusterPersonAssignment(
            cluster_id=uuid4(),
            person_id=uuid4(),
            source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
            score=0.42,
        )


# ── 组合守卫（C-1C.A.5） ────────────────────────────────────────────────────


def test_auto_confirmed_requires_auto_source():
    with pytest.raises(ValidationError):
        ClusterPersonAssignment(
            cluster_id=uuid4(),
            person_id=uuid4(),
            status="auto_confirmed",
        )  # 默认 source=ordered_suggestion


def test_auto_source_cannot_be_confirmed_at_construction():
    with pytest.raises(ValidationError):
        ClusterPersonAssignment(
            cluster_id=uuid4(),
            person_id=uuid4(),
            status="confirmed",
            source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
        )


def test_auto_confirm_refuses_foreign_sources():
    # source 在构造时确定；auto_confirm 只服务 ordered_auto_confirm——
    # 防止把样本匹配/人工来源行误升格为自动确认。
    for source in ("ordered_suggestion", "sample_match", "manual", "review"):
        assignment = ClusterPersonAssignment(
            cluster_id=uuid4(), person_id=uuid4(), source=source,
        )
        with pytest.raises(ValidationError):
            assignment.auto_confirm(dict(_SNAPSHOT))


def test_generic_confirm_transitions_suggested_to_confirmed():
    # 最小行为钉定：通用 confirm() 将 suggested 迁移至 confirmed（目标态为
    # 字面常量）。auto_confirmed 的产生仅经专用 auto_confirm() 入口——该结构
    # 性事实由本文件的转换/守卫测试与 auto_confirm 用例分别钉定。
    assignment = ClusterPersonAssignment(cluster_id=uuid4(), person_id=uuid4())
    assignment.confirm()
    assert assignment.status == "confirmed"


# ── 人工终审契约（C-1C.B） ──────────────────────────────────────────────────


def test_in_place_upgrade_of_auto_confirmed_row_is_blocked():
    assignment = _auto_confirmed()
    with pytest.raises(ValidationError):
        assignment.confirm()  # 状态机：auto_confirmed → confirmed 不存在


def test_in_place_upgrade_of_transient_auto_suggested_row_is_blocked():
    # 瞬态（未落库的 suggested + ordered_auto_confirm）也必须关死：
    # suggested → confirmed 是既有合法转移，但自动来源行不得借此升格。
    assignment = _auto_suggested()
    with pytest.raises(ValidationError):
        assignment.confirm()


def test_auto_source_rows_keep_reject_and_unassign_paths():
    # D6=A：人工可拒绝/解除（终态化本行，历史保留）。
    rejected = _auto_confirmed()
    rejected.reject()
    assert rejected.status == "rejected"
    rejected.unassign()
    assert rejected.status == "unassigned"

    released = _auto_confirmed()
    released.unassign()
    assert released.status == "unassigned"


def test_human_final_confirmation_is_a_distinct_decision_event():
    """自动决策行与人工终审行是两条可区分的决策事件（C-1 契约 §5）。"""
    auto_row = _auto_confirmed()
    # 人工终审模式（与 S1-F review / 工作台 assign 同一事件模式）：终态化旧行
    # → 新建人工来源行 → confirm。
    auto_row.unassign()
    human_row = ClusterPersonAssignment(
        cluster_id=auto_row.cluster_id,
        person_id=auto_row.person_id,
        source="manual",
        created_at=auto_row.created_at,
    )
    human_row.confirm({"sort_key": "k", "confirmed_at": "later"})

    assert auto_row.id != human_row.id
    assert (auto_row.source, auto_row.status) == ("ordered_auto_confirm", "unassigned")
    assert (human_row.source, human_row.status) == ("manual", "confirmed")
    assert human_row.confirmed_at is not None


# ── 既有状态机回归（C-1C.A.7） ──────────────────────────────────────────────


def test_existing_transitions_unchanged():
    confirmed = ClusterPersonAssignment(cluster_id=uuid4(), person_id=uuid4())
    confirmed.confirm()
    with pytest.raises(ValidationError):
        confirmed.reject()
    confirmed.unassign()
    with pytest.raises(ValidationError):
        confirmed.confirm()  # unassigned 终态

    rejected = ClusterPersonAssignment(cluster_id=uuid4(), person_id=uuid4())
    rejected.reject()
    rejected.unassign()
    assert rejected.status == "unassigned"

    # ordered_suggestion 的 suggested 行仍可原地 confirm（既有工作台语义不动）。
    suggested = ClusterPersonAssignment(
        cluster_id=uuid4(), person_id=uuid4(),
        source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
    )
    suggested.confirm({"sort_key": "k"})
    assert suggested.status == "confirmed"
    assert suggested.source == ASSIGNMENT_SOURCE_ORDERED_SUGGESTION
