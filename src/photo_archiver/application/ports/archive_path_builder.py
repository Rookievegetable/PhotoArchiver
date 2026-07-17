"""Archive path builder port — builds ArchivePath from domain fields.

落 Phase 2 Step 11 裁决 #2 命名规则：
    {archive_root}/{person_name}/{event_or_date}/{original_name}
"""

from datetime import datetime
from typing import Protocol, runtime_checkable

from photo_archiver.domain.value_objects import ArchivePath


@runtime_checkable
class ArchivePathBuilder(Protocol):
    """Build an ArchivePath from the person name, captured_at, and original name.

    The builder owns the裁决 #2 naming rule and the降级 strategy
    (unknown-date / unknown-person segments). ArchivePlanner injects
    this port so tests can swap naming rules without touching the planner.
    """

    def build(
        self,
        archive_root: str,
        person_name: str,
        captured_at: datetime | None,
        original_name: str,
    ) -> ArchivePath:
        """Return the planned archive path for one photo.

        Args:
            archive_root: Root directory string (validated non-empty by caller).
            person_name: The matched person's name; empty becomes unknown-person.
            captured_at: Photo capture timestamp; None becomes unknown-date.
            original_name: The source file name to preserve at the leaf.
        """
        ...
