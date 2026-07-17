"""DTOs for the archive workflow (plan → execute → record).

落 Phase 2 Step 11 裁决 #3 拆分：ArchivePlan 由 ArchivePlanner 生成，
ArchiveExecutor 消费；CLI、UI、测试均复用此同一套 DTO。
"""

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from photo_archiver.domain.entities.archive import ArchiveStatus
from photo_archiver.domain.value_objects import ArchivePath


@dataclass(frozen=True, slots=True)
class ArchivePlanItem:
    """One photo's planned archive destination plus the metadata Executor needs.

    photo_id / source_path: The photo to archive and its current filesystem location.
    target_path: The planned ArchivePath value object (segments + resolve).
    person_id / person_name: Carried for logging and grouping; person_name
        is also embedded in target_path.person_name.
    """

    photo_id: UUID
    source_path: Path
    target_path: ArchivePath
    person_id: UUID
    person_name: str


@dataclass(frozen=True, slots=True)
class ArchivePlan:
    """A reusable, side-effect free archive plan covering one or more persons.

    CLI/UI/tests 调 ArchivePlanner.plan() 得此对象后，可以先展示预览
    （"Alice 下 12 张，Bob 下 5 张"）再决定是否调 ArchiveExecutor.execute()。
    """

    items: tuple[ArchivePlanItem, ...] = field(default_factory=tuple)
    skipped_count: int = 0  # photo already archived OR missing source OR no approved match

    @property
    def planned_count(self) -> int:
        """Return the number of items the executor should attempt."""
        return len(self.items)


@dataclass(frozen=True, slots=True)
class ArchiveOutcome:
    """One item's execution result, mirroring ArchiveStatus final states.

    photo_id correlates back to the ArchivePlanItem; status carries the
    final lifecycle (ARCHIVED / SKIPPED / RENAMED / OVERWRITTEN / DRY_RUN / FAILED).
    target_path is the actually-written path (differs from plan when renamed);
    error carries the failure reason for FAILED items.
    """

    photo_id: UUID
    status: ArchiveStatus
    target_path: ArchivePath
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    """Aggregate outcome of one archive run.

    planned_count: How many items the plan contained.
    outcomes: Per-item results in plan order (executor never reorders).
    """

    planned_count: int
    outcomes: tuple[ArchiveOutcome, ...] = field(default_factory=tuple)

    @property
    def archived_count(self) -> int:
        """Count of items actually archived (copy/move succeeded, not dry-run)."""
        return sum(
            1
            for o in self.outcomes
            if o.status in (ArchiveStatus.ARCHIVED, ArchiveStatus.RENAMED, ArchiveStatus.OVERWRITTEN)
        )

    @property
    def skipped_count(self) -> int:
        """Count of items skipped due to conflict_strategy=skip."""
        return sum(1 for o in self.outcomes if o.status is ArchiveStatus.SKIPPED)

    @property
    def dry_run_count(self) -> int:
        """Count of items that were dry-run logged only."""
        return sum(1 for o in self.outcomes if o.status is ArchiveStatus.DRY_RUN)

    @property
    def failed_count(self) -> int:
        """Count of items that failed with a filesystem error."""
        return sum(1 for o in self.outcomes if o.status is ArchiveStatus.FAILED)

    @property
    def errors(self) -> tuple[str, ...]:
        """Return the error messages of failed items, in plan order."""
        return tuple(o.error for o in self.outcomes if o.error is not None)

    @property
    def succeeded(self) -> bool:
        """Return whether the run completed with zero failures."""
        return self.failed_count == 0
