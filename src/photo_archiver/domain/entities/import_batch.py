"""Import batch aggregate — the traceable container of one roster import.

Stage A of the people-import redesign (owner plan §3.1): a draft batch keeps
the parsed, user-editable rows BEFORE anything touches the formal people
registry. Cancel leaves the draft in place; confirm atomically writes people
with their stable roster order.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

BATCH_STATUS_DRAFT = "draft"
BATCH_STATUS_CONFIRMED = "confirmed"
BATCH_STATUS_CANCELLED = "cancelled"

DRAFT_ACTION_CREATE = "create"
DRAFT_ACTION_MERGE_EXISTING = "merge_existing"
DRAFT_ACTION_SKIP = "skip"


@dataclass(slots=True)
class ImportBatch:
    """One roster-import container with its parse options and lifecycle status."""

    file_name: str
    file_hash: str
    source_type: str
    encoding: str | None = None
    delimiter: str | None = None
    has_header: bool = True
    sheet_name: str | None = None
    status: str = BATCH_STATUS_DRAFT
    id: UUID | None = None
    created_at: datetime | None = None
    confirmed_at: datetime | None = None

    def __post_init__(self) -> None:
        """Initialize generated values."""
        if self.id is None:
            self.id = uuid4()
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass(slots=True)
class ImportDraftRow:
    """One editable draft row: raw cell values plus the parsed person fields.

    ``warnings`` carries non-blocking parse advisories (multi-name cells,
    group titles, duplicates). ``action`` is the user's confirm-time decision;
    splitting one raw row into several people replaces the row in place.
    """

    batch_id: UUID
    source_row: int
    raw_values: list[str] = field(default_factory=list)
    parsed_name: str = ""
    parsed_identity: str | None = None
    parsed_department: str | None = None
    parsed_note: str | None = None
    parsed_group: str | None = None
    warnings: tuple[tuple[str, str], ...] = ()
    action: str = DRAFT_ACTION_CREATE
    merge_target_id: UUID | None = None
    order_index: int = 0
    id: UUID | None = None

    def __post_init__(self) -> None:
        """Initialize generated values."""
        if self.id is None:
            self.id = uuid4()
