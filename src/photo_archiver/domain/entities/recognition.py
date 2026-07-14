"""Recognition result entity and match status enum."""

from dataclasses import dataclass
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


@dataclass(slots=True)
class RecognitionResult:
    """Represent the outcome of matching a detected face to a person.

    A ``RecognitionResult`` ties one ``Photo`` to at most one ``Person`` and
    carries the match ``confidence`` plus a review ``status``. The aggregate
    is created in the ``PENDING`` state and only transitions to ``APPROVED``
    or ``REJECTED`` via the explicit state-transition methods, which keeps the
    invariant that a finalized result cannot be re-opened.
    """

    photo_id: UUID
    confidence: float
    id: UUID | None = None
    person_id: UUID | None = None
    status: MatchStatus = MatchStatus.PENDING
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate fields and initialize generated values."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValidationError("RecognitionResult confidence must be in [0.0, 1.0]")
        if self.id is None:
            self.id = uuid4()
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
