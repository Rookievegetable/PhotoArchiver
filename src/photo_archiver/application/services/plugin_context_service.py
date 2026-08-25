"""Plugin context service — Plugin DTO ↔ Domain 映射编排（阶段 1，ADR-026）.

本服务是 PluginContext Protocol 的具体实现——宿主经此向插件暴露只读
Application Service 子集（search_photos + detect_duplicates），但**返 Plugin DTO
而非 Domain 实体**（加固 DEP-060 Plugins → Application only，插件不触 Domain）。

职责链::

    Plugin DTO（PluginPhotoQuery / PluginDuplicateReport）
      ↓
    映射为 Domain 入参（PhotoSearchCriteria / 调 SearchPhotosService）
      ↓
    Application Service 编排（SearchPhotosService / DetectDuplicatesService）
      ↓
    联查 RecognitionRepository 取 match_status（Photo 实体无此字段）
      ↓
    映射为 Plugin DTO 返（PluginPhotoSummary / PluginDuplicateReport）

阶段 1 加固（ADR-026）：

- ``PluginPhotoQuery.match_status`` 3 态 → ``PhotoSearchCriteria.match_status``
  Domain ``MatchStatus``：字面值一致（pending/approved/rejected），直映射。
- ``PluginPhotoSummary.match_status`` 4 态含 none——RecognitionResult 不存在
  即"未注册审核"。InMemory 仓储不持 recognition，按契约返 "none"（与
  InMemory 下 search match_status 轴行为一致）。
- ``PluginPhotoSummary.registered_at`` 映射自 ``Photo.created_at``（注册入库时刻；
  Photo entity 无 registered_at 字段，created_at 即其语义）。
- ``PluginDuplicateReport`` 跎 DuplicateReport 但脱 content_hash 与 Photo 实体引用——
  groups 持 PluginDuplicateGroup（photo_ids + count），不暴露哈希原值。

阶段 3 写能力（ADR-028，拍板 2026-08-13）：

- 新增 ``import_people`` 写方法——``PluginImportPeopleCommand.rows`` 映射为
  Application ``PersonImportRow``（补 row_number 元组序 1-based），委托
  ``ImportPeopleService.import_rows`` 落库，结果 ``ImportPeopleResult.person_ids``
  （UUID）→ ``PluginImportResult.imported_person_ids``（str）脱 Domain 字面。
  仅此一条写路径开放（裁决点 1=A）；export 续暂缓；无宿主审批门（裁决点 2=A）。

不持 Repository 实例给插件——本服务是 PluginContext 的具体实现，插件只触
PluginContext Protocol 签名，不触本服务类。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from photo_archiver.application.dtos import PersonImportRow
from photo_archiver.application.dtos.plugin_context import (
    PluginDuplicateGroup,
    PluginDuplicateReport,
    PluginImportPeopleCommand,
    PluginImportResult,
    PluginMatchStatusSummary,
    PluginPhotoQuery,
    PluginPhotoSummary,
)
from photo_archiver.application.services.detect_duplicates_service import DetectDuplicatesService
from photo_archiver.application.services.import_people_service import ImportPeopleService
from photo_archiver.application.services.search_photos_service import SearchPhotosService
from photo_archiver.domain import Photo, PhotoSearchCriteria
from photo_archiver.domain.entities.recognition import MatchStatus

if TYPE_CHECKING:
    from photo_archiver.domain.repositories import RecognitionRepository


def _map_match_status_to_domain(status: str | None) -> MatchStatus | None:
    """Map PluginPhotoQuery.match_status (3态) → Domain MatchStatus.

    Args:
        status: None / "pending" / "approved" / "rejected"——Query 不含 "none"。

    Returns:
        None passthrough；字面值映射 MatchStatus 枚举成员。
    """
    if status is None:
        return None
    return MatchStatus(status)


def _map_match_status_to_plugin(status: MatchStatus | None) -> PluginMatchStatusSummary:
    """Map Domain MatchStatus | None → PluginPhotoSummary.match_status (4态).

    None 即 RecognitionResult 不存在——返 "none"（未注册审核）。
    """
    if status is None:
        return "none"
    return status.value  # type: ignore[return-value]  # MatchStatus.value 是 str，运行时即 Literal 字面值


def _photo_to_summary(photo: Photo, recognition_status: MatchStatus | None) -> PluginPhotoSummary:
    """Map Domain Photo + recognition_status → PluginPhotoSummary.

    registered_at 映射自 photo.created_at（注册入库时刻；Photo 无 registered_at 字段）。
    captured_at 直映射（None 即未捕获拍摄日期，MINOR-7 语义）。
    """
    return PluginPhotoSummary(
        photo_id=photo.id,  # type: ignore[arg-type]  # Photo.id 雇 UUID | None，search 后必赋值
        captured_at=photo.captured_at,
        registered_at=photo.created_at,  # type: ignore[arg-type]  # created_at 在 _post_init_ 兜底 datetime.now()
        match_status=_map_match_status_to_plugin(recognition_status),
    )


def _duplicate_report_to_plugin(report: object) -> PluginDuplicateReport:
    """Map Domain-facing DuplicateReport → PluginDuplicateReport.

    脱 content_hash 与 Photo 实体引用——groups 持 PluginDuplicateGroup
    （photo_ids + count），不暴露哈希原值。
    """
    groups: tuple[PluginDuplicateGroup, ...] = tuple(
        PluginDuplicateGroup(
            photo_ids=tuple(member.id for member in group.members),  # type: ignore[arg-type, union-attr]
            count=len(group.members),
        )
        for group in report.groups  # type: ignore[attr-defined]
    )
    return PluginDuplicateReport(
        groups=groups,
        duplicate_group_count=report.group_count,  # type: ignore[attr-defined]
        duplicate_photo_count=report.photos_in_groups,  # type: ignore[attr-defined]
    )


def _query_to_criteria(query: PluginPhotoQuery) -> PhotoSearchCriteria:
    """Map PluginPhotoQuery → Domain PhotoSearchCriteria.

    captured_from/to date → datetime（PhotoSearchCriteria 持 datetime，Plugin
    DTO 持 date——在 date 当日 00:00:00 下推； Plugin 用 date 表达日粒度查询）。
    match_status 3 态直映射 MatchStatus（不含 none）。
    """
    captured_from_dt: datetime | None = (
        datetime.combine(query.captured_from, datetime.min.time())
        if query.captured_from is not None
        else None
    )
    captured_to_dt: datetime | None = (
        datetime.combine(query.captured_to, datetime.min.time())
        if query.captured_to is not None
        else None
    )
    return PhotoSearchCriteria(
        person_id=query.person_id,
        match_status=_map_match_status_to_domain(query.match_status),
        captured_from=captured_from_dt,
        captured_to=captured_to_dt,
    )


class PluginContextService:
    """Concrete PluginContext impl wiring read-only services + import write path.

    Injected by bootstrap into ApplicationContext.plugin_context. Host
    (MainWindow / PluginRegistry) consumes via PluginContext Protocol签名——
    plugins never touch this class directly.

    Args:
        search_service: SearchPhotosService (B2 落地)——Photo 查询编排。
        duplicates_service: DetectDuplicatesService (B1 落地)——查重编排。
        recognition_repository: RecognitionRepository——联查 RecognitionResult
            取 match_status（Photo 实体无此字段，需补联查）。InMemory 仓储不持
            recognition 时按契约返 "none"。
        import_people_service: ImportPeopleService (阶段 3 ADR-028)——人员导入
            写编排。插件经 import_people 调用，宿主映射 PluginImportPeopleCommand
            → tuple[PersonImportRow, ...]（补 row_number）走
            ImportPeopleService.import_rows，ImportPeopleResult →
            PluginImportResult（UUID → str 脱 Domain）。
    """

    def __init__(
        self,
        search_service: SearchPhotosService,
        duplicates_service: DetectDuplicatesService,
        recognition_repository: "RecognitionRepository",
        import_people_service: "ImportPeopleService",
    ) -> None:
        """Wire the read-only Application services + recognition repo + import service."""
        self._search = search_service
        self._duplicates = duplicates_service
        self._recognition = recognition_repository
        self._import_people = import_people_service

    def search_photos(self, query: PluginPhotoQuery) -> tuple[PluginPhotoSummary, ...]:
        """Delegate to SearchPhotosService + recognition repo联查，返 Plugin DTO.

        Args:
            query: PluginPhotoQuery 持 3 态 match_status + person_id + date 区间。

        Returns:
            tuple of PluginPhotoSummary ordered by created_at + id.
            match_status 4 态含 none（RecognitionResult 不存在即"未注册审核"）。
        """
        criteria = _query_to_criteria(query)
        photos = self._search.execute(criteria)
        summaries: list[PluginPhotoSummary] = []
        for photo in photos:
            photo_id = photo.id
            if photo_id is None:
                continue  # Photo.id 未赋值（search 后必赋，防御）
            recognition_results = self._recognition.list_by_photo(photo_id)
            recognition_status: MatchStatus | None = (
                recognition_results[0].status
                if recognition_results
                else None
            )
            summaries.append(_photo_to_summary(photo, recognition_status))
        return tuple(summaries)

    def detect_duplicates(self) -> PluginDuplicateReport:
        """Delegate to DetectDuplicatesService，映射为 Plugin DTO返.

        Returns:
            PluginDuplicateReport——groups 持 PluginDuplicateGroup（photo_ids
            + count），不暴露 content_hash 与 Photo 实体引用。
        """
        report = self._duplicates.execute()
        return _duplicate_report_to_plugin(report)

    def import_people(self, command: PluginImportPeopleCommand) -> PluginImportResult:
        """Delegate to ImportPeopleService，映射 Plugin DTO ↔ Application DTO（ADR-028）.

        阶段 3 写能力（裁决点 1=A 仅 import_people，2=A 无审批门，3=C 双向 DTO）。

        映射编排：
        - 入参 PluginImportPeopleCommand.rows: tuple[PluginImportPersonRow, ...]
          → Sequence[PersonImportRow]——补 row_number（元组序 +1，1-based）补
          PluginImportPersonRow 脱的字段，交 ImportPeopleService.import_rows。
        - 结果 ImportPeopleResult（person_ids: tuple[UUID, ...]）
          → PluginImportResult（imported_person_ids: tuple[str, ...]）——
          UUID → str 脱 Domain 字面。

        Args:
            command: PluginImportPeopleCommand 持 rows: tuple[PluginImportPersonRow, ...]
                （name 必填 / identity/department/note 可选）。

        Returns:
            PluginImportResult——imported_count/skipped_count/imported_person_ids
            （str 非 UUID）/errors。宿主渲染 ActionResult 摘要。
        """
        # PluginImportPersonRow → PersonImportRow（补 row_number 元组序 1-based）
        rows = tuple(
            PersonImportRow(
                name=row.name,
                identity=row.identity,
                department=row.department,
                note=row.note,
                row_number=index + 1,
            )
            for index, row in enumerate(command.rows)
        )
        app_result = self._import_people.import_rows(rows)
        # ImportPeopleResult → PluginImportResult（UUID → str 脱 Domain）
        return PluginImportResult(
            imported_count=app_result.imported_count,
            skipped_count=app_result.skipped_count,
            imported_person_ids=tuple(str(pid) for pid in app_result.person_ids),
            errors=app_result.errors,
        )
