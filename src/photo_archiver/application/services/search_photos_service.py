"""Search photos service — B2 搜索/筛选编排.

本服务编排 ``PhotoRepository.search(criteria)``（Protocol 扩展于 B2-2），
返回 ``list[Photo]`` DTO 返 Presentation 层。无 SQL、无 GUI——纯用例编排，
符合 DEP-012/013。

不新建专门 DTO：Photo 已 Domain 实体，跨用例直接持引用合规（与 B1
DetectDuplicatesService 同模式；无序列化落地故无冗余）。
"""

from loguru import logger

from photo_archiver.domain import Photo, PhotoSearchCriteria
from photo_archiver.domain.repositories import PhotoRepository


class SearchPhotosService:
    """Orchestrate photo search over the photo repository.

    The service is a thin coordination layer: the actual filtering logic lives
    in the repository implementation (SQL push-down for SQLite, in-memory
    filtering for InMemory — dual-strategy with consistency guarded by contrast
    tests). The service injects the criteria and logs the result count for
    observability; no business decision is made here.
    """

    def __init__(self, photo_repository: PhotoRepository) -> None:
        """Initialize the service with the photo repository to query.

        Args:
            photo_repository: Persistence target whose ``search`` supplies the
                filtered photos. Must satisfy the Protocol defined in
                ``domain/repositories/photo_repository.py``.
        """
        self._photo_repository = photo_repository

    def execute(self, criteria: PhotoSearchCriteria) -> list[Photo]:
        """Return photos matching every supplied criterion (AND combination).

        Args:
            criteria: The ``PhotoSearchCriteria`` carrying optional person_id /
                match_status / captured_from / captured_to axes. All-None
                criteria matches every photo (equivalent to ``list_all`` but
                routed through the same search contract for UI consistency).

        Returns:
            A list of matching ``Photo`` aggregates ordered by ``created_at``
            then ``id`` for stable presentation. Empty when no photo matches.
        """
        results = self._photo_repository.search(criteria)
        logger.info(
            "SearchPhotosService: person_id={} status={} from={} to={} matched {} photo(s)",
            criteria.person_id,
            criteria.match_status,
            criteria.captured_from,
            criteria.captured_to,
            len(results),
        )
        return results
