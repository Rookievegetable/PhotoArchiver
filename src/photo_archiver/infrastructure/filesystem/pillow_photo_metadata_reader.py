"""Pillow-based implementation of the photo metadata reader port.

EXIF 拍摄时刻读取（落 Phase 2 Step 11 裁决 #2 链式降级；ISSUE-019 修复
升级子 IFD 读取）：
    Exif 子 IFD DateTimeOriginal(36867)
    → Exif 子 IFD DateTimeDigitized(36868)
    → IFD0 顶层 DateTimeDigitized(36868，历史兼容)
    → PhotoMetadata.modified_at（文件 mtime）→ None
Archive 阶段只消费 ``Photo.captured_at`` 领域字段，本适配器是该字段的
唯一数据源。DateTimeOriginal(36867) 是相机原生记录，可信度最高；缺 EXIF
时回退 mtime（扫描过程中转存/拷贝会破坏 mtime，不可靠但好过留 None）。

content_hash 计算（B1 重复图片检测）：
    可选注入 ``ContentHashCalculator`` 实例——注入时在 Pillow 开图读 EXIF
    的同一 pass 内顺手算 SHA-256 填 ``PhotoMetadata.content_hash``；未注入
    时 reader 不算哈希保持向后兼容（既有调用方零改动）。归属 reader 而非
    Application service 的理由：保持 Application 零 Infrastructure 依赖
    （DEP-010），同一 pass 读图+哈希避免二次读盘（ai-rules §18 性能）。
"""

from datetime import datetime
from pathlib import Path

from loguru import logger

from photo_archiver.application.ports import PhotoMetadataReader
from photo_archiver.domain import PhotoMetadata
from photo_archiver.infrastructure.image import ContentHashCalculator

# Pillow EXIF tag ids（EXIF 标准命名，ISSUE-019 顺修原注释的命名错位）：
#   36867 = DateTimeOriginal（相机原生拍摄时刻，位于 Exif 子 IFD）
#   36868 = DateTimeDigitized（位于 Exif 子 IFD）
_EXIF_TAG_DATETIME_ORIGINAL = 36867
_EXIF_TAG_DATETIME_DIGITIZED = 36868
# EXIF 子 IFD 指针（0x8769）：EXIF 标准把拍摄时刻放在该子 IFD——真实相机/
# 手机照片几乎全是此结构；IFD0 顶层读取仅命中个别非标准写放。
_EXIF_SUB_IFD_POINTER = 0x8769
# 历史兼容：Phase 2 Step 11 从 IFD0 顶层读 36868（非标准结构，个别工具
# 按此写放），保留为降级链链尾（ISSUE-019）。
_LEGACY_IFD0_TAG_DATETIME_DIGITIZED = 36868


class PillowPhotoMetadataReader(PhotoMetadataReader):
    """Read basic image metadata using Pillow.

    When constructed with a ``ContentHashCalculator`` the reader also fills
    ``PhotoMetadata.content_hash`` during the same read pass, supporting B1
    duplicate detection without forcing the Application layer to coordinate a
    second Infrastructure adapter.
    """

    def __init__(
        self,
        content_hasher: ContentHashCalculator | None = None,
        max_image_pixels: int | None = None,
    ) -> None:
        """Initialize the reader with an optional content hash calculator.

        Args:
            content_hasher: When provided, the reader computes the SHA-256
                content hash of each photo in the same pass that reads Pillow
                metadata. When ``None`` (default) the reader keeps historical
                behavior and does not fill ``content_hash`` — existing callers
                are unaffected.
            max_image_pixels: Optional decompression-bomb guard applied to the
                Pillow pixel limit (P2-002 fix). ``None`` keeps Pillow's
                built-in default; a positive value tunes the global limit.
        """
        self._content_hasher = content_hasher
        if max_image_pixels is not None:
            from PIL import Image

            Image.MAX_IMAGE_PIXELS = max_image_pixels

    def read(self, path: Path) -> PhotoMetadata:
        """Return image dimensions, filesystem metadata, captured_at, and content hash.

        captured_at 降级链：Exif 子 IFD DateTimeOriginal → 子 IFD
        DateTimeDigitized → IFD0 顶层 DateTimeDigitized（历史兼容）→
        文件 mtime → None。
        EXIF 解析失败不抛错（只 log warning），mtime 兜底——保持本适配器
        对"无 EXIF 图片"（如 PNG、被剥离 EXIF 的 JPG）的非致命容忍。

        content_hash 仅当构造时注入了 ``ContentHashCalculator`` 才填充；
        否则保持 ``None``。哈希计算在 Pillow 开图读 EXIF 的同一 pass 内
        完成（文件已读入内存或可读），避免二次读盘。
        """
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:
            raise RuntimeError("Pillow is required to read photo metadata") from exc

        image_path = Path(path)
        if not image_path.exists():
            raise FileNotFoundError(f"Photo file does not exist: {image_path}")
        if not image_path.is_file():
            raise IsADirectoryError(f"Photo path is not a file: {image_path}")

        try:
            with Image.open(image_path) as image:
                width, height = image.size
                captured_at = self._extract_captured_at(image, image_path)
        except UnidentifiedImageError as exc:
            raise ValueError(f"Unsupported or invalid image file: {image_path}") from exc
        except Image.DecompressionBombError as exc:
            # P2-002 fix: map the bomb guard onto the existing ValueError path
            # so the scan loop's per-photo error isolation records it and keeps
            # processing the remaining photos.
            raise ValueError(
                f"Image exceeds the configured MAX_IMAGE_PIXELS guard: {image_path}"
            ) from exc
        except OSError as exc:
            raise ValueError(f"Failed to read image metadata: {image_path}") from exc

        stat = image_path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime)
        # EXIF 缺失时用 mtime 兜底；EXIF 异常时 captured_at 已为 None，同样兜底。
        if captured_at is None:
            captured_at = modified_at
        content_hash = self._compute_content_hash(image_path)
        return PhotoMetadata(
            width=width,
            height=height,
            file_size_bytes=stat.st_size,
            modified_at=modified_at,
            captured_at=captured_at,
            content_hash=content_hash,
        )

    def _compute_content_hash(self, image_path: Path) -> str | None:
        """Return the SHA-256 content hash, or None when no hasher is configured.

        哈希失败不抛错（只 log warning）——元数据读取的主职责不应因哈希算
        法 I/O 异常而中断扫描整批。调用方（B1 查重）按 content_hash 为 None
        处理"该照片不参与查重分组"的语义，与历史数据行为一致。
        """
        if self._content_hasher is None:
            return None
        try:
            return self._content_hasher.calculate(image_path)
        except (OSError, FileNotFoundError) as exc:
            logger.warning("Content hash failed for {}: {}", image_path, exc)
            return None

    @staticmethod
    def _extract_captured_at(image, image_path: Path) -> datetime | None:
        """Read EXIF capture time down a priority chain, tolerating failures.

        降级链（ISSUE-019 修复，2026-09-06）：

            Exif 子 IFD DateTimeOriginal(36867)
            → Exif 子 IFD DateTimeDigitized(36868)
            → IFD0 顶层 DateTimeDigitized(36868，历史兼容链尾)
            → None（调用方以文件 mtime 兜底）

        EXIF 标准把拍摄时刻置于 Exif 子 IFD（0x8769）——真实相机/手机照片
        几乎全是此结构；仅读 IFD0 顶层会 miss 而落 mtime 兜底，导致归档
        "按拍摄日期"分桶实际按文件修改时间执行（ISSUE-019 缺陷本体）。

        Args:
            image: An open PIL Image instance.
            image_path: The path being read, for log context only.

        Returns:
            The parsed datetime, or None when EXIF is absent / unparsable.
        """
        try:
            exif_data = image.getexif()
        except (AttributeError, OSError, ValueError) as exc:
            # getexif() 可在某些 Pillow 版本对无 EXIF 格式抛 ValueError；
            # OSError 涉及读文件底层；AttributeError 防御性兼容。
            logger.debug("No EXIF block for {}: {}", image_path, exc)
            return None
        if not exif_data:
            return None
        try:
            sub_ifd = exif_data.get_ifd(_EXIF_SUB_IFD_POINTER)
        except (AttributeError, OSError, ValueError) as exc:
            # 子 IFD 访问失败不致命：继续走 IFD0 历史兼容链尾。
            logger.debug("Exif sub-IFD unavailable for {}: {}", image_path, exc)
            sub_ifd = {}
        candidates = (
            (_EXIF_TAG_DATETIME_ORIGINAL, "DateTimeOriginal(sub-IFD)", sub_ifd),
            (_EXIF_TAG_DATETIME_DIGITIZED, "DateTimeDigitized(sub-IFD)", sub_ifd),
            (
                _LEGACY_IFD0_TAG_DATETIME_DIGITIZED,
                "DateTimeDigitized(IFD0 legacy)",
                exif_data,
            ),
        )
        for tag_id, tag_label, source in candidates:
            parsed = PillowPhotoMetadataReader._parse_exif_datetime(
                source.get(tag_id), image_path, tag_label
            )
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _parse_exif_datetime(
        raw_value: str, image_path: Path, tag_label: str
    ) -> datetime | None:
        """Parse one EXIF datetime candidate; log and return None on failure."""
        if raw_value is None:
            return None
        try:
            # EXIF DateTime 格式：'YYYY:MM:DD HH:MM:SS'（冒号分隔日期段）
            return datetime.strptime(raw_value, "%Y:%m:%d %H:%M:%S")
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Unparsable EXIF datetime ({}) for {}: {} ({})",
                tag_label,
                image_path,
                raw_value,
                exc,
            )
            return None