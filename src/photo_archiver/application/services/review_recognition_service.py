"""Service implementation for user review of recognition results.

S1-F：**带身份的批准**（``person_id is not None``）是人工身份决策——委托
:class:`IdentityDecisionService` 走 ``Assignment(source='review', confirmed) →
ProjectionReconciler → approved(assignment_id≠NULL)`` 唯一链（S0 INV-3，
D-2 = B：照片未聚类则 fail-closed 抛 :class:`PhotoNotClusteredError`）。

**不带身份的批准**（``person_id is None``，D-1 语义：显式告警后的"已处理未定
身份"）仍就地翻转 pending 行为 ``approved``——它不产生任何身份归属，落点为
ownership 契约的「匿名孤儿」态（person_id/assignment_id 均 NULL，不可归档、
不被 reconcile 消费），因此不构成第二身份链，也无需 Assignment。

reject / bulk_reject 语义不变（S1-F8）：否决的是审核候选行本身，不触碰
Assignment、不删除他人的 projection。

批量批准沿用既有**逐项**语义（与 ArchiveExecutor 一致）：已聚类 → 成功；
未聚类 → 记录日志并跳过（行留在队列可见），不因单项失败中断整批。
"""

from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.identity_decision import (
    ConfirmReviewDecisionCommand,
)
from photo_archiver.application.ports import UnitOfWork
from photo_archiver.application.services.identity_decision_service import (
    IdentityDecisionService,
)
from photo_archiver.application.use_cases import ReviewRecognitionUseCase
from photo_archiver.domain import MatchStatus, RecognitionRepository, RecognitionResult
from photo_archiver.domain.exceptions import PhotoNotClusteredError


class ReviewRecognitionService(ReviewRecognitionUseCase):
    """Transition pending recognition results through the user-review workflow."""

    def __init__(
        self,
        recognition_repository: RecognitionRepository,
        unit_of_work: UnitOfWork | None = None,
        identity_decision_service: IdentityDecisionService | None = None,
    ) -> None:
        """Initialize the service with its collaborators.

        Args:
            recognition_repository: Persistence target for status transitions.
            unit_of_work: Optional transactional scope for the non-identity
                transitions (reject / approve-without-identity). When provided the
                service wraps each ``update_status`` call so the in-memory flip and
                the DB persist commit atomically (ISSUE-005 fix).
            identity_decision_service: Required for **identity approvals**
                (``person_id is not None``) since S1-F. When absent, an identity
                approval raises :class:`ValidationError` instead of silently
                writing an unowned approved row.
        """
        self._recognition_repository = recognition_repository
        self._unit_of_work = unit_of_work
        self._decisions = identity_decision_service

    def approve(
        self,
        result_id: UUID,
        person_id: UUID | None = None,
        cluster_id: UUID | None = None,
    ) -> RecognitionResult | None:
        """Approve one pending result.

        **带身份**（``person_id is not None``）→ 人工身份决策：经
        :class:`IdentityDecisionService` 产生 ``Assignment(source='review',
        confirmed)`` 并 reconcile 出带 ``assignment_id`` 的投影（D-2 = B：照片
        未聚类抛 :class:`PhotoNotClusteredError`，由调用方显式处理）。

        **不带身份**（``person_id is None``，D-1：显式告警后的"已处理未定身份"）
        → 就地翻转 pending 行为 approved，不产生归属（匿名孤儿态，不可归档）。

        Returns:
            The refreshed aggregate after approval, or ``None`` when the result
            was missing or already finalized.
        """
        if person_id is not None:
            return self._approve_with_identity(result_id, person_id, cluster_id)
        return self._transition(result_id, MatchStatus.APPROVED)

    def _approve_with_identity(
        self, result_id: UUID, person_id: UUID, cluster_id: UUID | None = None,
    ) -> RecognitionResult | None:
        """S1-F：身份批准走 Assignment → ProjectionReconciler 唯一链。"""
        if self._decisions is None:
            from photo_archiver.domain.exceptions import ValidationError

            raise ValidationError(
                "identity approval requires the identity decision service "
                "(S1-F); direct approved writes are forbidden since migration 009"
            )
        result = self._recognition_repository.find_by_id(result_id)
        if result is None:
            logger.warning("Recognition result {} not found", result_id)
            return None
        if result.status is not MatchStatus.PENDING:
            logger.info(
                "Recognition result {} already finalized as {}; skipping",
                result_id, result.status.value,
            )
            return None
        outcome = self._decisions.confirm_from_review(
            ConfirmReviewDecisionCommand(
                result_id=result_id, photo_id=result.photo_id, person_id=person_id,
                cluster_id=cluster_id,
            )
        )
        # 返回与持久化一致的聚合：pending 行被复用为投影（D-3）。
        return self._recognition_repository.find_by_id(outcome.projection.id)

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
        """Approve each pending result in the batch（既有**逐项**语义）。

        S1-F：带身份的批准逐项走决策链；**未聚类照片按 D-2 = B 跳过**（记录
        日志、行留在队列可见），不因单项失败中断整批、不弹模态框。

        Returns:
            How many results actually transitioned (missing, finalized or
            unclustered ones are skipped so the operation stays idempotent).
        """
        transitioned = 0
        for result_id in result_ids:
            try:
                if self.approve(result_id, person_id) is not None:
                    transitioned += 1
            except PhotoNotClusteredError:
                logger.warning(
                    "Bulk approve skipped result {}: photo not clustered (D-2=B); "
                    "run clustering first",
                    result_id,
                )
        return transitioned

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
