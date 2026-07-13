"""Pillow-based thumbnail generator with on-disk cache."""

from pathlib import Path

from loguru import logger

from photo_archiver.application.ports import ThumbnailGenerator
from photo_archiver.infrastructure.image.thumbnail_cache import ThumbnailCache


class PillowThumbnailGenerator(ThumbnailGenerator):
    """Generate cached thumbnails using Pillow.

    Delegates cache path resolution and invalidation to :class:`ThumbnailCache`
    so this adapter only renders when a cache miss occurs.
    """

    def __init__(self, cache: ThumbnailCache) -> None:
        """Initialize the generator with a cache strategy."""
        self._cache = cache

    def generate(self, source: Path, size: int = 256) -> Path:
        """Return the cached thumbnail path, rendering on cache miss.

        Args:
            source: Absolute path to the source image.
            size: Target square bounding box in pixels.

        Returns:
            Path to the cached thumbnail file.

 Raises:
            FileNotFoundError: If the source file does not exist.
            OSError: If the image cannot be decoded or written.
        """
        cached = self._cache.resolve(source, size)
        if cached.exists() and not self._cache.is_stale(source, cached):
            return cached

        from PIL import Image

        Image.MAX_IMAGE_PIXELS = None  # disable decompression bomb limit for archives
        with Image.open(source) as image:
            thumbnail = image.copy()
            thumbnail.thumbnail((size, size))
            cached.parent.mkdir(parents=True, exist_ok=True)
            thumbnail.save(cached)
        logger.debug("Generated thumbnail {} from {}", cached, source)
        return cached
