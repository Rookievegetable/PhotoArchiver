"""Atomic export write tests (Phase D, P2-5).

The swap must leave the previous export intact when the write fails, and
never leave a ``.part`` sibling behind — at the target path a half-written
file is exactly the failure mode this exists to prevent.
"""

from pathlib import Path

from photo_archiver.infrastructure.exporters._atomic_write import write_atomic


def test_write_atomic_swaps_temp_into_target(tmp_path: Path) -> None:
    """Success: target holds the new content, no .part sibling remains."""
    target = tmp_path / "report.csv"

    write_atomic(target, lambda path: path.write_text("new export", encoding="utf-8"))

    assert target.read_text(encoding="utf-8") == "new export"
    assert list(tmp_path.glob("*.part")) == []


def test_write_atomic_failure_leaves_no_partial_file(tmp_path: Path) -> None:
    """A failing write removes the .part sibling and never touches the target."""
    target = tmp_path / "report.csv"
    target.write_text("previous export", encoding="utf-8")

    def failing_write(path: Path) -> object:
        path.write_text("half written", encoding="utf-8")
        raise RuntimeError("disk full mid-write")

    try:
        write_atomic(target, failing_write)
    except RuntimeError:
        pass

    assert target.read_text(encoding="utf-8") == "previous export"
    assert list(tmp_path.glob("*.part")) == []


def test_write_atomic_replaces_previous_export(tmp_path: Path) -> None:
    """Re-exporting over an existing file replaces it atomically."""
    target = tmp_path / "report.csv"
    target.write_text("old", encoding="utf-8")

    write_atomic(target, lambda path: path.write_text("fresh", encoding="utf-8"))
    write_atomic(target, lambda path: path.write_text("fresher", encoding="utf-8"))

    assert target.read_text(encoding="utf-8") == "fresher"
    assert list(tmp_path.glob("*.part")) == []
