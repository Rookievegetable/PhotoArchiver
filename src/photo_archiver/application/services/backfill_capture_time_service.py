"""Backfill capture time service — Phase F F-1（ADR-035）.

Issue-019 修复后的一次性纠错：修复前入库的历史照片 ``captured_at`` 可能是
旧 reader 的 mtime 冒名。本服务全量重读（EXIF 是事实源，重读幂等），登记值
与重读值不一致者经 ``PhotoRepository.update_capture_time`` 对齐；**dry-run
默认只读不写**（owner 裁决 R3）。与 ``BackfillContentHashService`` 同模式：
一次性低频操作、list_all 全量内存过滤、不扩查询 Protocol、逐文件异常降级
计数不中断整批。
"""

from dataclasses import dataclass

from loguru import logger

from photo_archiver.application.commands.backfill_capture_time import (
    BackfillCaptureTimeCommand,
)
from photo_archiver.application.ports import PhotoMetadataReader
from photo_archiver.domain.repositories import PhotoRepository


@dataclass(frozen=True, slots=True)
class BackfillCaptureTimeResult:
    """Aggregate outcome of a one-time captured_at correction run.

    scanned: Total photos considered (all registrations).
    updated: Registrations actually rewritten (always 0 under dry-run).
    would_update: Registrations whose stored value differs from the fresh
        read — the dry-run preview figure and the audit baseline.
    unchanged: Registrations whose stored value already matches the fresh
        read (includes no-EXIF photos whose mtime fallback did not move).
    failed: Re-read exceptions (logged individually; never abort the batch).
    skipped_missing: Registrations whose disk file is gone (the prune-missing
        CLI owns those — this service never deletes).
    """

    scanned: int
    updated: int
    would_update: int
    unchanged: int
    failed: int
    skipped_missing: int

    @property
    def succeeded(self) -> bool:
        """Return whether the run completed with zero failures."""
        return self.failed == 0


class BackfillCaptureTimeService:
    """One-time captured_at correction over all registered photos.

    Idempotent: re-running on an already-corrected database finds zero
    differences and returns ``updated=0``. Safe to invoke repeatedly from
    the CLI; dry-run is the default so the first invocation is a preview.
    """

    def __init__(
        self,
        photo_repository: PhotoRepository,
        metadata_reader: PhotoMetadataReader,
    ) -> None:
        """Initialize the service with its ports.

        Args:
            photo_repository: Registration source of truth and the
                ``update_capture_time`` write channel (ADR-035).
            metadata_reader: Re-reads metadata including ``captured_at``
                (the ISSUE-019 fixed sub-IFD chain).
        """
        self._photo_repository = photo_repository
        self._metadata_reader = metadata_reader

    def execute(
        self, command: BackfillCaptureTimeCommand | None = None
    ) -> BackfillCaptureTimeResult:
        """Run the correction (dry-run by default); audit-log the outcome."""
        resolved = command or BackfillCaptureTimeCommand()
        photos = self._photo_repository.list_all()
        updated = 0
        would_update = 0
        unchanged = 0
        failed = 0
        skipped_missing = 0
        for photo in photos:
            source_path = photo.path.raw_path
            if not source_path.exists():
                logger.warning(
                    "Backfill capture-time: photo {} file missing at {}, skipping",
                    photo.id,
                    source_path,
                )
                skipped_missing += 1
                continue
            try:
                fresh = self._metadata_reader.read(source_path)
            except (OSError, ValueError, RuntimeError) as exc:
                logger.warning("Backfill capture-time: failed to re-read {}: {}", source_path, exc)
                failed += 1
                continue
            fresh_capture = fresh.captured_at
            if fresh_capture == photo.captured_at:
                unchanged += 1
                continue
            would_update += 1
            if resolved.dry_run:
                continue
            if self._photo_repository.update_capture_time(
                photo.id, fresh_capture  # type: ignore[arg-type]  # UUID | None guarantee
            ) == 1:
                updated += 1
            else:
                # 并发删除信号（返回 0 行）——如实计为失败而不是静默吞。
                logger.warning(
                    "Backfill capture-time: update hit 0 rows for {} (removed concurrently?)",
                    photo.id,
                )
                failed += 1
        logger.info(
            "BackfillCaptureTimeService: dry_run={} scanned={} updated={} would_update={} "
            "unchanged={} failed={} skipped_missing={}",
            resolved.dry_run,
            len(photos),
            updated,
            would_update,
            unchanged,
            failed,
            skipped_missing,
        )
        return BackfillCaptureTimeResult(
            scanned=len(photos),
            updated=updated,
            would_update=would_update,
            unchanged=unchanged,
            failed=failed,
            skipped_missing=skipped_missing,
        )
