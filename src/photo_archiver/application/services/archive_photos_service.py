"""ArchivePhotosService — 落裁决 #3 编排：Planner → Executor + UnitOfWork。

责任：
    解析 command（archive_root 必填校验、conflict_strategy 默认值填充）；
    调 ArchivePlanner.plan() 得 ArchivePlan；
    包 UnitOfWork 调 ArchiveExecutor.execute()，原子提交 ArchiveRecord 批量；
    返回 ArchiveResult。

CLI、UI（Step 12 工作台）、tests 共用此编排——Planner 单独可复用预览，
Executor 单独可复用只执行不规划，本服务则是"完整闭环"入口。
"""

from pathlib import Path

from loguru import logger

from photo_archiver.application.commands import ArchivePhotosCommand
from photo_archiver.application.dtos import ArchiveResult
from photo_archiver.application.services.archive_executor import ArchiveExecutor
from photo_archiver.application.services.archive_planner import ArchivePlanner
from photo_archiver.application.use_cases import ArchivePhotosUseCase
from photo_archiver.infrastructure.config import (
    DEFAULT_ARCHIVE_CONFLICT_STRATEGY,
    VALID_ARCHIVE_CONFLICT_STRATEGIES,
)


class ArchivePhotosService(ArchivePhotosUseCase):
    """Orchestrate the archive workflow.

    Transaction boundary (review M-1 fix): the executor owns its own UnitOfWork
    so PLANNED + finalized records commit atomically. The service no longer wraps
    executor.execute() in a UoW to avoid nested-transaction crashes (SQLiteUnitOfWork
    raises RuntimeError on nesting). Planner is read-only at plan time so it
    does not need a transaction boundary.
    """

    def __init__(
        self,
        planner: ArchivePlanner,
        executor: ArchiveExecutor,
        default_conflict_strategy: str = DEFAULT_ARCHIVE_CONFLICT_STRATEGY,
    ) -> None:
        """Initialize the service with planner, executor, and default conflict strategy.

        Args:
            planner: Builds the ArchivePlan from approved recognitions.
            executor: Performs the filesystem copy + ArchiveRecord persistence.
                The executor SHOULD own its own UnitOfWork so the per-batch
                PLANNED → finalized transitions commit atomically.
            default_conflict_strategy: Used when command.conflict_strategy is None.
                Defaults to AppSettings.archive_conflict_strategy's default.
        """
        self._planner = planner
        self._executor = executor
        self._default_conflict_strategy = default_conflict_strategy

    def execute(self, command: ArchivePhotosCommand) -> ArchiveResult:
        """Plan and execute archiving for the command's persons.

        Args:
            command: Carries archive_root (required), person_ids, conflict_strategy,
                and dry_run flag.

        Returns:
            The aggregate ArchiveResult covering every planned item.
        """
        archive_root_str = self._require_archive_root(command.archive_root)
        conflict_strategy = self._resolve_conflict_strategy(command.conflict_strategy)

        plan = self._planner.plan(
            archive_root=archive_root_str,
            person_ids=command.person_ids,
        )
        if plan.planned_count == 0:
            logger.info(
                "ArchivePhotosService: plan empty (skipped={}); no execution needed",
                plan.skipped_count,
            )
            return ArchiveResult(planned_count=0)

        return self._executor.execute(
            plan,
            conflict_strategy=conflict_strategy,
            dry_run=command.dry_run,
        )

    @staticmethod
    def _require_archive_root(archive_root: Path) -> str:
        """Return the validated archive_root string, raising on empty / cwd-only.

        Empty archive_root is a configuration error, not a recoverable runtime
        condition — failing loud here keeps the executor from silently landing
        files under the current working directory. ``Path('.').resolve()`` would
        expand to the cwd and slip past a naive non-empty check, so we explicitly
        reject the dot form before any resolution.
        """
        raw = archive_root.expanduser()
        if str(raw).strip() in ("", "."):
            raise ValueError("Archive root must not be empty")
        resolved = raw.resolve(strict=False)
        if str(resolved).strip() in ("", "."):
            raise ValueError("Archive root must not be empty")
        return str(resolved)

    def _resolve_conflict_strategy(self, command_value: str | None) -> str:
        """Return the effective conflict strategy, falling back to the default.

        Validates against VALID_ARCHIVE_CONFLICT_STRATEGIES so CLI / UI typos
        surface here rather than inside the executor where the branch would
        silently fall through to "treat as overwrite" or similar.
        """
        effective = command_value if command_value is not None else self._default_conflict_strategy
        normalized = effective.strip().lower()
        if normalized not in VALID_ARCHIVE_CONFLICT_STRATEGIES:
            raise ValueError(
                f"Archive conflict strategy {effective!r} not in "
                f"{VALID_ARCHIVE_CONFLICT_STRATEGIES}"
            )
        return normalized
