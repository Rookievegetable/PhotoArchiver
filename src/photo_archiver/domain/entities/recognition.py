"""Recognition result entity and match status enum."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from photo_archiver.domain.exceptions import ValidationError


class MatchStatus(str, Enum):
    """Lifecycle states for a recognition result awaiting user review.

    Inheriting from ``str`` keeps the enum JSON-serializable without extra
    adapters, which matters because Step 9 persists these values into the
    ``recognition_results`` table.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(slots=True)  # NOT frozen: approve()/reject() mutate status
class RecognitionResult:
    """Represent the outcome of matching a detected face to a person.

    A ``RecognitionResult`` ties one ``Photo`` to at most one ``Person`` and
    carries the match ``confidence`` plus a review ``status``. The aggregate
    is created in the ``PENDING`` state and only transitions to ``APPROVED``
    or ``REJECTED`` via the explicit state-transition methods, which keeps the
    invariant that a finalized result cannot be re-opened.

    ``confidence`` 三态语义（Stage 4 BLK-5 修复）：
    - ``float`` —— 该归属**有**相似度证据（识别期 Top-1 匹配分，或配对确认时
      的样本余弦）；
    - ``None`` —— 该归属**无**相似度证据（按位置配对 / 人工指派确认）。
      此时**不得**写成 ``0.0``——"无证据"与"相似度为零"语义完全不同。

    ISSUE-006 resolution: ``id`` is now typed ``UUID`` (not ``UUID | None``)
    with ``field(default_factory=uuid4)`` so the type signature honestly
    expresses the post-init non-null guarantee — mypy and callers no longer
    need to None-check a field that is always populated after construction.

    ``assignment_id``（S1 / migration 009）区分 approved 行的两种来源，**不是**归档
    资格的判据：
    - ``None`` → **legacy 人工决策**。ADR-045 D-1 的审核批准行属于此类：人工裁决，
      从不经过 Assignment 表。S0 INV-4 要求它们不被 reconcile / rebuild 触碰。
    - 非 ``None`` → **Assignment-derived projection**。其存在性由「该
      ``(photo, person)`` 是否仍有 active supporting Assignment」决定；该字段只是
      **当前支撑引用**，可被 retarget 到另一个支撑（同一 pair 可被多个 Assignment
      支撑）。

    删除人员时 ``cluster_person_assignments`` 经 FK CASCADE 被删，本字段随之置
    NULL；同时 ``person_id`` 也被置 NULL（ADR-052），此类行不参与任何身份判断。
    """

    photo_id: UUID
    confidence: float | None
    id: UUID = field(default_factory=uuid4)
    person_id: UUID | None = None
    status: MatchStatus = MatchStatus.PENDING
    created_at: datetime | None = None
    assignment_id: UUID | None = None

    def __post_init__(self) -> None:
        """Validate fields and initialize generated values."""
        if not isinstance(self.status, MatchStatus):
            # AUD-018-B：与 ``ArchiveRecord.status`` 同口径的构造期类型校验
            # （dataclass 不强制类型——缺此校验时非法状态可直达 DB；本表无
            # DB 层 CHECK，域枚举是唯一状态机，见 ADR-052 记录）。
            raise ValidationError(
                "RecognitionResult status must be a MatchStatus enum"
            )
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValidationError("RecognitionResult confidence must be in [0.0, 1.0]")
        if self.created_at is None:
            self.created_at = datetime.now()

    def approve(self) -> None:
        """Mark the result as approved by the user."""
        self._assert_pending()
        self.status = MatchStatus.APPROVED

    def reject(self) -> None:
        """Mark the result as rejected by the user."""
        self._assert_pending()
        self.status = MatchStatus.REJECTED

    def _assert_pending(self) -> None:
        """Raise if the result has already been finalized."""
        if self.status is not MatchStatus.PENDING:
            raise ValidationError(
                f"RecognitionResult already finalized as {self.status.value}"
            )
