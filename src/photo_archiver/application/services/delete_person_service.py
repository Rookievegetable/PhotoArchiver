"""Delete person service — Phase E E-3（ADR-034 D2/D3）.

删除人员的库内登记：预览（嵌入级联 + 识别归属置空计数）→ 确认 → 事务内
删除。**照片全部保留**（D2：人员是归属维度而非照片容器）；人脸嵌入随外键
CASCADE 删除；识别结果行保留、``person_id`` 置空为"未知人员"（既有外键
SET NULL 语义承担）。幂等：不存在的 id 计入 ``missing``，不抛错。
"""

from collections.abc import Sequence
from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.deletion import DeletePersonCommand
from photo_archiver.application.dtos.deletion import PersonDeletionPreview, PersonDeletionResult
from photo_archiver.application.ports import UnitOfWork
from photo_archiver.application.use_cases.deletion import DeletePersonUseCase
from photo_archiver.domain.repositories import (
    FaceEmbeddingRepository,
    PersonRepository,
    PhotoRepository,
    RecognitionRepository,
)


class DeletePersonService(DeletePersonUseCase):
    """Orchestrate previewed, transactional, photo-preserving person deletion."""

    def __init__(
        self,
        person_repository: PersonRepository,
        photo_repository: PhotoRepository,
        recognition_repository: RecognitionRepository,
        face_embedding_repository: FaceEmbeddingRepository,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize the service with its ports.

        Args:
            person_repository: Registration source of truth (E-2 ``remove``).
            photo_repository: Supplies the full photo id set so the preview can
                count the person's recognition rows via the batched
                ``list_by_photo_ids`` push-down (deletion is low-frequency;
                the full-set scan mirrors the ``BackfillContentHashService``
                precedent and avoids widening the recognition Protocol).
            recognition_repository: Orphan-attribution counting for the preview.
            face_embedding_repository: CASCADE counting for the preview.
            unit_of_work: Optional transactional scope; ``None`` persists bare.
        """
        self._people = person_repository
        self._photos = photo_repository
        self._recognition = recognition_repository
        self._embeddings = face_embedding_repository
        self._unit_of_work = unit_of_work

    def preview(self, person_ids: Sequence[UUID]) -> PersonDeletionPreview:
        """Return the embedding/orphan-recognition preview; side-effect free."""
        requested = tuple(dict.fromkeys(person_ids))
        missing = tuple(pid for pid in requested if self._people.find_by_id(pid) is None)
        missing_set = set(missing)
        existing = [pid for pid in requested if pid not in missing_set]
        existing_set = set(existing)

        embedding_count = (
            sum(1 for pid in self._embeddings.list_all() if pid in existing_set)
            if existing
            else 0
        )
        recognition_count = 0
        if existing:
            photo_ids = [
                photo.id for photo in self._photos.list_all() if photo.id is not None
            ]
            recognition_count = sum(
                1
                for row in self._recognition.list_by_photo_ids(photo_ids)
                if row.person_id in existing_set
            )
        return PersonDeletionPreview(
            person_ids=tuple(existing),
            missing_ids=missing,
            embedding_count=embedding_count,
            recognition_count=recognition_count,
        )

    def execute(self, command: DeletePersonCommand) -> PersonDeletionResult:
        """Delete the confirmed people; audit-log the outcome."""
        preview = self.preview(command.person_ids)

        def _remove_all() -> int:
            removed = 0
            for person_id in preview.person_ids:
                removed += self._people.remove(person_id)
            return removed

        if self._unit_of_work is not None:
            with self._unit_of_work:
                removed = _remove_all()
        else:
            removed = _remove_all()
        logger.info(
            "AUDIT delete-person actor=local-user removed={} embedding_cascade={} "
            "recognition_orphaned={} missing={} person_ids={}",
            removed,
            preview.embedding_count,
            preview.recognition_count,
            preview.missing_count,
            list(preview.person_ids),
        )
        return PersonDeletionResult(
            requested=preview.person_count + preview.missing_count,
            removed=removed,
            missing=preview.missing_count,
            embedding_cascade=preview.embedding_count,
            recognition_orphaned=preview.recognition_count,
        )
