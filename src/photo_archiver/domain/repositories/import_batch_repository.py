"""Import batch repository interface."""

from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities import ImportBatch, ImportDraftRow


class ImportBatchRepository(Protocol):
    """Define persistence operations for import batches and their draft rows."""

    def add_batch(self, batch: ImportBatch) -> None:
        """Persist a new import batch (draft status)."""

    def get_batch(self, batch_id: UUID) -> ImportBatch | None:
        """Return the batch or ``None`` when it does not exist."""

    def set_batch_status(self, batch_id: UUID, status: str, confirmed_at=None) -> None:
        """Move a batch through its lifecycle (draft → confirmed/cancelled)."""

    def replace_draft_rows(self, batch_id: UUID, rows: list[ImportDraftRow]) -> None:
        """Replace all draft rows of a batch (used by re-parse and splits)."""

    def list_draft_rows(self, batch_id: UUID) -> list[ImportDraftRow]:
        """Return the batch's draft rows ordered by ``order_index``."""

    def list_batches(self) -> list[ImportBatch]:
        """Return all batches, newest first (batch source review)."""

    def remove_batch(self, batch_id: UUID) -> int:
        """Delete the batch row; draft rows cascade via FK（界面优化 §4.3）.

        Returns 1 when the batch existed, 0 otherwise (idempotent). People are
        never touched — ``people.source_batch_id`` is a soft reference without
        an FK and keeps its (now dangling) value.
        """
