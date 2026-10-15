"""Cluster person assignment + person face sample entities（阶段 E）.

owner 批准方案 §3.2/§6 与执行计划 §E-1 的身份指派层数据地基：

- ``ClusterPersonAssignment``：Cluster → Person 的一次身份决策行。同一
  cluster 的决策历史以多行表达，**当前有效行 = status ∈ {suggested,
  confirmed, auto_confirmed}**（服务层保证至多一行有效）。状态机：
  suggested → confirmed（人工确认）/ rejected（人工拒绝）/ unassigned
  （解除）/ auto_confirmed（S4 冷启动位置规则自动确认）；confirmed →
  unassigned（改派/解除）；rejected → unassigned（撤销拒绝）；
  auto_confirmed → rejected / unassigned（人工拒绝/解除/改派前置，D6=A）。
  sample_match 命中仍然只是 suggested（方案 §6："建议状态均为 suggested，
  不改变正式归属"）。
- ``source`` 区分决策来源：ordered_suggestion（§6 规则③顺序配对）/
  sample_match（§6 规则①已确认样本高置信匹配）/ manual（人工改派、
  新增指派——人工明确选择即 confirmed，区别于系统建议的待确认）/
  review（S1-F 审核中心人工身份确认）/ ordered_auto_confirm（S4 冷启动
  位置自动确认，机器来源，score 恒 NULL）。**人工终审必须新建 manual/review
  决策行**：source 不可变，auto_confirmed 行不得原地升格为 confirmed
  （S1-F 实证过的 INV-4 失效模式，禁止复现）；自动决策行保留为可追溯历史。
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
ASSIGNMENT_STATUS_AUTO_CONFIRMED = "auto_confirmed"

ASSIGNMENT_STATUSES = frozenset(
    {
        ASSIGNMENT_STATUS_SUGGESTED,
        ASSIGNMENT_STATUS_CONFIRMED,
        ASSIGNMENT_STATUS_REJECTED,
        ASSIGNMENT_STATUS_UNASSIGNED,
        ASSIGNMENT_STATUS_AUTO_CONFIRMED,
    }
)
# 当前有效行（一个 cluster 至多一行）。S4：auto_confirmed 是机器产生的当前
# 身份——簇"有人"，等待人工终审（新决策行）或人工拒绝/解除（终态化本行）。
ACTIVE_ASSIGNMENT_STATUSES = frozenset(
    {
        ASSIGNMENT_STATUS_SUGGESTED,
        ASSIGNMENT_STATUS_CONFIRMED,
        ASSIGNMENT_STATUS_AUTO_CONFIRMED,
    }
)
# **归档投影支撑**状态（S1）。刻意窄于 ACTIVE_ASSIGNMENT_STATUSES：
#
# ``suggested`` / ``auto_confirmed`` 都是机器产生的决策：前者等待人工核实，
# 后者是 S4 冷启动位置规则的自动确认（owner 裁决 D1=A，2026-10-10）。基线
# CORE-05 / BA-01「配对确认 = 归档门槛」要求机器决策**不得**产生可归档投影
# ——否则一条未被人看过的机器结论就能把照片送进归档链（K-3 / D-1 要消除的
# 风险）。``auto_confirmed`` 因此**不加入**本集合：位置自动确认只表达指派层
# 的当前身份，归档可见性仍必须由人工终审产生的新决策行（source=manual/review,
# status=confirmed）承载。
#
# 两个集合的用途不可混用：
# - ACTIVE_ASSIGNMENT_STATUSES → 「这个簇当前是否有人」（INV-1 判定 + 改派替换目标）
# - PROJECTION_SUPPORT_STATUSES → 「这个簇的身份是否已确定到可以归档」
PROJECTION_SUPPORT_STATUSES = frozenset({ASSIGNMENT_STATUS_CONFIRMED})

ASSIGNMENT_SOURCE_ORDERED_SUGGESTION = "ordered_suggestion"
ASSIGNMENT_SOURCE_MANUAL = "manual"
ASSIGNMENT_SOURCE_SAMPLE_MATCH = "sample_match"
ASSIGNMENT_SOURCE_REVIEW = "review"
ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM = "ordered_auto_confirm"
ASSIGNMENT_SOURCES = frozenset(
    {
        ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
        ASSIGNMENT_SOURCE_MANUAL,
        ASSIGNMENT_SOURCE_SAMPLE_MATCH,
        ASSIGNMENT_SOURCE_REVIEW,
        ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
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
            ASSIGNMENT_STATUS_AUTO_CONFIRMED,
        }
    ),
    ASSIGNMENT_STATUS_CONFIRMED: frozenset({ASSIGNMENT_STATUS_UNASSIGNED}),
    ASSIGNMENT_STATUS_REJECTED: frozenset({ASSIGNMENT_STATUS_UNASSIGNED}),
    ASSIGNMENT_STATUS_UNASSIGNED: frozenset(),
    # S4 冷启动位置自动确认（owner D6=A，2026-10-10）：人工可拒绝/解除（终态化
    # 本行，机器侧由服务层 actor 守卫拦截——C-3 门）。**故意没有 → confirmed**：
    # 人工终审必须新建 manual/review 决策行——source 不可变，原地升格会把人工
    # 最终身份落在 machine source 上（可被机器撤回，S1-F 已实证的 INV-4 失效
    # 模式），且 confirmed+自动来源行会绕过 E-02 人工来源语义。
    ASSIGNMENT_STATUS_AUTO_CONFIRMED: frozenset(
        {ASSIGNMENT_STATUS_REJECTED, ASSIGNMENT_STATUS_UNASSIGNED}
    ),
}


def validate_status_source_combination(
    status: str, source: str, score: float | None,
) -> None:
    """跨字段不变量：S4 冷启动自动确认的组合约束（构造期与持久化共用同一实现）。

    - ``auto_confirmed`` 只能由 ``ordered_auto_confirm`` 来源承载；
    - ``ordered_auto_confirm`` 行不得 ``confirmed``——人工终审必须新建
      manual/review 决策行（source 不可变，原地升格即 INV-4 失效模式）；
    - ``ordered_auto_confirm`` 的 ``score`` 恒 NULL（BD-4：位置配对不得伪造
      相似度证据）。

    AUD-027 方案 B：仓储持久化前（``add_assignments``/``update_assignment``）
    复用本函数，使绕过构造期校验的内存状态也无法落库；错误消息与构造期
    守卫逐字一致。
    """
    if (
        status == ASSIGNMENT_STATUS_AUTO_CONFIRMED
        and source != ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM
    ):
        raise ValidationError(
            "auto_confirmed status requires source=ordered_auto_confirm"
        )
    if source == ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM:
        if status == ASSIGNMENT_STATUS_CONFIRMED:
            raise ValidationError(
                "ordered_auto_confirm rows cannot be confirmed in place; "
                "human final confirmation must be a new manual/review decision row"
            )
        if score is not None:
            raise ValidationError(
                "ordered_auto_confirm carries no similarity evidence "
                "(score must stay NULL)"
            )


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
        # S4 冷启动位置自动确认的组合守卫（owner 裁决 2026-10-10；AUD-027 方案 B
        # 起与仓储持久化校验共用 validate_status_source_combination 同一实现，
        # 绕过构造期校验的内存状态无法经 add_assignments/update_assignment 落库）。
        # 仓储反序列化按构造函数重建行，同样过本守卫——库内出现非法组合即
        # fail-closed，不会静默复活。
        validate_status_source_combination(
            self.status, self.source, self.score)
        object.__setattr__(
            self, "sort_snapshot", MappingProxyType(deepcopy(dict(self.sort_snapshot))),
        )

    def confirm(self, sort_snapshot: dict[str, Any] | None = None) -> None:
        """人工确认：suggested → confirmed，保存排序快照与确认时间。

        S4 守卫：``ordered_auto_confirm`` 来源禁止经本方法确认——人工终审必须
        新建 manual/review 决策行，自动决策行保留为可追溯历史（source 不可变）。
        """
        if self.source == ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM:
            raise ValidationError(
                "ordered_auto_confirm rows cannot be confirmed in place; "
                "human final confirmation must be a new manual/review decision row"
            )
        self._transition_to(ASSIGNMENT_STATUS_CONFIRMED)
        if sort_snapshot is not None:
            object.__setattr__(
                self, "sort_snapshot", MappingProxyType(deepcopy(dict(sort_snapshot))),
            )
        self.confirmed_at = datetime.now()

    def auto_confirm(self, sort_snapshot: dict[str, Any]) -> None:
        """S4 冷启动位置规则自动确认：suggested → auto_confirmed（机器侧）。

        自动确认的**专用入口**（不允许经 confirm/reject 等通用入口制造）：

        - 仅 ``ordered_auto_confirm`` 来源可进入——来源在构造时确定，本守卫
          防止把样本匹配/人工来源行误升格为自动确认；
        - ``score`` 非 None 即拒绝（BD-4：位置配对不得伪造相似度证据）；
        - ``sort_snapshot`` 必填——自动确认必须携带位次依据（如 sort_key /
          first_captured_at / auto_confirmed_at），保证可追溯；
        - ``confirmed_at`` 保持 None：该字段语义是"人工最终确认时刻"，只由
          人工终审产生的新决策行携带（C-3 接线）。
        """
        if self.source != ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM:
            raise ValidationError(
                "auto_confirm is restricted to source=ordered_auto_confirm"
            )
        if self.score is not None:
            raise ValidationError(
                "auto_confirm refuses a similarity score; positional pairing "
                "carries no evidence (BD-4)"
            )
        self._transition_to(ASSIGNMENT_STATUS_AUTO_CONFIRMED)
        object.__setattr__(
            self, "sort_snapshot", MappingProxyType(deepcopy(dict(sort_snapshot))),
        )

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
