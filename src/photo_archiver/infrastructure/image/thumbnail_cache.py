"""Thumbnail cache path resolution and invalidation strategy."""

import re
from pathlib import Path
import hashlib

# Content-addressed entries only: 24 hex chars + a source-style extension.
# Anything else in the cache root is never touched by cleanup (ISSUE-023
# safety guard against mispointed cache roots).
_CACHE_FILE_PATTERN = re.compile(r"^[0-9a-f]{24}\.[a-z0-9]+$")


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
        digest = self.compute_key(source, size)
        if digest is None:
            return None
        ext = source.suffix.lower() or ".jpg"
        return self._root / f"{digest}{ext}"

    def compute_key(self, source: Path, size: int) -> str | None:
        """Return the content-addressed digest for a source (None if missing)."""
        try:
            stat = source.stat()
        except FileNotFoundError:
            return None
        key = f"{source.resolve(strict=False)}|{size}|{stat.st_mtime_ns}|{stat.st_size}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]

    def cleanup(self, keep_keys: set[str], *, dry_run: bool = True) -> tuple[int, int]:
        """Delete non-content-addressed-orphans not in ``keep_keys`` (ISSUE-023).

        Only files matching the ``{24-hex-key}{extension}`` form are removed —
        foreign files in the cache root are left untouched and counted as
        retained.
        """
        removed = 0
        retained = 0
        for entry in sorted(self._root.iterdir()):
            if not entry.is_file() or not _CACHE_FILE_PATTERN.match(entry.name):
                retained += 1
                continue
            if entry.stem in keep_keys:
                retained += 1
                continue
            if not dry_run:
                entry.unlink()
            removed += 1
        return removed, retained

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
