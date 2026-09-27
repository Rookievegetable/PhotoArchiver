"""Service implementation for user review of recognition results.

Step 10 implements approve / reject / bulk_approve / bulk_reject as an
Application-layer orchestration over the :class:`RecognitionRepository`.
Each transition validates that the target result is currently ``pending``;
finalized results are skipped silently so bulk operations remain idempotent
under partial re-invocation.

ISSUE-005 fix (Step 13): wrap the status transition in a ``UnitOfWork`` so
the in-memory ``approve()/reject()`` and the DB-side ``update_status`` commit
atomically. Without a UoW an exception raised by ``update_status`` after the
in-memory flip would leave the entity transitioned but the DB row pending —
the same honesty gap Step 12's ArchiveExecutor closed. The UoW is optional
(``None``) so existing unit tests using in-memory repos keep passing without
a SQLite scope; production wiring injects ``SQLiteUnitOfWork`` via the
``app/services.py`` assembler.
"""

from uuid import UUID

from loguru import logger

from photo_archiver.application.ports import UnitOfWork
from photo_archiver.application.use_cases import ReviewRecognitionUseCase
from photo_archiver.domain import MatchStatus, RecognitionRepository, RecognitionResult


class ReviewRecognitionService(ReviewRecognitionUseCase):
    """Transition pending recognition results through the user-review workflow."""

    def __init__(
        self,
        recognition_repository: RecognitionRepository,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize the service with the recognition repository and optional UoW.

        Args:
            recognition_repository: Persistence target for status transitions.
            unit_of_work: Optional transactional scope. When provided the service
                wraps each ``update_status`` call so the in-memory flip and the
                DB persist commit atomically (ISSUE-005 fix, mirroring
                ArchiveExecutor). When None the service runs without a
                transaction boundary — existing unit tests using in-memory
                repositories rely on this path and MUST NOT be forced to construct
                a SQLite scope.
        """
        self._recognition_repository = recognition_repository
        self._unit_of_work = unit_of_work

    def approve(
        self,
        result_id: UUID,
        person_id: UUID | None = None,
    ) -> RecognitionResult | None:
        """Mark a single pending result as approved and persist the transition.

        ``person_id`` (Stage 4 D-1) records the **human-decided identity** in
        the same write. The new recognition chain always projects
        ``person_id = NULL`` (no ``person_embeddings`` producer), so approving
        without an identity used to yield an APPROVED row the archive planner
        could never select (``WHERE person_id = ? AND status = 'approved'``) —
        i.e. a "final" human result that silently never archives. Callers that
        genuinely have no identity to record pass ``None`` and should surface
        the row as not-yet-archivable rather than imply it is settled.

        Returns:
            The refreshed aggregate after approval, or ``None`` when the result
            was missing or already finalized.
        """
        return self._transition(result_id, MatchStatus.APPROVED, person_id=person_id)

    def reject(self, result_id: UUID) -> RecognitionResult | None:
        """Mark a single pending result as rejected and persist the transition.

        Returns:
            The refreshed aggregate after rejection, or ``None`` when the result
            was missing or already finalized.
        """
        return self._transition(result_id, MatchStatus.REJECTED)

    def bulk_approve(
        self,
        result_ids: tuple[UUID, ...],
        person_id: UUID | None = None,
    ) -> int:
        """Approve each pending result in the batch.

        Args:
            result_ids: Recognition result identifiers to approve.
            person_id: Stage 4 D-1 — human-decided identity written alongside
                the approval. Rows that already carry an identity keep their
                own; passing ``None`` leaves every row's identity untouched.

        Returns:
            How many results actually transitioned (missing or finalized ones
            are skipped silently so the operation is idempotent).
        """
        return self._bulk_transition(result_ids, MatchStatus.APPROVED, person_id=person_id)

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
        person_id: UUID | None = None,
    ) -> RecognitionResult | None:
        """Persist a status transition for a single result.

        Args:
            result_id: The recognition result identifier.
            target: The desired final status.
            person_id: Stage 4 D-1 — the human-decided identity to write with
                an approval. ``None`` leaves the column untouched.

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
            if person_id is not None:
                # Keep the in-memory aggregate honest about what the DB will
                # hold, so the returned entity matches the persisted row.
                result.person_id = person_id
        else:
            result.reject()
        # ISSUE-005 fix: wrap the DB persist in a UoW so an exception after the
        # in-memory flip rolls back the SQLite transaction. ArchiveExecutor
        # established this pattern (review M-1 fix); ReviewRecognitionService
        # follows it so review honesty matches archive honesty. When the UoW is
        # None (in-memory test path) the call runs bare as before.
        if self._unit_of_work is not None:
            with self._unit_of_work:
                affected = self._persist_status(result, target, person_id)
        else:
            affected = self._persist_status(result, target, person_id)
        if affected == 0:
            # Concurrent deletion between find_by_id and update_status: roll back
            # the in-memory transition so the returned aggregate stays honest.
            # The UoW (if active) already rolled the SQLite tx back on this path
            # only if we raise — instead we deliberately return None which the
            # UoW normal-exit branch treats as commit. That commit is a no-op for
            # a 0-affected update so no inconsistency lands on disk.
            logger.warning(
                "Recognition result {} vanished before status persist; not transitioned",
                result_id,
            )
            return None
        logger.info("Recognition result {} -> {}", result_id, target.value)
        return result

    def _persist_status(
        self,
        result: RecognitionResult,
        target: MatchStatus,
        person_id: UUID | None = None,
    ) -> int:
        """Persist the status (and optional identity) for the transitioned row.

        ``update_status`` writes only the status column by default, avoiding the
        wider upsert that ``add()`` would perform (which could overwrite
        photo_id/confidence). Stage 4 D-1 passes ``person_id`` so a manual
        approval can record the decided identity in the same statement.
        """
        return self._recognition_repository.update_status(
            result.id,  # type: ignore[arg-type]  # RecognitionResult.__post_init__ guarantees id is set
            target,
            person_id,
        )

    def _bulk_transition(
        self,
        result_ids: tuple[UUID, ...],
        target: MatchStatus,
        person_id: UUID | None = None,
    ) -> int:
        """Persist status transitions for a batch, returning how many transitioned.

        Stage 4 D-1: a single ``person_id`` applies only to rows that do not
        already carry an identity — an explicit per-row human decision recorded
        earlier must never be overwritten by a later bulk default.
        """
        transitioned = 0
        for result_id in result_ids:
            effective = person_id
            if effective is not None:
                existing = self._recognition_repository.find_by_id(result_id)
                if existing is not None and existing.person_id is not None:
                    effective = None
            if self._transition(result_id, target, person_id=effective) is not None:
                transitioned += 1
        logger.info(
            "Bulk {} transitioned {}/{} result(s)",
            target.value,
            transitioned,
            len(result_ids),
        )
        return transitioned
