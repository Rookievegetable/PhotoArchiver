"""DTOs for photo-level ignore/restore operations（界面优化 §3.2/§3.3）.

批量忽略/恢复按照片逐项提交、允许部分成功：每项独立报告成功/跳过/失败，
不把部分成功报告为整批成功。``revoked_projections`` 记录该项同步撤销的
既有归属投影数（忽略项），``reestablished`` 恒为 0——恢复只恢复参与资格，
不自动恢复以前撤销的投影（§3.2.7）。
"""

from dataclasses import dataclass
from uuid import UUID

OUTCOME_IGNORED = "ignored"
OUTCOME_RESTORED = "restored"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PhotoIgnoreOutcome:
    """Per-photo outcome of one ignore/restore batch item."""

    photo_id: UUID
    outcome: str  # ignored | restored | skipped | failed
    reason: str | None = None
    revoked_projections: int = 0

    @property
    def succeeded(self) -> bool:
        """Return whether the item actually changed state."""
        return self.outcome in (OUTCOME_IGNORED, OUTCOME_RESTORED)


@dataclass(frozen=True, slots=True)
class PhotoIgnoreResult:
    """Outcome of one ignore/restore batch; partial success is preserved."""

    cluster_run_id: UUID
    outcomes: tuple[PhotoIgnoreOutcome, ...]

    @property
    def succeeded_count(self) -> int:
        """Return how many items changed state."""
        return sum(1 for item in self.outcomes if item.succeeded)

    @property
    def skipped_count(self) -> int:
        """Return how many items were skipped (with reasons)."""
        return sum(1 for item in self.outcomes if item.outcome == OUTCOME_SKIPPED)

    @property
    def failed_count(self) -> int:
        """Return how many items failed."""
        return sum(1 for item in self.outcomes if item.outcome == OUTCOME_FAILED)

    @property
    def revoked_projections(self) -> int:
        """Return the total projections revoked by this batch."""
        return sum(item.revoked_projections for item in self.outcomes)
