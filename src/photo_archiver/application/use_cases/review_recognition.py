"""Use case boundary for the user recognition-review workflow."""

from uuid import UUID

from photo_archiver.domain import RecognitionResult


class ReviewRecognitionUseCase:
    """Define the user-review use case contract.

    Implementations transition pending :class:`RecognitionResult` aggregates
    between ``approved`` / ``rejected`` statuses, either one at a time or in
    bulk, and persist the outcome through the recognition repository.
    """

    def approve(self, result_id: UUID) -> RecognitionResult | None:  # type: ignore[empty-body]
        """Mark a single pending result as approved."""
        raise NotImplementedError

    def reject(self, result_id: UUID) -> RecognitionResult | None:  # type: ignore[empty-body]
        """Mark a single pending result as rejected."""
        raise NotImplementedError

    def bulk_approve(self, result_ids: tuple[UUID, ...]) -> int:  # type: ignore[empty-body]
        """Approve each pending result in the batch; return how many transitioned."""
        raise NotImplementedError

    def bulk_reject(self, result_ids: tuple[UUID, ...]) -> int:  # type: ignore[empty-body]
        """Reject each pending result in the batch; return how many transitioned."""
        raise NotImplementedError
