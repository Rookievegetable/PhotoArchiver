"""List persons service — Phase 9 FEAT-P9-2 筛选人员轴的读取用例.

本服务是 Presentation 筛选人员轴的数据入口：薄封装
``PersonRepository.list_all()``，把人员实体列表交给 FilterBar 下拉框填充。
与 ``SearchPhotosService`` 同模式——纯用例编排，无 SQL、无 GUI
（DEP-012/013）；持久化细节归仓储实现。

不新建专门 DTO：Person 已 Domain 实体，跨用例直接持引用合规（与 B1
DetectDuplicatesService / B2 SearchPhotosService 同模式；无序列化落地故无冗余）。
"""

from loguru import logger

from photo_archiver.domain import Person
from photo_archiver.domain.repositories import PersonRepository


class ListPersonsService:
    """Expose the person catalog to Presentation for the filter person axis.

    Thin read-only use case: the service adds no business decision — it
    returns whatever ``PersonRepository.list_all`` holds so the FilterBar can
    populate its selector. Ordering is the repository's (``list_all``
    contract) and is stable for presentation purposes.
    """

    def __init__(self, person_repository: PersonRepository) -> None:
        """Initialize the service with the person repository to read.

        Args:
            person_repository: Persistence target whose ``list_all`` supplies
                the person catalog. Must satisfy the Protocol defined in
                ``domain/repositories/person_repository.py``.
        """
        self._person_repository = person_repository

    def execute(self) -> list[Person]:
        """Return all known persons for filter population.

        Returns:
            The full person catalog in repository order. Empty when no person
            has been imported yet — the FilterBar then only offers its
            no-constraint "All persons" entry.
        """
        persons = self._person_repository.list_all()
        logger.info("ListPersonsService: {} person(s) available for filtering", len(persons))
        return persons
