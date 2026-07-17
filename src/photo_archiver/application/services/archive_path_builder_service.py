"""ArchivePathBuilderService — 落裁决 #2 命名规则 + 降级段。

命名规则：{archive_root}/{person_name}/{event_or_date}/{original_name}
降级策略：
    person_name 空 → unknown-person
    captured_at None → unknown-date
    captured_at 取日期段（YYYY-MM-DD，跨平台文件名安全、字典序与时间序一致）
"""

from datetime import datetime

from photo_archiver.application.ports import ArchivePathBuilder
from photo_archiver.domain.value_objects import ArchivePath
from photo_archiver.domain.value_objects.archive_path import (
    UNKNOWN_EVENT_SEGMENT,
    UNKNOWN_PERSON_SEGMENT,
)

# 裁决 #2 落地：ISO 8601 日期段，无冒号 → 跨平台文件名安全。
_DATE_FORMAT = "%Y-%m-%d"


class ArchivePathBuilderService(ArchivePathBuilder):
    """Build ArchivePath values from domain fields per the Step 11 naming rule."""

    def build(
        self,
        archive_root: str,
        person_name: str,
        captured_at: datetime | None,
        original_name: str,
    ) -> ArchivePath:
        """Return the planned archive path for one photo.

        Args:
            archive_root: Root directory string (must be non-empty).
            person_name: Matched person's name; whitespace-stripped; empty → unknown-person.
            captured_at: Capture timestamp; None → unknown-date segment.
            original_name: Source file name to preserve at the leaf.
        """
        normalized_person = person_name.strip() if person_name else ""
        person_segment = normalized_person if normalized_person else UNKNOWN_PERSON_SEGMENT
        event_segment = (
            captured_at.strftime(_DATE_FORMAT)
            if captured_at is not None
            else UNKNOWN_EVENT_SEGMENT
        )
        return ArchivePath(
            archive_root=archive_root,
            person_name=person_segment,
            event_or_date=event_segment,
            original_name=original_name,
        )
