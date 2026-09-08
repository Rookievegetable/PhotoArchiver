"""Delete photos service — Phase E E-3（ADR-034 D1/D3）.

批量删除照片的库内登记：预览（级联计数）→ 确认 → 事务内删除。**磁盘文件
一律不动**（D3，服务层不变量——本服务根本不接收文件系统依赖）。幂等：请求
中不存在的 id 计入 ``missing``，不抛错。级联（识别结果 / 归档记录 CASCADE）
由既有外键承担，本服务不手写级联。
"""

from collections.abc import Sequence
from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.deletion import DeletePhotosCommand
from photo_archiver.application.dtos.deletion import PhotoDeletionPreview, PhotoDeletionResult
from photo_archiver.application.ports import UnitOfWork
from photo_archiver.application.use_cases.deletion import DeletePhotosUseCase
from photo_archiver.domain.repositories import (
    ArchiveRecordRepository,
    PhotoRepository,
    RecognitionRepository,
)


class DeletePhotosService(DeletePhotosUseCase):
    """Orchestrate previewed, transactional, disk-safe photo deletion."""

    def __init__(
        self,
        photo_repository: PhotoRepository,
        recognition_repository: RecognitionRepository,
        archive_record_repository: ArchiveRecordRepository,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize the service with its ports.

        Args:
            photo_repository: Registration source of truth; supplies the
                ``remove`` capability added by Phase E E-2.
            recognition_repository: Cascade counting for the preview.
            archive_record_repository: Cascade counting for the preview.
            unit_of_work: Optional transactional scope (optional-UoW convention
                of ``ImportPeopleService`` / ``ReviewRecognitionService``);
                ``None`` (in-memory unit-test path) persists bare.
        """
        self._photos = photo_repository
        self._recognition = recognition_repository
        self._archive_records = archive_record_repository
        self._unit_of_work = unit_of_work

    def preview(self, photo_ids: Sequence[UUID]) -> PhotoDeletionPreview:
        """Return the cascade-count preview; side-effect free."""
        requested = tuple(dict.fromkeys(photo_ids))
        missing = tuple(pid for pid in requested if self._photos.find_by_id(pid) is None)
        missing_set = set(missing)
        existing = [pid for pid in requested if pid not in missing_set]
        recognition_count = (
            len(self._recognition.list_by_photo_ids(existing)) if existing else 0
        )
        archive_count = len(self._archive_records.list_by_photo_ids(existing)) if existing else 0
        return PhotoDeletionPreview(
            photo_ids=tuple(existing),
            missing_ids=missing,
            recognition_count=recognition_count,
            archive_count=archive_count,
        )

    def execute(self, command: DeletePhotosCommand) -> PhotoDeletionResult:
        """Delete the confirmed registrations; audit-log the outcome."""
        preview = self.preview(command.photo_ids)
        if self._unit_of_work is not None:
            with self._unit_of_work:
                removed = self._photos.remove(preview.photo_ids)
        else:
            removed = self._photos.remove(preview.photo_ids)
        logger.info(
            "AUDIT delete-photos actor=local-user removed={} recognition_cascade={} "
            "archive_cascade={} missing={} photo_ids={}",
            removed,
            preview.recognition_count,
            preview.archive_count,
            preview.missing_count,
            list(preview.photo_ids),
        )
        return PhotoDeletionResult(
            requested=preview.photo_count + preview.missing_count,
            removed=removed,
            missing=preview.missing_count,
            recognition_cascade=preview.recognition_count,
            archive_cascade=preview.archive_count,
        )
