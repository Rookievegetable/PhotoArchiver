"""Thumbnail cache port for resolve / stale-check without infrastructure coupling.

Lives at the Application layer so ``PhotoListController`` (Presentation) can
depend on this Protocol rather than the concrete ``infrastructure.image.ThumbnailCache``
class — closing the ADR-002 hard violation surfaced in the second-round review.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ThumbnailCache(Protocol):
    """Resolve thumbnail cache paths and detect stale entries.

    Implementations MUST key on source path + size + mtime + file size so
    renamed or edited photos invalidate their thumbnails automatically. The
    concrete ``ThumbnailCache`` in ``infrastructure/image/`` honours this.
    """

    def resolve(self, source: Path, size: int) -> Path | None:
        """Return the cache file path for the given source and size.

        Returns ``None`` when the source file does not exist so callers can
        skip rendering instead of crashing.
        """
        ...

    def is_stale(self, source: Path, cached: Path) -> bool:
        """Return whether the cached thumbnail is missing or outdated."""
        ...
