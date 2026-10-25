"""Delete person service — Phase E E-3（ADR-034 D2/D3）.

删除人员的库内登记：预览（嵌入级联 + 识别归属置空计数）→ 确认 → 事务内
删除。**照片全部保留**（D2：人员是归属维度而非照片容器）；人脸嵌入随外键
CASCADE 删除；识别结果行保留、``person_id`` 置空为"未知人员"（既有外键
SET NULL 语义承担）。幂等：不存在的 id 计入 ``missing``，不抛错。
"""

from collections.abc import Sequence
from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.deletion import (
    ClearAllPeopleCommand,
    DeletePeopleByBatchCommand,
    DeletePersonCommand,
)
from photo_archiver.application.dtos.deletion import (
    BatchRosterDeletionPreview,
    BatchRosterDeletionResult,
    PersonDeletionPreview,
    PersonDeletionResult,
)
from photo_archiver.application.ports import UnitOfWork
from photo_archiver.application.use_cases.deletion import DeletePersonUseCase
from photo_archiver.domain.entities.person import Person
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
        import_batch_repository=None,
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
            import_batch_repository: Batch record/draft cleanup port（界面优化
                §4.3）；``None`` 时批次清理方法不可用（构造期不要求）。
        """
        self._people = person_repository
        self._photos = photo_repository
        self._recognition = recognition_repository
        self._embeddings = face_embedding_repository
        self._unit_of_work = unit_of_work
        self._import_batches = import_batch_repository

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

    # ── 界面优化 §4.3：按批次删除 / 清空全部人员 ────────────────────────

    def _batch_members(self, batch_id: UUID) -> tuple[Person, ...]:
        """Current batch members by execution-time ``source_batch_id`` query.

        人员合并可能改写批次归属（confirm 的 merge/查重降级都会把既有人员
        的 ``source_batch_id`` 改写为本批次）——删除范围必须基于执行时点的
        当前归属，不得信任历史导入数量。
        """
        return tuple(
            person for person in self._people.list_all()
            if person.source_batch_id == batch_id
        )

    def _batch_preview(
        self, person_ids: Sequence[UUID], people_names: Sequence[str],
        batch_id: UUID | None,
    ) -> BatchRosterDeletionPreview:
        """Assemble the roster-level preview over the resolved member set."""
        base = self.preview(person_ids)
        batch_record_found = False
        draft_row_count = 0
        if batch_id is not None and self._import_batches is not None:
            batch_record_found = self._import_batches.get_batch(batch_id) is not None
            draft_row_count = len(self._import_batches.list_draft_rows(batch_id))
        return BatchRosterDeletionPreview(
            person_ids=tuple(base.person_ids),
            people_names=tuple(people_names),
            missing_ids=tuple(base.missing_ids),
            embedding_count=base.embedding_count,
            recognition_count=base.recognition_count,
            batch_record_found=batch_record_found,
            draft_row_count=draft_row_count,
        )

    def preview_batch(self, batch_id: UUID) -> BatchRosterDeletionPreview:
        """Preview deleting one batch's current members（批量删除确认流）."""
        members = self._batch_members(batch_id)
        return self._batch_preview(
            tuple(person.id for person in members if person.id is not None),
            tuple(person.name for person in members),
            batch_id,
        )

    def preview_clear_all(self) -> BatchRosterDeletionPreview:
        """Preview deleting every person in the registry（清空确认流）."""
        everyone = tuple(self._people.list_all())
        return self._batch_preview(
            tuple(person.id for person in everyone if person.id is not None),
            tuple(person.name for person in everyone),
            None,
        )

    def execute_batch(
        self, command: DeletePeopleByBatchCommand,
    ) -> BatchRosterDeletionResult:
        """Delete the batch's current members; optionally the batch + drafts.

        单事务边界（§8.5）：人员删除与可选的批次记录/草稿清理在同一个
        unit of work 内——清理失败回滚整个删除，绝不误报全部成功。级联
        计数取自删除前的同一事务内预览（与 preview() 同口径）。
        """
        batch_id = command.batch_id

        def _run() -> BatchRosterDeletionResult:
            members = self._batch_members(batch_id)
            member_ids = [person.id for person in members if person.id is not None]
            base = self.preview(tuple(member_ids))
            removed = 0
            for person_id in base.person_ids:
                assert person_id is not None  # 实体 __post_init__ 保证
                removed += self._people.remove(person_id)
            batch_record_deleted = 0
            draft_rows_deleted = 0
            if command.delete_batch_record and self._import_batches is not None:
                draft_rows_deleted = len(self._import_batches.list_draft_rows(batch_id))
                batch_record_deleted = self._import_batches.remove_batch(batch_id)
            return BatchRosterDeletionResult(
                requested=base.person_count + base.missing_count,
                removed=removed,
                missing=base.missing_count,
                embedding_cascade=base.embedding_count,
                recognition_orphaned=base.recognition_count,
                batch_record_deleted=batch_record_deleted,
                draft_rows_deleted=draft_rows_deleted,
            )

        if self._unit_of_work is not None:
            with self._unit_of_work:
                result = _run()
        else:
            result = _run()
        logger.info(
            "AUDIT delete-people-by-batch actor=local-user batch={} removed={} "
            "embedding_cascade={} recognition_orphaned={} batch_record_deleted={} "
            "draft_rows_deleted={}",
            batch_id, result.removed, result.embedding_cascade,
            result.recognition_orphaned, result.batch_record_deleted,
            result.draft_rows_deleted,
        )
        return result

    def execute_clear_all(self, command: ClearAllPeopleCommand) -> BatchRosterDeletionResult:
        """Delete every person in the registry（单事务，全有或全无）。"""

        def _run() -> BatchRosterDeletionResult:
            everyone = tuple(self._people.list_all())
            base = self.preview(tuple(
                person.id for person in everyone if person.id is not None
            ))
            removed = 0
            for person_id in base.person_ids:
                assert person_id is not None  # 实体 __post_init__ 保证
                removed += self._people.remove(person_id)
            return BatchRosterDeletionResult(
                requested=base.person_count + base.missing_count,
                removed=removed,
                missing=base.missing_count,
                embedding_cascade=base.embedding_count,
                recognition_orphaned=base.recognition_count,
                batch_record_deleted=0,
                draft_rows_deleted=0,
            )

        if self._unit_of_work is not None:
            with self._unit_of_work:
                result = _run()
        else:
            result = _run()
        logger.info(
            "AUDIT clear-all-people actor=local-user removed={} "
            "embedding_cascade={} recognition_orphaned={}",
            result.removed, result.embedding_cascade, result.recognition_orphaned,
        )
        return result
