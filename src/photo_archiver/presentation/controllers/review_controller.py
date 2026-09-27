"""Controller coordinating the recognition-review workflow with the UI.

落 Phase 2 Step 12 裁决 A：approve/reject 不包装 Worker——DB 操作 <10ms，
同步调即可，避免本轮过度工程。Controller 持 ReviewRecognitionUseCase 直接调，
UI 拿结果后刷新照片列表状态列。

list_pending 走 RecognitionRepository 而非 UseCase——ReviewRecognitionUseCase
接口只暴露 approve/reject/bulk_*，list 是读侧查询不属复核业务变更，
故本 controller 直接持 RecognitionRepository 做只读查询。
"""

from uuid import UUID

from PySide6.QtCore import QObject

from photo_archiver.application import ReviewRecognitionUseCase
from photo_archiver.domain import (
    PersonRepository,
    Photo,
    PhotoRepository,
    RecognitionRepository,
    RecognitionResult,
)
from photo_archiver.presentation.ui_text import REVIEW_PERSON_UNKNOWN


class ReviewController(QObject):
    """Bridge recognition-review use case calls to synchronous UI refresh.

    All methods are synchronous because the underlying service touches only
    SQLite (sub-10ms even for bulk). If profiling later shows UI jank on
    1000+ bulk operations, wrap bulk_approve/bulk_reject in Worker tasks.
    """

    def __init__(
        self,
        use_case: ReviewRecognitionUseCase,
        recognition_repository: RecognitionRepository,
        photo_repository: PhotoRepository | None = None,
        person_repository: PersonRepository | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with its use case and read-side repository.

        Args:
            use_case: approve/reject/bulk_* mutations.
            recognition_repository: read-side for list_pending (not in UseCase).
            photo_repository: optional read-side resolving human-readable photo
                labels for review rows (ADR-036: names instead of bare UUIDs).
            person_repository: optional read-side resolving person display names.
        """
        super().__init__(parent)
        self._use_case = use_case
        self._recognition_repository = recognition_repository
        self._photo_repository = photo_repository
        self._person_repository = person_repository

    def resolve_row_labels(self, result: RecognitionResult) -> tuple[str, str]:
        """Return (photo label, person label) for a review row.

        Falls back to the raw UUIDs when the entity is gone or no lookup
        repository was injected; a deleted person renders as 未知人员
        (matching the v2.4.0 deletion semantics: person_id SET NULL).
        """
        photo_label = str(result.photo_id)
        if self._photo_repository is not None:
            photo = self._photo_repository.find_by_id(result.photo_id)
            if photo is not None:
                photo_label = photo.original_name or photo.path.raw_path.name
        person_label = str(result.person_id) if result.person_id is not None else REVIEW_PERSON_UNKNOWN
        if self._person_repository is not None and result.person_id is not None:
            person = self._person_repository.find_by_id(result.person_id)
            if person is not None:
                person_label = person.name
        return photo_label, person_label

    def photo_for(self, result: RecognitionResult) -> Photo | None:
        """Return the photo entity behind a review row (Batch 5 read-side).

        Feeds the dialog's thumbnail channel (source path for the existing
        async loader); ``None`` when the entity is gone or no lookup
        repository was injected — the row then simply renders without a
        thumbnail, never via a synchronous disk read in the widget.
        """
        if self._photo_repository is None:
            return None
        return self._photo_repository.find_by_id(result.photo_id)

    def list_pending(self) -> list[RecognitionResult]:
        """Return all recognition results awaiting user review."""
        return self._recognition_repository.list_pending()

    def list_persons(self) -> list[tuple[UUID, str]]:
        """Return ``(person_id, display name)`` pairs for the D-1 identity picker.

        Stage 4 D-1: the new recognition chain projects ``person_id = NULL``, so
        a reviewer must be able to *name* the person when approving. Returns an
        empty list when no person repository was injected (caller disables the
        picker rather than blocking the queue outright).
        """
        if self._person_repository is None:
            return []
        pairs: list[tuple[UUID, str]] = []
        for person in self._person_repository.list_all():
            if person.id is not None:
                pairs.append((person.id, person.name))
        return pairs

    def approve(
        self,
        result_id: UUID,
        person_id: UUID | None = None,
    ) -> RecognitionResult | None:
        """Mark a single pending result as approved; return the transitioned result.

        ``person_id`` (Stage 4 D-1) carries the human-decided identity so the
        approved row stays reachable by the archive planner.
        """
        return self._use_case.approve(result_id, person_id)

    def reject(self, result_id: UUID) -> RecognitionResult | None:
        """Mark a single pending result as rejected; return the transitioned result."""
        return self._use_case.reject(result_id)

    def bulk_approve(
        self,
        result_ids: tuple[UUID, ...],
        person_id: UUID | None = None,
    ) -> int:
        """Approve each pending result in the batch; return how many transitioned.

        ``person_id`` (Stage 4 D-1) only fills rows without an identity yet.
        """
        return self._use_case.bulk_approve(result_ids, person_id)

    def bulk_reject(self, result_ids: tuple[UUID, ...]) -> int:
        """Reject each pending result in the batch; return how many transitioned."""
        return self._use_case.bulk_reject(result_ids)
