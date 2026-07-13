"""Thumbnail generation port for streaming use-case updates."""

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ThumbnailGenerator(Protocol):
    """Generate a cached thumbnail for a source image and return its path.

    Implementations MUST be idempotent: requesting the same source and size
    twice returns the same cached path without re-rendering. Cache invalidation
    is based on source mtime + file size so stale thumbnails are regenerated
    when the original changes.
    """

    def generate(self, source: Path, size: int = 256) -> Path:
        """Generate a square-bounded thumbnail of the source image.

        Args:
            source: Absolute path to the source image file.
            size: Target square bounding box in pixels (default 256).

        Returns:
            Path to the cached thumbnail file.
        """
        ...
