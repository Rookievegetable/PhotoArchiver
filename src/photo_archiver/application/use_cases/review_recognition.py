"""Use case boundary for the user recognition-review workflow."""

from uuid import UUID

from photo_archiver.domain import RecognitionResult


class ReviewRecognitionUseCase:
    """Define the user-review use case contract.

    Implementations transition pending :class:`RecognitionResult` aggregates
    between ``approved`` / ``rejected`` statuses, either one at a time or in
    bulk, and persist the outcome through the recognition repository.
    """

    def approve(
        self,
        result_id: UUID,
        person_id: UUID | None = None,  # type: ignore[empty-body]
    ) -> RecognitionResult | None:
        """Mark a single pending result as approved.

        ``person_id`` (Stage 4 D-1) is the human-decided identity written with
        the approval so the row can actually reach the archive planner.
        """
        raise NotImplementedError

    def reject(self, result_id: UUID) -> RecognitionResult | None:  # type: ignore[empty-body]
        """Mark a single pending result as rejected."""
        raise NotImplementedError

    def bulk_approve(
        self,
        result_ids: tuple[UUID, ...],
        person_id: UUID | None = None,  # type: ignore[empty-body]
    ) -> int:
        """Approve each pending result in the batch; return how many transitioned.

        ``person_id`` (Stage 4 D-1) only fills rows that carry no identity yet.
        """
        raise NotImplementedError

    def bulk_reject(self, result_ids: tuple[UUID, ...]) -> int:  # type: ignore[empty-body]
        """Reject each pending result in the batch; return how many transitioned."""
        raise NotImplementedError
