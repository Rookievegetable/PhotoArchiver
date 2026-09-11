"""ArchivePathBuilderService — 落裁决 #2 命名规则 + 降级段。

命名规则：{archive_root}/{person_name}/{event_or_date}/{original_name}
降级策略：
    person_name 空 → unknown-person
    captured_at None → unknown-date
    captured_at 取日期段（YYYY-MM-DD，跨平台文件名安全、字典序与时间序一致）

ADR-036 D4：段值经 Domain `sanitize_windows_filename` 净化（ArchivePath 构造
时兜底强制）；本服务在净化改变输入时记一行 loguru 审计，便于把归档失败追溯
到"人名/文件名不安全"的真实原因。
"""

from datetime import datetime

from loguru import logger

from photo_archiver.application.ports import ArchivePathBuilder
from photo_archiver.domain.value_objects import ArchivePath
from photo_archiver.domain.value_objects.archive_path import (
    UNKNOWN_EVENT_SEGMENT,
    UNKNOWN_PERSON_SEGMENT,
    sanitize_windows_filename,
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
        safe_person = sanitize_windows_filename(person_segment)
        safe_event = sanitize_windows_filename(event_segment)
        safe_original = sanitize_windows_filename(original_name)
        if safe_person != person_segment:
            logger.warning(
                "ArchivePath person segment sanitized: {!r} -> {!r} (ADR-036 D4)",
                person_segment,
                safe_person,
            )
        if safe_event != event_segment:
            logger.warning(
                "ArchivePath event/date segment sanitized: {!r} -> {!r} (ADR-036 D4)",
                event_segment,
                safe_event,
            )
        if safe_original != original_name:
            logger.warning(
                "ArchivePath original-name segment sanitized: {!r} -> {!r} (ADR-036 D4)",
                original_name,
                safe_original,
            )
        return ArchivePath(
            archive_root=archive_root,
            person_name=safe_person,
            event_or_date=safe_event,
            original_name=safe_original,
        )
