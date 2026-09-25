"""Commands for Stage E pairing operations."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class StartSuggestPairingsCommand:
    """Request one suggestion generation over one clustering generation."""

    cluster_run_id: UUID


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
