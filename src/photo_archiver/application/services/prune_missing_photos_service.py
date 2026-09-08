"""Prune missing photos service — Phase E E-3（ADR-034 D5）.

清理"登记在库但磁盘文件已消失"的照片登记。D5 语义：**扫描只增不删**——
失联登记绝不自动删除（防移动盘未挂载误判），仅经本用例显式清理：
``preview()`` 列出失联项（含解析后的期望路径供用户核实），``execute()`` 只删
调用方确认的 id，且**执行时重新校验仍处失联集合**（文件在预览后恢复者被
拒绝并计数，绝不删除在册有效照片）。

路径解析：ABSOLUTE 直接用登记路径；PHOTO_ROOT 相对路径需注入 photo_root
（组合根从 settings 传入）；无法解析者（PHOTO_ROOT 无根 / PROJECT_ROOT）
保守计为 ``unresolvable``，**永不视为失联**。
"""

from pathlib import Path

from loguru import logger

from photo_archiver.application.commands.deletion import PruneMissingCommand
from photo_archiver.application.dtos.deletion import (
    MissingPhotoItem,
    PruneMissingPreview,
    PruneMissingResult,
)
from photo_archiver.application.ports import UnitOfWork
from photo_archiver.application.use_cases.deletion import PruneMissingPhotosUseCase
from photo_archiver.domain.entities import Photo
from photo_archiver.domain.repositories import PhotoRepository
from photo_archiver.domain.value_objects import PhotoPathBase


class PruneMissingPhotosService(PruneMissingPhotosUseCase):
    """Orchestrate guarded pruning of missing-on-disk registrations."""

    def __init__(
        self,
        photo_repository: PhotoRepository,
        photo_root: Path | None = None,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize the service with its ports.

        Args:
            photo_repository: Registration source of truth (E-2 ``remove``).
            photo_root: Resolution root for ``PHOTO_ROOT``-based relative
                paths; ``None`` leaves those photos unresolvable (conservatively
                kept). Absolute-base photos ignore it.
            unit_of_work: Optional transactional scope; ``None`` persists bare.
        """
        self._photos = photo_repository
        self._photo_root = photo_root
        self._unit_of_work = unit_of_work

    def _resolve_disk_path(self, photo: Photo) -> Path | None:
        """Return the absolute disk path for a registration, or ``None``."""
        if photo.path.base is PhotoPathBase.ABSOLUTE:
            return photo.path.raw_path
        if photo.path.base is PhotoPathBase.PHOTO_ROOT and self._photo_root is not None:
            return self._photo_root / photo.path.raw_path
        return None

    def preview(self) -> PruneMissingPreview:
        """List missing-on-disk registrations; side-effect free."""
        photos = self._photos.list_all()
        items: list[MissingPhotoItem] = []
        unresolvable = 0
        for photo in photos:
            resolved = self._resolve_disk_path(photo)
            if resolved is None:
                unresolvable += 1
                continue
            if not resolved.exists():
                items.append(
                    MissingPhotoItem(
                        photo_id=photo.id,  # type: ignore[arg-type]  # guaranteed by Photo.__post_init__
                        disk_path=resolved,
                    )
                )
        logger.info(
            "PruneMissingPhotosService preview: scanned={} missing={} unresolvable={}",
            len(photos),
            len(items),
            unresolvable,
        )
        return PruneMissingPreview(
            scanned=len(photos),
            items=tuple(items),
            unresolvable=unresolvable,
        )

    def execute(self, command: PruneMissingCommand) -> PruneMissingResult:
        """Prune the confirmed ids that are still missing; audit-log."""
        preview = self.preview()
        still_missing = {item.photo_id for item in preview.items}
        requested = list(dict.fromkeys(command.photo_ids))
        confirmed = [pid for pid in requested if pid in still_missing]
        rejected = len(requested) - len(confirmed)

        if self._unit_of_work is not None:
            with self._unit_of_work:
                pruned = self._photos.remove(confirmed)
        else:
            pruned = self._photos.remove(confirmed)
        logger.info(
            "AUDIT prune-missing actor=local-user pruned={} rejected={} "
            "missing={} unresolvable={} photo_ids={}",
            pruned,
            rejected,
            preview.missing_count,
            preview.unresolvable,
            confirmed,
        )
        return PruneMissingResult(
            scanned=preview.scanned,
            missing=preview.missing_count,
            requested=len(requested),
            pruned=pruned,
            rejected=rejected,
            unresolvable=preview.unresolvable,
        )
