"""Tests for ArchivePathBuilderService — 落裁决 #2 命名规则 + 降级段."""

from datetime import datetime

from photo_archiver.application.services import ArchivePathBuilderService
from photo_archiver.domain.value_objects.archive_path import (
    UNKNOWN_EVENT_SEGMENT,
    UNKNOWN_PERSON_SEGMENT,
)


def _builder() -> ArchivePathBuilderService:
    return ArchivePathBuilderService()


def test_build_yields_naming_rule_segments() -> None:
    """build() produces {root}/{person}/{YYYY-MM-DD}/{original} per裁决 #2."""
    path = _builder().build(
        archive_root="/archive",
        person_name="Alice",
        captured_at=datetime(2024, 5, 1, 13, 45, 0),
        original_name="photo.jpg",
    )
    assert path.archive_root == "/archive"
    assert path.person_name == "Alice"
    assert path.event_or_date == "2024-05-01"
    assert path.original_name == "photo.jpg"


def test_build_falls_back_to_unknown_person_when_name_empty() -> None:
    """Empty person_name triggers the unknown-person placeholder segment."""
    path = _builder().build(
        archive_root="/archive",
        person_name="",
        captured_at=datetime(2024, 5, 1),
        original_name="photo.jpg",
    )
    assert path.person_name == UNKNOWN_PERSON_SEGMENT


def test_build_falls_back_to_unknown_date_when_captured_at_none() -> None:
    """None captured_at triggers the unknown-date placeholder segment."""
    path = _builder().build(
        archive_root="/archive",
        person_name="Alice",
        captured_at=None,
        original_name="photo.jpg",
    )
    assert path.event_or_date == UNKNOWN_EVENT_SEGMENT


def test_build_strips_whitespace_in_person_name() -> None:
    """Whitespace around person_name is normalized before segment emission."""
    path = _builder().build(
        archive_root="/archive",
        person_name="  Alice  ",
        captured_at=datetime(2024, 5, 1),
        original_name="photo.jpg",
    )
    assert path.person_name == "Alice"


def test_build_date_segment_is_iso_8601_without_separators_in_filename() -> None:
    """Date segment uses YYYY-MM-DD — no colons, cross-platform filename safe."""
    path = _builder().build(
        archive_root="/archive",
        person_name="Alice",
        captured_at=datetime(2024, 12, 31, 23, 59, 59),
        original_name="photo.jpg",
    )
    assert path.event_or_date == "2024-12-31"
    assert ":" not in path.event_or_date
