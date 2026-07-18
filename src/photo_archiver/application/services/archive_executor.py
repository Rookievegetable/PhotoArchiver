"""ArchiveExecutor — 落裁决 #3 第二段：消费 ArchivePlan 真实落盘 + 写 ArchiveRecord。

责任范围：
    按 conflict_strategy（skip/overwrite/rename）真 copy 文件到 target；
    dry_run 路径只 log 不碰文件系统；
    每项写 ArchiveRecord 到 archive_record_repository；
    包在 UnitOfWork 内（由 ArchivePhotosService 传入，不在 Executor 内嵌）。

不负责：
    生成 plan（归 ArchivePlanner）；
    选择 person 范围（归 ArchivePhotosService）；
    事务边界（归 ArchivePhotosService 调 UnitOfWork 包整批）。
"""

from pathlib import Path

from loguru import logger

from photo_archiver.application.dtos import ArchiveOutcome, ArchivePlan, ArchivePlanItem, ArchiveResult
from photo_archiver.application.ports import UnitOfWork
from photo_archiver.domain import ArchiveRecord, ArchiveRecordRepository
from photo_archiver.domain.entities.archive import ArchiveStatus
from photo_archiver.domain.value_objects import ArchivePath

# rename 策略下目标已存在时的后缀；裁决 #3 落地：保留原名 + .dup-N 段。
# 用 dup 而非 archived，避免与 ArchiveStatus.ARCHIVED 字面混淆（review m-5）。
_RENAME_CONFLICT_SUFFIX = "dup"


class ArchiveExecutor:
    """Execute an ArchivePlan against the filesystem, persisting ArchiveRecord per item.

    The executor is the only component in the archive workflow that touches the
    filesystem and the only one that writes ArchiveRecord aggregates. Keeping
    these two responsibilities together means the persisted record always
    reflects what actually happened on disk, even under partial failures.

    Transaction boundary (review M-1 fix): the executor accepts an optional
    UnitOfWork and wraps the entire batch so the per-item "PLANNED → finalized"
    ArchiveRecord transitions commit atomically. Without a UoW the two add()
    calls per item commit independently, leaving orphan PLANNED rows on crash.
    Callers reusing the executor without a UoW MUST wrap it themselves.
    """

    def __init__(
        self,
        archive_record_repository: ArchiveRecordRepository,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize the executor with its persistence target.

        Args:
            archive_record_repository: Where per-item ArchiveRecord aggregates land.
            unit_of_work: Optional transactional scope. When provided the executor
                wraps the whole batch so PLANNED + finalized records commit atomically.
                When None the executor runs without a transaction boundary — callers
                reuse it WITHOUT a UoW MUST wrap the execute() call in their own UoW
                to avoid orphan PLANNED rows on mid-batch crash.
        """
        self._archive_record_repository = archive_record_repository
        self._unit_of_work = unit_of_work

    def execute(
        self,
        plan: ArchivePlan,
        conflict_strategy: str,
        dry_run: bool = False,
    ) -> ArchiveResult:
        """Execute the plan item-by-item, returning one ArchiveOutcome per item.

        Args:
            plan: The ArchivePlanner-produced plan (immutable side-effect free DTO).
            conflict_strategy: skip | overwrite | rename — controls target-exists behavior.
            dry_run: When True, log intended operations without touching the filesystem.
                Records still persist as DRY_RUN so callers can inspect the plan outcome
                AND so re-runs can detect "this photo was dry-run previewed" — the record
                is the executor's only durable signal of having previewed the item.
        """
        if self._unit_of_work is not None:
            with self._unit_of_work:
                return self._execute_batch(plan, conflict_strategy, dry_run)
        return self._execute_batch(plan, conflict_strategy, dry_run)

    def _execute_batch(
        self,
        plan: ArchivePlan,
        conflict_strategy: str,
        dry_run: bool,
    ) -> ArchiveResult:
        """Run the per-item loop without UoW wrapping — caller's responsibility."""
        outcomes: list[ArchiveOutcome] = []
        for item in plan.items:
            record = self._make_planned_record(item)
            self._archive_record_repository.add(record)

            if dry_run:
                outcome = self._execute_dry_run(item, record)
            else:
                outcome = self._execute_real(item, conflict_strategy, record)

            self._archive_record_repository.add(record)
            outcomes.append(outcome)

        result = ArchiveResult(planned_count=plan.planned_count, outcomes=tuple(outcomes))
        logger.info(
            "ArchiveExecutor: planned={} archived={} skipped={} renamed={} "
            "overwritten={} dry_run={} failed={}",
            result.planned_count,
            result.archived_count,
            result.skipped_count,
            sum(1 for o in outcomes if o.status is ArchiveStatus.RENAMED),
            sum(1 for o in outcomes if o.status is ArchiveStatus.OVERWRITTEN),
            result.dry_run_count,
            result.failed_count,
        )
        return result

    def _execute_dry_run(
        self,
        item: ArchivePlanItem,
        record: ArchiveRecord,
    ) -> ArchiveOutcome:
        """Log the intended operation and mark the record DRY_RUN.

        Source existence is still checked so dry-run output reflects what would
        happen on a real run; missing source surfaces as FAILED rather than DRY_RUN
        so the user can see "this plan has a broken photo" before committing.
        """
        source = item.source_path
        target = Path(item.target_path.resolve())
        if not source.exists():
            error = f"source missing: {source}"
            logger.warning("Archive dry-run FAIL {}: {}", item.photo_id, error)
            record.mark_failed(error)
            return ArchiveOutcome(
                photo_id=item.photo_id,
                status=ArchiveStatus.FAILED,
                target_path=item.target_path,
                error=error,
            )
        logger.info(
            "Archive dry-run OK {}: would copy {} -> {}",
            item.photo_id,
            source,
            target,
        )
        record.mark_dry_run()
        return ArchiveOutcome(
            photo_id=item.photo_id,
            status=ArchiveStatus.DRY_RUN,
            target_path=item.target_path,
        )

    def _execute_real(
        self,
        item: ArchivePlanItem,
        conflict_strategy: str,
        record: ArchiveRecord,
    ) -> ArchiveOutcome:
        """Perform the real copy, honoring conflict_strategy."""
        source = item.source_path
        target = Path(item.target_path.resolve())

        # review M-3 fix: assert target stays under archive_root before any
        # filesystem mutation. ArchivePath validates segments at construction
        # but this is the filesystem boundary — fail loud here if a malformed
        # target would escape the configured root.
        archive_root_path = Path(item.target_path.archive_root).resolve(strict=False)
        try:
            target.relative_to(archive_root_path)
        except ValueError:
            error = f"target escapes archive_root: {target} not under {archive_root_path}"
            logger.warning("Archive FAIL {} {}", item.photo_id, error)
            record.mark_failed(error)
            return ArchiveOutcome(
                photo_id=item.photo_id,
                status=ArchiveStatus.FAILED,
                target_path=item.target_path,
                error=error,
            )

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if conflict_strategy == "skip":
                    logger.info("Archive SKIP {} (target exists): {}", item.photo_id, target)
                    record.mark_skipped()
                    return ArchiveOutcome(item.photo_id, ArchiveStatus.SKIPPED, item.target_path)
                if conflict_strategy == "overwrite":
                    self._copy_file(source, target)
                    logger.info("Archive OVERWRITE {}: {} -> {}", item.photo_id, source, target)
                    record.mark_overwritten()
                    return ArchiveOutcome(item.photo_id, ArchiveStatus.OVERWRITTEN, item.target_path)
                if conflict_strategy == "rename":
                    renamed_target = self._compute_renamed_target(target)
                    self._copy_file(source, renamed_target)
                    logger.info(
                        "Archive RENAME {}: {} -> {} (target existed)",
                        item.photo_id,
                        source,
                        renamed_target,
                    )
                    record.mark_renamed()
                    renamed_path = self._path_segments_from(renamed_target, item.target_path)
                    return ArchiveOutcome(item.photo_id, ArchiveStatus.RENAMED, renamed_path)

            self._copy_file(source, target)
            logger.info("Archive COPY {}: {} -> {}", item.photo_id, source, target)
            record.mark_archived()
            return ArchiveOutcome(item.photo_id, ArchiveStatus.ARCHIVED, item.target_path)

        except OSError as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("Archive FAIL {} {}: {}", item.photo_id, target, error)
            record.mark_failed(error)
            return ArchiveOutcome(
                photo_id=item.photo_id,
                status=ArchiveStatus.FAILED,
                target_path=item.target_path,
                error=error,
            )

    @staticmethod
    def _copy_file(source: Path, target: Path) -> None:
        """Copy source to target preserving metadata (mtime, mode bits).

        review M-4 fix: use shutil.copy2 (not copyfile) so target mtime tracks
        the source — re-scanning archive_root later can fall back to mtime for
        captured_at without seeing every archived file stamped "now". EXIF lives
        in the byte stream so it survives either helper; copy2 also preserves
        access mode bits which copyfile drops. Caller still owns parent mkdir.
        """
        import shutil

        shutil.copy2(source, target)

    @staticmethod
    def _compute_renamed_target(target: Path) -> Path:
        """Find the next non-existing sibling of target under the rename strategy.

        Pattern: insert ``.archived-1`` ``.archived-2`` ... before the first
        extension. Stops at the first non-existing sibling so the rename
        counter is deterministic under concurrent runs of the same plan.
        """
        stem = target.stem
        suffix = target.suffix
        parent = target.parent
        counter = 1
        while True:
            candidate = parent / f"{stem}.{_RENAME_CONFLICT_SUFFIX}-{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    @staticmethod
    def _path_segments_from(resolved: Path, original: ArchivePath) -> ArchivePath:
        """Rebuild an ArchivePath from a renamed resolved path.

        After rename, only the leaf ``original_name`` changes; root / person /
        event_or_date stay as planned. Keeping the value object's segments
        honest with the on-disk leaf name matters for downstream reporting.
        """
        return ArchivePath(
            archive_root=original.archive_root,
            person_name=original.person_name,
            event_or_date=original.event_or_date,
            original_name=resolved.name,
        )

    def _make_planned_record(self, item: ArchivePlanItem) -> ArchiveRecord:
        """Create a PLANNED ArchiveRecord capturing the plan's intent for this photo.

        PLANNED records persist even if the executor later fails on this item —
        that historical record lets re-runs detect "this was attempted before"
        without inspecting the filesystem.
        """
        target = item.target_path
        return ArchiveRecord(
            photo_id=item.photo_id,
            target_archive_root=target.archive_root,
            target_person_name=target.person_name,
            target_event_or_date=target.event_or_date,
            target_original_name=target.original_name,
            status=ArchiveStatus.PLANNED,
        )
