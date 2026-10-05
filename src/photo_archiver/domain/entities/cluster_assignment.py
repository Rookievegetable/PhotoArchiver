"""Cluster person assignment + person face sample entities（阶段 E）.

owner 批准方案 §3.2/§6 与执行计划 §E-1 的身份指派层数据地基：

- ``ClusterPersonAssignment``：Cluster → Person 的一次身份决策行。同一
  cluster 的决策历史以多行表达，**当前有效行 = status ∈ {suggested,
  confirmed}**（服务层保证至多一行有效）。状态机：
  suggested → confirmed（人工确认）/ rejected（人工拒绝）/ unassigned
  （解除）；confirmed → unassigned（改派/解除）；rejected → unassigned
  （撤销拒绝）。**没有自动确认**——sample_match 命中也只是 suggested
  （方案 §6："建议状态均为 suggested，不改变正式归属"）。
- ``source`` 区分决策来源：ordered_suggestion（§6 规则③顺序配对）/
  sample_match（§6 规则①已确认样本高置信匹配）/ manual（人工改派、
  新增指派——人工明确选择即 confirmed，区别于系统建议的待确认）。
- ``sort_snapshot`` 在确认时保存当时的组排序快照（§5.3：以后补入更早
  照片不回写已确认映射）。
- ``PersonFaceSample``：确认映射时沉淀的人员多样本（D4：后续 1:N 匹配
  = 多样本最大余弦）；UNIQUE(person_id, observation_id) 由仓储强制。
"""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.value_objects import FaceEmbedding

ASSIGNMENT_STATUS_SUGGESTED = "suggested"
ASSIGNMENT_STATUS_CONFIRMED = "confirmed"
ASSIGNMENT_STATUS_REJECTED = "rejected"
ASSIGNMENT_STATUS_UNASSIGNED = "unassigned"

ASSIGNMENT_STATUSES = frozenset(
    {
        ASSIGNMENT_STATUS_SUGGESTED,
        ASSIGNMENT_STATUS_CONFIRMED,
        ASSIGNMENT_STATUS_REJECTED,
        ASSIGNMENT_STATUS_UNASSIGNED,
    }
)
# 当前有效行（一个 cluster 至多一行）。
ACTIVE_ASSIGNMENT_STATUSES = frozenset(
    {ASSIGNMENT_STATUS_SUGGESTED, ASSIGNMENT_STATUS_CONFIRMED}
)
# **归档投影支撑**状态（S1）。刻意窄于 ACTIVE_ASSIGNMENT_STATUSES：
#
# ``suggested`` 表示机器归类建议仍在等待人工核实。基线 CORE-05 / BA-01
# 「配对确认 = 归档门槛」要求机器建议**不得**产生可归档投影——否则一条未被人看
# 过的建议就能把照片送进归档链（这正是 K-3 / D-1 要消除的风险）。
#
# 两个集合的用途不可混用：
# - ACTIVE_ASSIGNMENT_STATUSES → 「这个簇当前是否有人」（INV-1 判定 + 改派替换目标）
# - PROJECTION_SUPPORT_STATUSES → 「这个簇的身份是否已确定到可以归档」
#
# S4 引入 ``auto_confirmed``（自动确认）时在此加入，不改动上者的语义。
PROJECTION_SUPPORT_STATUSES = frozenset({ASSIGNMENT_STATUS_CONFIRMED})

ASSIGNMENT_SOURCE_ORDERED_SUGGESTION = "ordered_suggestion"
ASSIGNMENT_SOURCE_MANUAL = "manual"
ASSIGNMENT_SOURCE_SAMPLE_MATCH = "sample_match"
ASSIGNMENT_SOURCE_REVIEW = "review"
ASSIGNMENT_SOURCES = frozenset(
    {
        ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
        ASSIGNMENT_SOURCE_MANUAL,
        ASSIGNMENT_SOURCE_SAMPLE_MATCH,
        ASSIGNMENT_SOURCE_REVIEW,
    }
)

# **人工来源**的决策（S0 INV-4 / P0-5）。machine 侧 mutation（自动撤回、自动重跑
# 覆盖）遇到这些来源必须拒绝——人工再修改不受限。S1-F：Review 的身份确认是人工
# 决策（source="review"），与人工指派同等最终。
MANUAL_ASSIGNMENT_SOURCES = frozenset(
    {ASSIGNMENT_SOURCE_MANUAL, ASSIGNMENT_SOURCE_REVIEW}
)

# ── actor 词表（S0 INV-4 的显式化） ────────────────────────────────────────────
#
# actor 标注"谁在改这条决策"。它**不是**数据字段（不落库、不进 assignment 行），
# 而是 mutation 入口的必填契约：守卫据此判断能否触碰人工最终决策。
#
# 为何需要具名的 MACHINE_ACTOR 而非"任何非 human 字符串"：
# * 无 MACHINE_ACTOR 时，S4 的机器调用方可能随手写一个字符串、甚至**忘记传
#   actor** 而落到签名默认值 —— 默认值是 human，于是机器静默获得人工权限
#   （fail-open）。具名常量让机器入口的写法可被code review 一眼识别。
# * 未知 actor 一律按机器处理（保守默认 fail-closed），见
#   :func:`photo_archiver.application.services.pairing_workbench_service.
#   _assert_mutable_by_machine`。
HUMAN_ACTOR = "human"
MACHINE_ACTOR = "machine"

_ALLOWED_ASSIGNMENT_TRANSITIONS = {
    ASSIGNMENT_STATUS_SUGGESTED: frozenset(
        {
            ASSIGNMENT_STATUS_CONFIRMED,
            ASSIGNMENT_STATUS_REJECTED,
            ASSIGNMENT_STATUS_UNASSIGNED,
        }
    ),
    ASSIGNMENT_STATUS_CONFIRMED: frozenset({ASSIGNMENT_STATUS_UNASSIGNED}),
    ASSIGNMENT_STATUS_REJECTED: frozenset({ASSIGNMENT_STATUS_UNASSIGNED}),
    ASSIGNMENT_STATUS_UNASSIGNED: frozenset(),
}


@dataclass(slots=True)  # NOT frozen: confirm/reject/unassign 迁移状态
class ClusterPersonAssignment:
    """One traceable Cluster → Person identity decision."""

    cluster_id: UUID
    person_id: UUID | None = None
    status: str = ASSIGNMENT_STATUS_SUGGESTED
    source: str = ASSIGNMENT_SOURCE_ORDERED_SUGGESTION
    score: float | None = None
    id: UUID | None = None
    created_at: datetime | None = None
    confirmed_at: datetime | None = None
    sort_snapshot: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate vocabulary and the status/person consistency invariant."""
        if self.id is None:
            self.id = uuid4()
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.status not in ASSIGNMENT_STATUSES:
            raise ValidationError(f"Unknown ClusterPersonAssignment status: {self.status}")
        if self.source not in ASSIGNMENT_SOURCES:
            raise ValidationError(f"Unknown ClusterPersonAssignment source: {self.source}")
        if self.status != ASSIGNMENT_STATUS_UNASSIGNED and self.person_id is None:
            raise ValidationError(
                f"{self.status} assignment requires a person_id",
            )
        if self.score is not None and not -1.0 <= self.score <= 1.0:
            raise ValidationError("ClusterPersonAssignment score must be in [-1.0, 1.0]")
        object.__setattr__(
            self, "sort_snapshot", MappingProxyType(deepcopy(dict(self.sort_snapshot))),
        )

    def confirm(self, sort_snapshot: dict[str, Any] | None = None) -> None:
        """人工确认：suggested → confirmed，保存排序快照与确认时间。"""
        self._transition_to(ASSIGNMENT_STATUS_CONFIRMED)
        if sort_snapshot is not None:
            object.__setattr__(
                self, "sort_snapshot", MappingProxyType(deepcopy(dict(sort_snapshot))),
            )
        self.confirmed_at = datetime.now()

    def reject(self) -> None:
        """人工拒绝该候选人员。"""
        self._transition_to(ASSIGNMENT_STATUS_REJECTED)

    def unassign(self) -> None:
        """解除映射/改派前的失效/撤销拒绝——历史行保留。"""
        self._transition_to(ASSIGNMENT_STATUS_UNASSIGNED)

    def _transition_to(self, target: str) -> None:
        """Enforce the state machine（无终态回退、无重复确认）。"""
        if target not in _ALLOWED_ASSIGNMENT_TRANSITIONS.get(self.status, frozenset()):
            raise ValidationError(
                f"ClusterPersonAssignment cannot transition from {self.status} to {target}"
            )
        self.status = target


@dataclass(frozen=True, slots=True)
class PersonFaceSample:
    """One confirmed member observation sunk into a person's sample library."""

    person_id: UUID
    observation_id: UUID
    embedding: FaceEmbedding
    quality_score: float | None = None
    enabled: bool = True
    id: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate quality bounds and initialize the creation timestamp."""
        if self.quality_score is not None and not 0.0 <= self.quality_score <= 1.0:
            raise ValidationError("PersonFaceSample quality_score must be in [0.0, 1.0]")
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
