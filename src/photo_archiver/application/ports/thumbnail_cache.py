"""Thumbnail cache port for resolve / stale-check without infrastructure coupling.

Lives at the Application layer so ``PhotoListController`` (Presentation) can
depend on this Protocol rather than the concrete ``infrastructure.image.ThumbnailCache``
class — closing the ADR-002 hard violation surfaced in the second-round review.
"""

from pathlib import Path
from typing import Final, Protocol, runtime_checkable

# 唯一缩略图渲染尺寸（photo_list_controller / cleanup service 共用）。
DEFAULT_THUMBNAIL_SIZE: Final = 256


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

    def compute_key(self, source: Path, size: int) -> str | None:
        """Return the content-addressed cache key digest for a source.

        Mirrors the digest embedded in :meth:`resolve`'s file name; ``None``
        when the source file does not exist. Cleanup consumers build the
        keep-set from these keys.
        """
        ...

    def cleanup(self, keep_keys: set[str], *, dry_run: bool = True) -> tuple[int, int]:
        """Delete cache files whose key is not in ``keep_keys`` (ISSUE-023).

        Returns ``(removed, retained)`` counts; with ``dry_run`` the removal
        is only counted, never performed. Only content-addressed entries
        (24-hex-char key + extension) are ever considered for removal.
        """
        ...
