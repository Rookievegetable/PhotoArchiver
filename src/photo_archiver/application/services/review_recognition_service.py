"""Service implementation for user review of recognition results.

Step 10 implements approve / reject / bulk_approve / bulk_reject as an
Application-layer orchestration over the :class:`RecognitionRepository`.
Each transition validates that the target result is currently ``pending``;
finalized results are skipped silently so bulk operations remain idempotent
under partial re-invocation.
"""

from uuid import UUID

from loguru import logger

from photo_archiver.application.use_cases import ReviewRecognitionUseCase
from photo_archiver.domain import MatchStatus, RecognitionRepository, RecognitionResult


class ReviewRecognitionService(ReviewRecognitionUseCase):
    """Transition pending recognition results through the user-review workflow."""

    def __init__(
        self,
        recognition_repository: RecognitionRepository,
    ) -> None:
        """Initialize the service with the recognition repository.

        Args:
            recognition_repository: Persistence target for status transitions.
        """
        self._recognition_repository = recognition_repository

    def approve(self, result_id: UUID) -> RecognitionResult | None:
        """Mark a single pending result as approved and persist the transition.

        Returns:
            The refreshed aggregate after approval, or ``None`` when the result
            was missing or already finalized.
        """
        return self._transition(result_id, MatchStatus.APPROVED)

    def reject(self, result_id: UUID) -> RecognitionResult | None:
        """Mark a single pending result as rejected and persist the transition.

        Returns:
            The refreshed aggregate after rejection, or ``None`` when the result
            was missing or already finalized.
        """
        return self._transition(result_id, MatchStatus.REJECTED)

    def bulk_approve(self, result_ids: tuple[UUID, ...]) -> int:
        """Approve each pending result in the batch.

        Args:
            result_ids: Recognition result identifiers to approve.

        Returns:
            How many results actually transitioned (missing or finalized ones
            are skipped silently so the operation is idempotent).
        """
        return self._bulk_transition(result_ids, MatchStatus.APPROVED)

    def bulk_reject(self, result_ids: tuple[UUID, ...]) -> int:
        """Reject each pending result in the batch.

        Args:
            result_ids: Recognition result identifiers to reject.

        Returns:
            How many results actually transitioned.
        """
        return self._bulk_transition(result_ids, MatchStatus.REJECTED)

    def _transition(
        self,
        result_id: UUID,
        target: MatchStatus,
    ) -> RecognitionResult | None:
        """Persist a status transition for a single result.

        Args:
            result_id: The recognition result identifier.
            target: The desired final status.

        Returns:
            The refreshed aggregate, or ``None`` when the result is missing or
            already finalized.
        """
        result = self._recognition_repository.find_by_id(result_id)
        if result is None:
            logger.warning("Recognition result {} not found", result_id)
            return None
        if result.status is not MatchStatus.PENDING:
            logger.info(
                "Recognition result {} already finalized as {}; skipping",
                result_id,
                result.status.value,
            )
            return None
        if target is MatchStatus.APPROVED:
            result.approve()
        else:
            result.reject()
        # update_status persists only the status column, avoiding the wider
        # upsert that add() would perform (which could overwrite photo_id/person_id).
        self._recognition_repository.update_status(result.id, target)
        logger.info("Recognition result {} -> {}", result_id, target.value)
        return result

    def _bulk_transition(
        self,
        result_ids: tuple[UUID, ...],
        target: MatchStatus,
    ) -> int:
        """Persist status transitions for a batch, returning how many transitioned."""
        transitioned = 0
        for result_id in result_ids:
            if self._transition(result_id, target) is not None:
                transitioned += 1
        logger.info(
            "Bulk {} transitioned {}/{} result(s)",
            target.value,
            transitioned,
            len(result_ids),
        )
        return transitioned
