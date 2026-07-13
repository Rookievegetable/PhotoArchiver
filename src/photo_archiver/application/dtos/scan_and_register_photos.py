"""DTOs for scan-and-register photo workflows."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ScanAndRegisterPhotosResult:
    """Outcome of scanning a folder and registering discovered photos."""

    folder_id: UUID | None = None
    discovered_count: int = 0
    registered_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        """Return whether the workflow completed without item-level failures."""
        return not self.errors
