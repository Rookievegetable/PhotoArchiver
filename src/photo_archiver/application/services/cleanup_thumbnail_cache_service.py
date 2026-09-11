"""Thumbnail cache cleanup service (ISSUE-023 / 体检 N-8, ADR-036 后续收口).

内容寻址缓存键包含源文件 mtime/size——照片重命名、编辑、删除登记后，旧缓存
条目成为孤儿且此前只增不减。本服务按"当前库内照片 × 当前渲染尺寸"构建
keep 集合，删除缓存根目录下不在集合内的内容寻址条目（24 hex + 扩展名形式，
外来文件一律不动）。

与 prune-missing 同语义：**dry-run 默认**，``--execute`` 才真删；被删除的
是派生数据（缩略图），最坏后果是下次打开照片墙时重新生成，无数据风险。
"""

from dataclasses import dataclass

from loguru import logger

from photo_archiver.application.ports import ThumbnailCache
from photo_archiver.application.ports.thumbnail_cache import DEFAULT_THUMBNAIL_SIZE
from photo_archiver.domain import PhotoRepository


@dataclass(frozen=True, slots=True)
class ThumbnailCacheCleanupResult:
    """Outcome of one thumbnail-cache cleanup pass."""

    removed: int
    retained: int
    dry_run: bool

    @property
    def succeeded(self) -> bool:
        """The pass itself cannot fail row-level; presence for CLI symmetry."""
        return True


class CleanupThumbnailCacheService:
    """Reconcile the thumbnail cache against the current photo library."""

    def __init__(
        self,
        photo_repository: PhotoRepository,
        thumbnail_cache: ThumbnailCache,
        thumbnail_size: int = DEFAULT_THUMBNAIL_SIZE,
    ) -> None:
        """Initialize with the photo repository and the cache port.

        Args:
            photo_repository: Source of truth for the keep-set (every
                registered photo contributes its current cache key).
            thumbnail_cache: Cache port whose ``compute_key``/``cleanup``
                build and enforce the keep-set.
            thumbnail_size: Render size the UI generates thumbnails for
                (``DEFAULT_THUMBNAIL_SIZE``); entries for other sizes count
                as orphans.
        """
        self._photo_repository = photo_repository
        self._thumbnail_cache = thumbnail_cache
        self._thumbnail_size = thumbnail_size

    def execute(self, *, dry_run: bool = True) -> ThumbnailCacheCleanupResult:
        """Run one cleanup pass (dry-run by default, mirrors prune-missing)."""
        keep_keys: set[str] = set()
        missing_sources = 0
        for photo in self._photo_repository.list_all():
            key = self._thumbnail_cache.compute_key(photo.path.raw_path, self._thumbnail_size)
            if key is None:
                missing_sources += 1  # 源文件已失联：其旧缓存条目按孤儿处理
                continue
            keep_keys.add(key)
        removed, retained = self._thumbnail_cache.cleanup(keep_keys, dry_run=dry_run)
        logger.info(
            "Thumbnail cache cleanup (dry_run={}): removed={}, retained={}, "
            "photos={}, missing_sources={}",
            dry_run,
            removed,
            retained,
            len(keep_keys) + missing_sources,
            missing_sources,
        )
        return ThumbnailCacheCleanupResult(removed=removed, retained=retained, dry_run=dry_run)
