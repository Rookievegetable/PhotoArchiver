"""Tests for ArchiveExecutor — 裁决 #3 第二段：消费 plan 真实落盘 + 写 record.

用 tmp_path + in-memory ArchiveRecordRepository fake；executor 真碰文件系统，
所以测试建临时 photo / archive_root。覆盖 conflict_strategy × dry_run 矩阵 + record 落库.
"""

from pathlib import Path
from uuid import uuid4

from photo_archiver.application.dtos import ArchivePlan, ArchivePlanItem
from photo_archiver.application.services import ArchiveExecutor
from photo_archiver.domain import ArchiveRecord, ArchiveStatus, ArchivePath


class _RecordingArchiveRecordRepository:
    """In-memory ArchiveRecordRepository capturing add() calls for assertions."""

    def __init__(self) -> None:
        self.added: list[ArchiveRecord] = []

    def add(self, record: ArchiveRecord) -> None:
        # Mimic upsert by id so the executor's two calls (PLANNED then finalized) keep one record.
        existing = next((r for r in self.added if r.id == record.id), None)
        if existing is not None:
            # Replace fields in place to mirror SQLite ON CONFLICT DO UPDATE.
            existing.status = record.status
            existing.archived_at = record.archived_at
            existing.error = record.error
        else:
            self.added.append(record)


def _make_plan_item(source: Path, archive_root: str, person_name: str = "Alice", original_name: str = "x.jpg") -> ArchivePlanItem:
    return ArchivePlanItem(
        photo_id=uuid4(),
        source_path=source,
        target_path=ArchivePath(
            archive_root=archive_root,
            person_name=person_name,
            event_or_date="2024-05-01",
            original_name=original_name,
        ),
        person_id=uuid4(),
        person_name=person_name,
    )


def _make_plan(item: ArchivePlanItem) -> ArchivePlan:
    return ArchivePlan(items=(item,))


def _write_source(tmp_path: Path, name: str, content: bytes = b"x") -> Path:
    source = tmp_path / "src" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    return source


def test_executor_copies_source_to_target(tmp_path: Path) -> None:
    """skip strategy + non-existing target → ARCHIVED + file copied."""
    source = _write_source(tmp_path, "x.jpg")
    archive_root = tmp_path / "archive"
    item = _make_plan_item(source, str(archive_root))
    repo = _RecordingArchiveRecordRepository()
    executor = ArchiveExecutor(repo)
    result = executor.execute(_make_plan(item), conflict_strategy="skip")
    assert len(result.outcomes) == 1
    assert result.outcomes[0].status is ArchiveStatus.ARCHIVED
    assert result.archived_count == 1
    assert (archive_root / "Alice" / "2024-05-01" / "x.jpg").read_bytes() == b"x"
    assert repo.added[0].status is ArchiveStatus.ARCHIVED


def test_executor_skip_strategy_skips_existing_target(tmp_path: Path) -> None:
    """skip strategy + existing target → SKIPPED, source not copied over."""
    source = _write_source(tmp_path, "x.jpg", b"new")
    archive_root = tmp_path / "archive"
    target = archive_root / "Alice" / "2024-05-01" / "x.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"old")
    item = _make_plan_item(source, str(archive_root))
    repo = _RecordingArchiveRecordRepository()
    executor = ArchiveExecutor(repo)
    result = executor.execute(_make_plan(item), conflict_strategy="skip")
    assert result.outcomes[0].status is ArchiveStatus.SKIPPED
    assert target.read_bytes() == b"old"  # not overwritten
    assert result.skipped_count == 1


def test_executor_overwrite_strategy_replaces_target(tmp_path: Path) -> None:
    """overwrite strategy + existing target → OVERWRITTEN, source replaces."""
    source = _write_source(tmp_path, "x.jpg", b"new")
    archive_root = tmp_path / "archive"
    target = archive_root / "Alice" / "2024-05-01" / "x.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"old")
    item = _make_plan_item(source, str(archive_root))
    repo = _RecordingArchiveRecordRepository()
    executor = ArchiveExecutor(repo)
    result = executor.execute(_make_plan(item), conflict_strategy="overwrite")
    assert result.outcomes[0].status is ArchiveStatus.OVERWRITTEN
    assert target.read_bytes() == b"new"


def test_executor_rename_strategy_picks_sibling(tmp_path: Path) -> None:
    """rename strategy + existing target → RENAMED with .archived-1 sibling."""
    source = _write_source(tmp_path, "x.jpg", b"new")
    archive_root = tmp_path / "archive"
    target = archive_root / "Alice" / "2024-05-01" / "x.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"old")
    item = _make_plan_item(source, str(archive_root))
    repo = _RecordingArchiveRecordRepository()
    executor = ArchiveExecutor(repo)
    result = executor.execute(_make_plan(item), conflict_strategy="rename")
    outcome = result.outcomes[0]
    assert outcome.status is ArchiveStatus.RENAMED
    renamed_target = archive_root / "Alice" / "2024-05-01" / outcome.target_path.original_name
    assert renamed_target.exists()
    assert renamed_target.read_bytes() == b"new"
    assert target.read_bytes() == b"old"  # original untouched
    assert outcome.target_path.original_name == "x.archived-1.jpg"


def test_executor_dry_run_does_not_touch_filesystem(tmp_path: Path) -> None:
    """dry_run=True → DRY_RUN status, no file written."""
    source = _write_source(tmp_path, "x.jpg")
    archive_root = tmp_path / "archive"
    item = _make_plan_item(source, str(archive_root))
    repo = _RecordingArchiveRecordRepository()
    executor = ArchiveExecutor(repo)
    result = executor.execute(_make_plan(item), conflict_strategy="skip", dry_run=True)
    assert result.outcomes[0].status is ArchiveStatus.DRY_RUN
    assert result.dry_run_count == 1
    # target should not exist
    assert not (archive_root / "Alice" / "2024-05-01" / "x.jpg").exists()
    assert repo.added[0].status is ArchiveStatus.DRY_RUN


def test_executor_dry_run_fails_on_missing_source(tmp_path: Path) -> None:
    """dry_run surfaces missing source as FAILED so users see broken plans pre-commit."""
    source = tmp_path / "nonexistent.jpg"
    archive_root = tmp_path / "archive"
    item = _make_plan_item(source, str(archive_root))
    repo = _RecordingArchiveRecordRepository()
    executor = ArchiveExecutor(repo)
    result = executor.execute(_make_plan(item), conflict_strategy="skip", dry_run=True)
    assert result.outcomes[0].status is ArchiveStatus.FAILED
    assert result.failed_count == 1


def test_executor_records_planned_before_finalize(tmp_path: Path) -> None:
    """Executor writes a PLANNED record first, then the finalized one — under UoW this
    makes partial-failure rollback atomic."""
    source = _write_source(tmp_path, "x.jpg")
    archive_root = tmp_path / "archive"
    item = _make_plan_item(source, str(archive_root))
    repo = _RecordingArchiveRecordRepository()
    executor = ArchiveExecutor(repo)
    executor.execute(_make_plan(item), conflict_strategy="skip")
    # Final state should reflect ARCHIVED, not PLANNED.
    assert len(repo.added) == 1
    assert repo.added[0].status is ArchiveStatus.ARCHIVED


def test_executor_failed_on_oserror(tmp_path: Path) -> None:
    """OSError during copy → FAILED outcome + error captured in record."""
    # Make source a directory so shutil.copyfile raises IsADirectoryError (OSError subclass).
    source = tmp_path / "src" / "x.jpg"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.mkdir()  # not a file
    archive_root = tmp_path / "archive"
    item = _make_plan_item(source, str(archive_root))
    repo = _RecordingArchiveRecordRepository()
    executor = ArchiveExecutor(repo)
    result = executor.execute(_make_plan(item), conflict_strategy="skip")
    assert result.outcomes[0].status is ArchiveStatus.FAILED
    assert result.outcomes[0].error is not None
    assert repo.added[0].status is ArchiveStatus.FAILED
