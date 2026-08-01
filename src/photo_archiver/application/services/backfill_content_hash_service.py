"""Backfill content hash service — B1 重复图片检测的一次性回填.

已注册但 ``metadata.content_hash`` 为 NULL 的历史照片，走一次性回填
CLI 子命令而非启动时惰性补齐——显式、可测、不拖慢启动。本服务编排回填闭环：
    1. 取所有 content_hash 为 NULL 的照片（走 PhotoRepository.list_all + 内存过滤，
       避免扩 Protocol 加专门查询——回填是一次性低频操作，性能不敏感）
    2. 对每张照片复用已注入 hasher 的 PillowPhotoMetadataReader 重读元数据（仅取 fresh content_hash）
    3. 用 PhotoRepository.add 回写——仅替换 ``PhotoMetadata.content_hash`` 一字段（双层 replace），
       **保留原 metadata 的 width/height/file_size/modified_at/captured_at**。这守护 ADR-021 数据
       完整性：``Photo.captured_at`` 与 ``PhotoMetadata.captured_at`` 不发散（若整体替换 metadata，
       reader 重读会刷新 captured_at 为当前文件值，与原归档时确定的值可能不一致——用户替换同名
       文件内容后回填会静默覆盖原 metadata，违反"回填历史哈希"语义）。
    4. 若文件已删则跳过并 log warning

不绕过 Application：服务持 PhotoRepository Protocol 与 PhotoMetadataReader Port，
基础设施适配器（SQLitePhotoRepository / PillowPhotoMetadataReader）由装配注入。

**假设风险**：回填仅替 content_hash 一字段，故原 metadata 的其他字段必须就绪——即原照片注册
时已填 metadata。若历史照片 metadata 为 None（极早期数据），回填会跳过该照片（``candidates``
过滤已含 ``metadata is None``），不会写入空 metadata。这一假设在 B1 落地前的数据上成立。
"""

from dataclasses import dataclass, replace

from loguru import logger

from photo_archiver.application.ports import PhotoMetadataReader
from photo_archiver.domain.repositories import PhotoRepository


@dataclass(frozen=True, slots=True)
class BackfillContentHashResult:
    """Aggregate outcome of a one-time backfill run.

    scanned: How many photos with NULL content hash were considered.
    backfilled: How many had their content hash successfully computed and persisted.
    skipped_missing: How many were skipped because the underlying file no longer exists.
    failed: How many raised an unexpected exception during re-read (logged individually).
    """

    scanned: int
    backfilled: int
    skipped_missing: int
    failed: int

    @property
    def succeeded(self) -> bool:
        """Return whether the run completed with zero failures."""
        return self.failed == 0


class BackfillContentHashService:
    """One-time backfill of ``content_hash`` for photos registered before B1 wiring.

    Idempotent: re-running on a database where B1 is already wired finds zero NULL
    hashes and returns a no-op result. Safe to invoke repeatedly from the CLI.
    """

    def __init__(
        self,
        photo_repository: PhotoRepository,
        metadata_reader: PhotoMetadataReader,
    ) -> None:
        """Initialize the service with the photo repository and metadata reader.

        Args:
            photo_repository: Persistence target for reading NULL-hash photos and
                writing back the computed hashes.
            metadata_reader: Re-reads metadata including ``content_hash`` — MUST be
                constructed with a ``ContentHashCalculator`` (or the
                backfill is a no-op. The Application assembler is responsible for
                wiring the hasher; this service does not import Infrastructure.
        """
        self._photo_repository = photo_repository
        self._metadata_reader = metadata_reader

    def execute(self) -> BackfillContentHashResult:
        """Backfill content hashes for all photos currently missing one.

        Returns:
            A ``BackfillContentHashResult`` summarizing the run. Re-invocation on
            an already-backfilled database returns ``scanned=0`` and is a no-op.
        """
        candidates = [
            photo
            for photo in self._photo_repository.list_all()
            if photo.metadata is None or photo.metadata.content_hash is None
        ]
        backfilled = 0
        skipped_missing = 0
        failed = 0
        for photo in candidates:
            source_path = photo.path.raw_path
            if not source_path.exists():
                logger.warning(
                    "Backfill: photo {} source file missing at {}, skipping",
                    photo.id,
                    source_path,
                )
                skipped_missing += 1
                continue
            try:
                fresh_metadata = self._metadata_reader.read(source_path)
            except (OSError, ValueError, RuntimeError) as exc:
                logger.warning("Backfill: failed to re-read {}: {}", source_path, exc)
                failed += 1
                continue
            # 仅替换 content_hash 一字段，保留原 metadata 的 width/height/file_size/
            # modified_at/captured_at——守护 ADR-021 数据完整性（见模块 docstring）。
            # PhotoMetadata 是 frozen dataclass，用 replace 仅替一字段；Photo 是
            # @dataclass(slots=True) 非 frozen，但同样用 replace 重建保留其他字段。
            if photo.metadata is None:
                # 候选已过滤 metadata is None，但防御性检查——不写空 metadata 入仓储
                logger.warning("Backfill: photo {} has None metadata, skipping", photo.id)
                failed += 1
                continue
            updated_metadata = replace(photo.metadata, content_hash=fresh_metadata.content_hash)
            updated = replace(photo, metadata=updated_metadata)
            self._photo_repository.add(updated)
            backfilled += 1
        logger.info(
            "BackfillContentHashService: scanned={} backfilled={} skipped_missing={} failed={}",
            len(candidates),
            backfilled,
            skipped_missing,
            failed,
        )
        return BackfillContentHashResult(
            scanned=len(candidates),
            backfilled=backfilled,
            skipped_missing=skipped_missing,
            failed=failed,
        )
