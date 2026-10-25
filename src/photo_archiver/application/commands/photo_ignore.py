"""Commands for photo-level ignore/restore operations（界面优化 §3.1/§3.3）."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class IgnorePhotosCommand:
    """Ignore one or more photos within one clustering generation."""

    cluster_run_id: UUID
    photo_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class RestorePhotosCommand:
    """Restore one or more previously ignored photos of one generation."""

    cluster_run_id: UUID
    photo_ids: tuple[UUID, ...]
