"""Detect duplicates service — B1 重复图片检测编排.

本服务编排 ``PhotoRepository.list_duplicate_groups``（Protocol
扩展于 B1-2），组装为 ``DuplicateReport`` DTO 返 Presentation 层。**首版只报告不
删除**——删除用户文件属高危操作（ai-rules §20 安全规则），留后续版本裁决。

无 SQL、无 GUI——纯用例编排，符合 DEP-012/013。
"""

from loguru import logger

from photo_archiver.application.dtos.duplicates import DuplicateGroup, DuplicateReport
from photo_archiver.domain.repositories import PhotoRepository


class DetectDuplicatesService:
    """Orchestrate duplicate detection over the photo repository.

    The service is a thin coordination layer: the actual grouping logic lives
    in the repository implementation (SQL push-down for SQLite, in-memory
    aggregation for InMemory — dual-strategy with consistency guarded by contrast tests). The service
    wraps the groups into an ordered ``DuplicateReport`` so the UI gets a
    stable, "worst-first" presentation without re-sorting at the view layer.
    """

    def __init__(self, photo_repository: PhotoRepository) -> None:
        """Initialize the service with the photo repository to query.

        Args:
            photo_repository: Persistence target whose ``list_duplicate_groups``
                supplies the raw groups. Must satisfy the Protocol defined in
                ``domain/repositories/photo_repository.py``.
        """
        self._photo_repository = photo_repository

    def execute(self) -> DuplicateReport:
        """Return the duplicate report over all known photos.

        Groups are sorted by descending member count so the most duplicated
        files surface first in the UI report — a user auditing "which file did
        I import 5 times?" benefits from the worst offender at the top rather
        than scrolling through 1-duplicate noise.

        Returns:
            A ``DuplicateReport`` carrying every duplicate group; empty
            (``groups=()``) when no content hash appears on more than one
            photo. Photos with NULL content hash are excluded by the
            repository implementation and thus never appear here.
        """
        raw_groups = self._photo_repository.list_duplicate_groups()
        groups: list[DuplicateGroup] = []
        for group in raw_groups:
            # 契约：list_duplicate_groups 只返回 content_hash 非空的照片组（SQLite
            # WHERE metadata_content_hash IS NOT NULL + InMemory 显式 continue None）。
            # 若某仓储实现未守契约返回 NULL 哈希组，这里 fail-loud 暴露而非用空串
            # 静默吞（review-rules §13 禁静默失败；ADR-018 契约诚实）。
            first = group[0]
            if first.metadata is None or first.metadata.content_hash is None:
                raise RuntimeError(
                    f"PhotoRepository.list_duplicate_groups violated contract: "
                    f"returned a group whose first photo has NULL content_hash (photo_id={first.id})",
                )
            groups.append(
                DuplicateGroup(
                    content_hash=first.metadata.content_hash,
                    members=tuple(group),
                ),
            )
        groups_tuple = tuple(sorted(groups, key=lambda g: (-len(g.members), g.content_hash)))
        logger.info(
            "DetectDuplicatesService: found {} group(s) covering {} photo(s)",
            len(groups_tuple),
            sum(len(g.members) for g in groups_tuple),
        )
        return DuplicateReport(groups=groups_tuple)
