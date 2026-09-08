"""Dispose duplicates service — Phase E E-3（ADR-034 D6/D1/D3）.

重复照片处置编排：在 ``PhotoRepository.list_duplicate_groups`` 报告基础上
产出处置提案——每组保留**最早注册一张**（``created_at`` 最小、同刻以 id
决胜，ADR-034 D6），其余删登记（走 D1 照片删除，原文件不动）。保留判定由
本服务显式按 ``(created_at, id)`` 排序做出，不依赖仓储返回序。

``execute()`` 端**重新校验**确认 id 确属某组建议删除集——保留者、唯一照片
或非重复 id 一律拒绝并计数（防 UI 状态过期误删在册有效照片）。
"""

from datetime import datetime
from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.deletion import DisposeDuplicatesCommand
from photo_archiver.application.dtos.deletion import (
    DuplicateDisposalGroup,
    DuplicateDisposalPreview,
    DuplicateDisposalResult,
)
from photo_archiver.application.ports import UnitOfWork
from photo_archiver.application.use_cases.deletion import DisposeDuplicatesUseCase
from photo_archiver.domain.entities import Photo
from photo_archiver.domain.repositories import (
    ArchiveRecordRepository,
    PhotoRepository,
    RecognitionRepository,
)


class DisposeDuplicatesService(DisposeDuplicatesUseCase):
    """Orchestrate guarded, transactional duplicate registration disposal."""

    def __init__(
        self,
        photo_repository: PhotoRepository,
        recognition_repository: RecognitionRepository,
        archive_record_repository: ArchiveRecordRepository,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize the service with its ports.

        Args:
            photo_repository: Duplicate group source (B1 push-down) and the
                E-2 ``remove`` capability.
            recognition_repository: Cascade counting per removal proposal.
            archive_record_repository: Cascade counting per removal proposal.
            unit_of_work: Optional transactional scope; ``None`` persists bare.
        """
        self._photos = photo_repository
        self._recognition = recognition_repository
        self._archive_records = archive_record_repository
        self._unit_of_work = unit_of_work

    @staticmethod
    def _ordered_members(group: list[Photo]) -> list[Photo]:
        """Order a group by registration time with id tiebreak (D6)."""
        return sorted(
            group,
            key=lambda photo: (
                photo.created_at if photo.created_at is not None else datetime.min,
                photo.id,  # type: ignore[arg-type]  # guaranteed by Photo.__post_init__
            ),
        )

    def preview(self) -> DuplicateDisposalPreview:
        """Return per-group keep/remove proposals with cascade counts."""
        raw_groups = self._photos.list_duplicate_groups()
        proposals: list[tuple[str, Photo, list[Photo]]] = []
        for group in raw_groups:
            ordered = self._ordered_members(group)
            keep = ordered[0]
            if keep.metadata is None or keep.metadata.content_hash is None:
                raise RuntimeError(
                    "PhotoRepository.list_duplicate_groups violated contract: "
                    f"returned a group whose first photo has NULL content_hash "
                    f"(photo_id={keep.id})"
                )
            proposals.append((keep.metadata.content_hash, keep, ordered[1:]))

        remove_ids = [
            photo.id for _, _, removes in proposals for photo in removes if photo.id is not None
        ]
        recognition_counts: dict[UUID, int] = {}
        archive_counts: dict[UUID, int] = {}
        if remove_ids:
            for recognition_row in self._recognition.list_by_photo_ids(remove_ids):
                recognition_counts[recognition_row.photo_id] = (
                    recognition_counts.get(recognition_row.photo_id, 0) + 1
                )
            for archive_row in self._archive_records.list_by_photo_ids(remove_ids):
                archive_counts[archive_row.photo_id] = (
                    archive_counts.get(archive_row.photo_id, 0) + 1
                )

        group_dtos: list[DuplicateDisposalGroup] = []
        for content_hash, keep, removes in proposals:
            remove_uuids = [photo.id for photo in removes if photo.id is not None]
            group_dtos.append(
                DuplicateDisposalGroup(
                    content_hash=content_hash,
                    keep_photo_id=keep.id,  # type: ignore[arg-type]  # guaranteed by Photo.__post_init__
                    remove_photo_ids=tuple(remove_uuids),
                    recognition_count=sum(
                        recognition_counts.get(uid, 0) for uid in remove_uuids
                    ),
                    archive_count=sum(archive_counts.get(uid, 0) for uid in remove_uuids),
                )
            )
        preview = DuplicateDisposalPreview(groups=tuple(group_dtos))
        logger.info(
            "DisposeDuplicatesService preview: groups={} removable={}",
            preview.group_count,
            preview.photo_count,
        )
        return preview


    def execute(self, command: DisposeDuplicatesCommand) -> DuplicateDisposalResult:
        """Remove confirmed removable duplicate ids; audit-log the outcome."""
        preview = self.preview()
        removable = {pid for group in preview.groups for pid in group.remove_photo_ids}
        requested = list(dict.fromkeys(command.photo_ids))
        confirmed = [pid for pid in requested if pid in removable]
        rejected = len(requested) - len(confirmed)

        if self._unit_of_work is not None:
            with self._unit_of_work:
                removed = self._photos.remove(confirmed)
        else:
            removed = self._photos.remove(confirmed)
        affected = {
            group.content_hash
            for group in preview.groups
            if any(pid in group.remove_photo_ids for pid in confirmed)
        }
        logger.info(
            "AUDIT dispose-duplicates actor=local-user removed={} rejected={} "
            "groups_affected={} photo_ids={}",
            removed,
            rejected,
            len(affected),
            confirmed,
        )
        return DuplicateDisposalResult(
            requested=len(requested),
            removed=removed,
            rejected=rejected,
            groups_affected=len(affected),
        )
