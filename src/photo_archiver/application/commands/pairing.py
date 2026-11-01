"""Commands for Stage E pairing operations."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class StartSuggestPairingsCommand:
    """Request one suggestion generation over one clustering generation.

    追加轮 28（Owner：只匹配选定的照片批次与人员名单批次）：
    ``source_batch_id`` 非空时，建议的人员侧只取该名单导入批次的成员
    （样本匹配与位置配对同口径收窄）；``None``＝全库名单（历史行为）。
    """

    cluster_run_id: UUID
    source_batch_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ConfirmAssignmentCommand:
    """Confirm one suggested assignment (人工确认)."""

    assignment_id: UUID


@dataclass(frozen=True, slots=True)
class RejectAssignmentCommand:
    """Reject one suggested assignment (人工拒绝)."""

    assignment_id: UUID


@dataclass(frozen=True, slots=True)
class UnassignClusterCommand:
    """Clear the active assignment of a cluster (解除映射)."""

    cluster_id: UUID


@dataclass(frozen=True, slots=True)
class AssignClusterPersonCommand:
    """Manually assign a person to a cluster (改派/新增指派——人工即确认)."""

    cluster_id: UUID
    person_id: UUID


@dataclass(frozen=True, slots=True)
class SetClusterStateCommand:
    """Mark a cluster unknown (标记陌生人) or ignored (忽略组)."""

    cluster_id: UUID
    state: str  # "unknown" | "ignored"
