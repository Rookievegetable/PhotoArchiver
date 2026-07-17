"""Tests for ArchivePath value object — 落裁决 #2 命名规则段验证."""

from pathlib import PurePath

import pytest

from photo_archiver.domain import ArchivePath, ValidationError


def test_archive_path_holds_four_segments() -> None:
    """ArchivePath stores root/person/date/name segments verbatim (stripped)."""
    path = ArchivePath(
        archive_root="/archive",
        person_name="Alice",
        event_or_date="2024-05-01",
        original_name="photo.jpg",
    )
    assert path.archive_root == "/archive"
    assert path.person_name == "Alice"
    assert path.event_or_date == "2024-05-01"
    assert path.original_name == "photo.jpg"


def test_archive_path_rejects_empty_segment() -> None:
    """Each of the four segments must be non-empty."""
    with pytest.raises(ValidationError):
        ArchivePath(archive_root="", person_name="A", event_or_date="2024-05-01", original_name="x.jpg")
    with pytest.raises(ValidationError):
        ArchivePath(archive_root="/a", person_name="  ", event_or_date="2024-05-01", original_name="x.jpg")
    with pytest.raises(ValidationError):
        ArchivePath(archive_root="/a", person_name="A", event_or_date="", original_name="x.jpg")
    with pytest.raises(ValidationError):
        ArchivePath(archive_root="/a", person_name="A", event_or_date="2024-05-01", original_name="")


def test_archive_path_rejects_path_separator_in_segment() -> None:
    """person_name / event_or_date / original_name segments may not contain separators.

    archive_root is exempt — it is a path prefix and naturally contains separators.
    """
    with pytest.raises(ValidationError):
        ArchivePath(archive_root="/a", person_name="A/B", event_or_date="2024-05-01", original_name="x.jpg")
    with pytest.raises(ValidationError):
        ArchivePath(archive_root="/a", person_name="A", event_or_date="2024-05-01", original_name="x\\y.jpg")
    # archive_root 含分隔符是合法的（它是路径前缀）
    ok = ArchivePath(archive_root="/a/b", person_name="A", event_or_date="2024-05-01", original_name="x.jpg")
    assert ok.archive_root == "/a/b"


def test_archive_path_resolve_is_purepath_concat() -> None:
    """resolve() returns archive_root/person/date/name as a PurePath, no filesystem."""
    path = ArchivePath(
        archive_root="/archive",
        person_name="Alice",
        event_or_date="2024-05-01",
        original_name="photo.jpg",
    )
    resolved = path.resolve()
    assert isinstance(resolved, PurePath)
    assert resolved == PurePath("/archive/Alice/2024-05-01/photo.jpg")


def test_archive_path_relative_path_excludes_root() -> None:
    """relative_path returns person/date/name without the root segment."""
    path = ArchivePath(
        archive_root="/archive",
        person_name="Alice",
        event_or_date="2024-05-01",
        original_name="photo.jpg",
    )
    assert path.relative_path == PurePath("Alice/2024-05-01/photo.jpg")


def test_archive_path_is_frozen() -> None:
    """ArchivePath is a frozen value object — segment mutation is rejected."""
    path = ArchivePath(
        archive_root="/a", person_name="A", event_or_date="2024-05-01", original_name="x.jpg"
    )
    with pytest.raises(Exception):
        path.person_name = "Bob"  # type: ignore[misc]
