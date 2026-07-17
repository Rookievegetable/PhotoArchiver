"""Thumbnail cache path resolution and invalidation strategy."""

from pathlib import Path
import hashlib


class ThumbnailCache:
    """Resolve thumbnail cache paths and detect stale entries.

    Cache key is a hash of the source path + size + mtime + file size so
    renamed or edited photos invalidate their thumbnails automatically.
    """

    def __init__(self, cache_root: Path) -> None:
        """Initialize the cache with its root directory.

        Args:
            cache_root: Directory under which thumbnail files are stored.
                Created eagerly so callers never need to bootstrap it.
        """
        self._root = Path(cache_root)
        self._root.mkdir(parents=True, exist_ok=True)

    def resolve(self, source: Path, size: int) -> Path | None:
        """Return the cache file path for the given source and size.

        Returns ``None`` when the source file does not exist (``stat`` fails)
        so callers can skip rendering instead of crashing. When the source
        exists, the cache path is derived from a hash of source path + size +
        mtime + file size so renamed or edited photos invalidate automatically.
        """
        try:
            stat = source.stat()
        except FileNotFoundError:
            return None
        key = f"{source.resolve(strict=False)}|{size}|{stat.st_mtime_ns}|{stat.st_size}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        ext = source.suffix.lower() or ".jpg"
        return self._root / f"{digest}{ext}"

    def is_stale(self, source: Path, cached: Path) -> bool:
        """Return whether the cached thumbnail is missing or outdated.

        A cached file is stale when it no longer exists. Mtime/size changes
        are already encoded into the cache path via :meth:`resolve`, so a
        present file at the resolved path is by construction current.
        """
        return not cached.exists()

    @property
    def root(self) -> Path:
        """Return the cache root directory."""
        return self._root
