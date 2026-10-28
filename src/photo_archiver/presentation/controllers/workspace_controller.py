"""Translate read-only workspace facts into presentation guidance."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from photo_archiver.application.dtos.workspace import ModelAvailability, WorkspaceStatus
from photo_archiver.presentation import ui_text as text

NextAction = Literal["import", "scan", "review", "settings", "model"]


class WorkspaceQuery(Protocol):
    """Read-side port consumed without coupling to repository implementations."""

    def execute(self, archive_root: Path | None) -> WorkspaceStatus:
        """Return current workspace facts."""
        ...


@dataclass(frozen=True, slots=True)
class ActionGuidance:
    """Availability and an actionable explanation for one workflow."""

    enabled: bool
    tooltip: str
    next_action: NextAction | None = None


class WorkspaceController:
    """Query once per workspace change; selection changes only render cached facts."""

    def __init__(self, query: WorkspaceQuery) -> None:
        self._query = query
        self.status: WorkspaceStatus | None = None

    def refresh(self, archive_root: Path | None) -> WorkspaceStatus:
        """Refresh the shared snapshot used by all workflow actions."""
        self.status = self._query.execute(archive_root)
        return self.status

    def feature_guidance(self) -> ActionGuidance:
        """Explain the feature-extraction (scan-integrated) state.

        任务书 §3：特征提取随扫描自动进行，**不再要求已导入名单**；门槛只
        剩模型可用与照片存在。缺特征的照片由下一次扫描按增量规则自动补齐。
        """
        status = self.status
        if status is None:
            return ActionGuidance(False, text.WORKSPACE_UNKNOWN)
        if not status.has_photos:
            return ActionGuidance(False, text.REFUSAL_NO_PHOTOS, "scan")
        if status.model_availability is not ModelAvailability.AVAILABLE:
            reason = (text.WORKSPACE_MODEL_MISSING
                      if status.model_availability is ModelAvailability.MISSING
                      else text.WORKSPACE_MODEL_UNKNOWN)
            return ActionGuidance(False, reason, "model")
        if status.pending_match_count:
            return ActionGuidance(
                True, text.WORKSPACE_MATCH_READY.format(count=status.pending_match_count),
                "scan",
            )
        return ActionGuidance(True, text.WORKSPACE_FEATURES_READY, "review")

    def archive_guidance(self) -> ActionGuidance:
        """Keep root setup reachable even before there are approved photos."""
        status = self.status
        if status is None:
            return ActionGuidance(False, text.WORKSPACE_UNKNOWN)
        if not status.archive_root_available:
            return ActionGuidance(False, text.WORKSPACE_ROOT_UNAVAILABLE, "settings")
        if not status.archivable_count:
            return ActionGuidance(False, text.WORKSPACE_ARCHIVE_EMPTY, "review")
        return ActionGuidance(True, text.WORKSPACE_ARCHIVE_READY.format(count=status.archivable_count))

    def review_guidance(self) -> ActionGuidance:
        """An empty review queue remains an inspectable screen."""
        count = self.status.pending_review_count if self.status is not None else 0
        return ActionGuidance(True, text.REVIEW_EMPTY if not count
                              else text.STATUS_PENDING_REVIEW_COUNT.format(count=count))
