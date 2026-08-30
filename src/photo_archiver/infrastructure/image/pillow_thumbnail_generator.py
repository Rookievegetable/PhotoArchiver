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

    def __init__(self, cache: ThumbnailCache, max_image_pixels: int | None = None) -> None:
        """Initialize the generator with a cache strategy and a pixel guard.

        Args:
            cache: Cache strategy resolving thumbnail paths.
            max_image_pixels: Optional decompression-bomb guard applied to the
                Pillow pixel limit (P2-002 fix). ``None`` keeps Pillow's
                built-in default; a positive value tunes the global limit.
        """
        self._cache = cache
        if max_image_pixels is not None:
            from PIL import Image

            Image.MAX_IMAGE_PIXELS = max_image_pixels

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
        if cached is None:
            raise FileNotFoundError(f"ThumbnailCache.resolve returned None for {source}")
        if cached.exists() and not self._cache.is_stale(source, cached):
            return cached

        from PIL import Image

        try:
            with Image.open(source) as image:
                thumbnail = image.copy()
                thumbnail.thumbnail((size, size))
                cached.parent.mkdir(parents=True, exist_ok=True)
                thumbnail.save(cached)
        except Image.DecompressionBombError as exc:
            # P2-002 fix: refuse oversized images with a clear OSError so the
            # per-photo worker error handling can isolate the failure instead
            # of exhausting memory on decode.
            raise OSError(
                f"Image exceeds the configured MAX_IMAGE_PIXELS guard and was refused: {source}"
            ) from exc
        logger.debug("Generated thumbnail {} from {}", cached, source)
        return cached
