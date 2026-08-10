"""Tests for ArchivePhotosService — 裁决 #3 编排：Planner → Executor.

用 fake planner / fake executor 隔离编排逻辑本身；planner 与 executor
各自的契约由 test_archive_planner.py / test_archive_executor.py 覆盖。
本测试只验：command 解析、conflict_strategy 默认值、空 plan 早返、dry_run 透传。

review M-1 fix: UoW 已下沉到 ArchiveExecutor 内部，Service 不再持 UoW，
故原 wraps_executor_in_unit_of_work 测试不再适用，删除。
"""

from pathlib import Path
from uuid import uuid4

import pytest

from photo_archiver.application.commands import ArchivePhotosCommand
from photo_archiver.application.dtos import ArchiveOutcome, ArchivePlan, ArchiveResult
from photo_archiver.application.services import ArchivePhotosService
from photo_archiver.domain import ArchiveStatus
from photo_archiver.infrastructure.config import DEFAULT_ARCHIVE_CONFLICT_STRATEGY


class _FakePlanner:
    """Planner stub returning a pre-canned plan, capturing call args.

    Methods named ``plan``/``execute`` clash with dataclass fields of the same
    name, so this is a plain class with explicit __init__ rather than a dataclass.
    """

    def __init__(self, plan: ArchivePlan) -> None:
        self._plan = plan
        self.calls: list = []

    def plan(self, archive_root, person_ids, photo_ids=()):
        self.calls.append((archive_root, person_ids, photo_ids))
        return self._plan


class _FakeExecutor:
    """Executor stub capturing call args, returning a pre-canned result."""

    def __init__(self, result: ArchiveResult) -> None:
        self._result = result
        self.calls: list = []

    def execute(self, plan, conflict_strategy, dry_run=False):
        self.calls.append((plan, conflict_strategy, dry_run))
        return self._result


def _empty_plan() -> ArchivePlan:
    return ArchivePlan()


def _nonempty_plan() -> ArchivePlan:
    from photo_archiver.application.dtos import ArchivePlanItem
    from photo_archiver.domain.value_objects import ArchivePath
    return ArchivePlan(items=(
        ArchivePlanItem(
            photo_id=uuid4(),
            source_path=Path("/src/x.jpg"),
            target_path=ArchivePath(
                archive_root="/archive",
                person_name="Alice",
                event_or_date="2024-05-01",
                original_name="x.jpg",
            ),
            person_id=uuid4(),
            person_name="Alice",
        ),
    ))


def _archived_result() -> ArchiveResult:
    from photo_archiver.domain.value_objects import ArchivePath
    return ArchiveResult(
        planned_count=1,
        outcomes=(ArchiveOutcome(
            photo_id=uuid4(),
            status=ArchiveStatus.ARCHIVED,
            target_path=ArchivePath(
                archive_root="/archive", person_name="Alice",
                event_or_date="2024-05-01", original_name="x.jpg",
            ),
        ),),
    )


def test_service_resolves_archive_root_to_absolute_string() -> None:
    """archive_root Path is expanded + resolved to a string for planner consumption."""
    planner = _FakePlanner(_empty_plan())
    executor = _FakeExecutor(ArchiveResult(planned_count=0))
    service = ArchivePhotosService(planner=planner, executor=executor)  # type: ignore[arg-type]
    service.execute(ArchivePhotosCommand(archive_root=Path("archive")))
    assert planner.calls[0][0] == str(Path("archive").expanduser().resolve(strict=False))


def test_service_rejects_empty_archive_root() -> None:
    """Empty archive_root raises ValueError rather than silently landing under cwd."""
    planner = _FakePlanner(_empty_plan())
    executor = _FakeExecutor(ArchiveResult(planned_count=0))
    service = ArchivePhotosService(planner=planner, executor=executor)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        service.execute(ArchivePhotosCommand(archive_root=Path(".")))


def test_service_falls_back_to_default_conflict_strategy_when_command_none() -> None:
    """command.conflict_strategy=None → service default_conflict_strategy used."""
    planner = _FakePlanner(_nonempty_plan())
    executor = _FakeExecutor(_archived_result())
    service = ArchivePhotosService(
        planner=planner,  # type: ignore[arg-type]
        executor=executor,  # type: ignore[arg-type]
        default_conflict_strategy=DEFAULT_ARCHIVE_CONFLICT_STRATEGY,
    )
    service.execute(ArchivePhotosCommand(archive_root=Path("/archive")))
    assert executor.calls[0][1] == DEFAULT_ARCHIVE_CONFLICT_STRATEGY


def test_service_uses_command_conflict_strategy_when_provided() -> None:
    """command.conflict_strategy override wins over service default."""
    planner = _FakePlanner(_nonempty_plan())
    executor = _FakeExecutor(_archived_result())
    service = ArchivePhotosService(
        planner=planner,  # type: ignore[arg-type]
        executor=executor,  # type: ignore[arg-type]
        default_conflict_strategy="skip",
    )
    service.execute(ArchivePhotosCommand(
        archive_root=Path("/archive"), conflict_strategy="overwrite",
    ))
    assert executor.calls[0][1] == "overwrite"


def test_service_rejects_invalid_conflict_strategy() -> None:
    """Typos surface as ValueError rather than silently degrading in executor."""
    planner = _FakePlanner(_nonempty_plan())
    executor = _FakeExecutor(_archived_result())
    service = ArchivePhotosService(planner=planner, executor=executor)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        service.execute(ArchivePhotosCommand(
            archive_root=Path("/archive"), conflict_strategy="merge",
        ))


def test_service_skips_executor_when_plan_empty() -> None:
    """Empty plan short-circuits — executor not called."""
    planner = _FakePlanner(_empty_plan())
    executor = _FakeExecutor(_archived_result())
    service = ArchivePhotosService(
        planner=planner,  # type: ignore[arg-type]
        executor=executor,  # type: ignore[arg-type]
    )
    result = service.execute(ArchivePhotosCommand(archive_root=Path("/archive")))
    assert result.planned_count == 0
    assert executor.calls == []


def test_service_passes_dry_run_flag_to_executor() -> None:
    """dry_run flag flows from command → service → executor unmodified."""
    planner = _FakePlanner(_nonempty_plan())
    executor = _FakeExecutor(_archived_result())
    service = ArchivePhotosService(planner=planner, executor=executor)  # type: ignore[arg-type]
    service.execute(ArchivePhotosCommand(
        archive_root=Path("/archive"), dry_run=True,
    ))
    assert executor.calls[0][2] is True
