"""Tests for ArchiveExecutor symlink containment — P2-005 fix (Phase 4.1).

Phase 3 security audit finding P2-005: the executor's pre-fix ``relative_to``
check was purely lexical, so a symlink/junction placed *inside* archive_root
could let ``mkdir``/``copy2`` write through it to a location outside the root
(local-attacker model). The fix adds filesystem-level containment
(``Path.resolve(strict=False)`` follows links) plus explicit leaf-symlink
rejection, mirrored into the dry-run path so previews show the same failure.

Real executor + real filesystem (tmp_path); repository is the same in-memory
fake used by test_archive_executor.py. Symlink creation requires privileges on
Windows (admin or Developer Mode) — tests skip gracefully when unavailable.
"""

import sys
from pathlib import Path
from uuid import uuid4

import pytest

from photo_archiver.application.dtos import ArchivePlan, ArchivePlanItem
from photo_archiver.application.services import ArchiveExecutor
from photo_archiver.domain import ArchiveRecord, ArchiveStatus, ArchivePath


class _RecordingArchiveRecordRepository:
    """In-memory ArchiveRecordRepository capturing add() calls for assertions."""

    def __init__(self) -> None:
        self.added: list[ArchiveRecord] = []

    def add(self, record: ArchiveRecord) -> None:
        existing = next((r for r in self.added if r.id == record.id), None)
        if existing is not None:
            existing.status = record.status
            existing.archived_at = record.archived_at
            existing.error = record.error
        else:
            self.added.append(record)


def _make_plan_item(source: Path, archive_root: str, person_name: str = "Alice") -> ArchivePlanItem:
    return ArchivePlanItem(
        photo_id=uuid4(),
        source_path=source,
        target_path=ArchivePath(
            archive_root=archive_root,
            person_name=person_name,
            event_or_date="2024-05-01",
            original_name="x.jpg",
        ),
        person_id=uuid4(),
        person_name=person_name,
    )


def _write_source(tmp_path: Path, name: str, content: bytes = b"x") -> Path:
    source = tmp_path / "src" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    return source


def _create_symlink(link: Path, target: Path, *, is_directory: bool) -> bool:
    """Create a symlink, returning False when the platform forbids it.

    Windows needs admin or Developer Mode for symlink privileges; CI runners
    usually have them, local accounts may not. Skipping keeps the suite green
    without weakening the containment assertions elsewhere.
    """
    try:
        link.symlink_to(target, target_is_directory=is_directory)
        return True
    except (OSError, NotImplementedError):
        return False


def _plan(item: ArchivePlanItem) -> ArchivePlan:
    return ArchivePlan(items=(item,))


def test_symlinked_person_dir_inside_root_cannot_escape(tmp_path: Path) -> None:
    """A pre-existing symlinked directory inside archive_root is refused.

    Alice/ is a symlink to <tmp>/outside, so the lexical target
    archive/Alice/2024-05-01/x.jpg would physically land *outside* the root
    through the link. The filesystem-level containment check must fail the
    item before any mkdir/copy — nothing may be written outside the root.
    """
    source = _write_source(tmp_path, "x.jpg", b"evil")
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    if not _create_symlink(archive_root / "Alice", outside, is_directory=True):
        pytest.skip("symlink creation not permitted on this platform/account")

    result = ArchiveExecutor(_RecordingArchiveRecordRepository()).execute(
        _plan(_make_plan_item(source, str(archive_root))), conflict_strategy="skip"
    )

    outcome = result.outcomes[0]
    assert outcome.status is ArchiveStatus.FAILED
    assert outcome.error is not None
    assert "via filesystem links" in outcome.error
    # The write-through must NOT have happened on the other side of the link.
    assert not (outside / "2024-05-01" / "x.jpg").exists()


def test_symlinked_leaf_target_is_refused_even_if_inside_root(tmp_path: Path) -> None:
    """Never overwrite or write through a symlinked *leaf* target."""
    source = _write_source(tmp_path, "x.jpg", b"new")
    archive_root = tmp_path / "archive"
    day_dir = archive_root / "Alice" / "2024-05-01"
    day_dir.mkdir(parents=True)
    # Innocent bystander inside the root that the symlink points at.
    bystander = day_dir / "other.jpg"
    bystander.write_bytes(b"original")
    if not _create_symlink(day_dir / "x.jpg", bystander, is_directory=False):
        pytest.skip("symlink creation not permitted on this platform/account")

    result = ArchiveExecutor(_RecordingArchiveRecordRepository()).execute(
        _plan(_make_plan_item(source, str(archive_root))), conflict_strategy="overwrite"
    )

    outcome = result.outcomes[0]
    assert outcome.status is ArchiveStatus.FAILED
    assert outcome.error is not None
    assert "target is a symlink" in outcome.error
    assert bystander.read_bytes() == b"original"  # untouched through the link


def test_dry_run_reports_symlink_escape_as_failed(tmp_path: Path) -> None:
    """Dry-run previews surface the same containment failure the real run has."""
    source = _write_source(tmp_path, "x.jpg")
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    if not _create_symlink(archive_root / "Alice", outside, is_directory=True):
        pytest.skip("symlink creation not permitted on this platform/account")

    result = ArchiveExecutor(_RecordingArchiveRecordRepository()).execute(
        _plan(_make_plan_item(source, str(archive_root))), conflict_strategy="skip", dry_run=True
    )

    outcome = result.outcomes[0]
    assert outcome.status is ArchiveStatus.FAILED  # not DRY_RUN — plan is unsafe
    assert outcome.error is not None
    assert "via filesystem links" in outcome.error


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are a Windows concept")
def test_junction_escape_is_refused_without_privileges(tmp_path: Path) -> None:
    """Windows variant of the escape test using a directory junction.

    Junctions need no admin/Developer-Mode privileges, so this test actually
    exercises the filesystem-level containment on Windows instead of skipping.
    ``Path.resolve()`` follows junctions, so the same refusal must trigger.
    """
    source = _write_source(tmp_path, "x.jpg", b"evil")
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    import _winapi  # noqa: PLC0415 — Windows-only stdlib module, import at use site

    _winapi.CreateJunction(str(outside), str(archive_root / "Alice"))

    result = ArchiveExecutor(_RecordingArchiveRecordRepository()).execute(
        _plan(_make_plan_item(source, str(archive_root))), conflict_strategy="skip"
    )

    outcome = result.outcomes[0]
    assert outcome.status is ArchiveStatus.FAILED
    assert outcome.error is not None
    assert "via filesystem links" in outcome.error
    assert not (outside / "2024-05-01" / "x.jpg").exists()
