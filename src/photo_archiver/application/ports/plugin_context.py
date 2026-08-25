"""Plugin context port — 插件上下文门面（阶段 1 公共边界加固 ADR-026；阶段 3 写能力 ADR-028）.

按 ADR-026 拍板（前置门 2026-08-11，定稿草案 `docs/development/phase1-adr-draft.md`）：
- **只读 PluginContext**——只暴露 search_photos + detect_duplicates 读方法；
  import/export 写能力暂缓留后续轮单独裁决（YAGNI 当前无清晰用例）。
- **Plugin DTO 边界**——协议签名不再触 Domain 类型（PhotoSearchCriteria / Photo /
  DuplicateReport），改引用 Application 层 Plugin DTO（PluginPhotoQuery /
  PluginPhotoSummary / PluginDuplicateReport），加固 DEP-060 Plugins → Application only。
- **宿主渲染动作结果**——Plugin.execute_action 返 ActionResult 结构化对象，
  宿主负责渲染/展示；插件不直触 UI/文件系统。

按 ADR-028 拍板（前置门 2026-08-13，定稿草案 `docs/development/phase3-adr-draft.md`）：
- **重新开放写能力 import_people**（推翻 B5-a 暂缓依据"YAGNI 当前无清晰用例"——
  真实用例已现：插件从外部 CSV/JSON 导入人员实体）。裁决点 1=A 仅 import_people
  先行；export 续暂缓留后续轮单独裁决（ExportController 已有宿主路径不需插件触发）。
- **双向 DTO 脱 Domain**（裁决点 3=C）——import_people 签名用 PluginImportPeopleCommand
  入参 + PluginImportResult 结果，**不触 Domain Person/UUID 字面/PersonRepository**。
- **无宿主审批门**（裁决点 2=A）——插件直调 Service，宿主仅渲染 ActionResult。

归 Application port 边界（DEP-060 Plugins → Application only）。
门面非 Service 全集——禁暴露 Repository / UnitOfWork / ArchivePhotosService /
WorkerExecutor / ApplicationContext 引用（详见 docs/development/plugin-context-design.md §3）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from photo_archiver.application.dtos.plugin_context import (
        PluginDuplicateReport,
        PluginImportPeopleCommand,
        PluginImportResult,
        PluginPhotoQuery,
        PluginPhotoSummary,
    )


class PluginContext(Protocol):
    """受限门面——插件经此访问 Application Service 子集。

    阶段 1 加固（ADR-026）：协议签名改引用 Plugin DTO，插件不再触 Domain
    类型。暴露 search_photos + detect_duplicates 读方法。

    阶段 3 写能力（ADR-028）：扩 import_people 写方法（裁决点 1=A 仅
    import_people 先行，export 续暂缓）。双向 DTO 脱 Domain（裁决点 3=C），
    无宿主审批门（裁决点 2=A）。Context 不持 Repository 实例 / UnitOfWork /
    ApplicationContext 引用——见方案文档 §3 禁止清单。
    """

    def search_photos(self, query: "PluginPhotoQuery") -> tuple["PluginPhotoSummary", ...]:
        """Return photos matching the supplied query (read-only).

        暴露 SearchPhotosService.execute —— B2 落地后的查询编排，插件
        可据 person/status/date 区间取照片做统计报表等读路径用例。

        Args:
            query: PluginPhotoQuery 持 person_id/match_status（3 态：
                pending/approved/rejected，与 Domain MatchStatus 一致，不含 none）/
                captured_from/captured_to 均可选 AND 组合。

        Returns:
            A tuple of matching PluginPhotoSummary ordered by created_at + id.
            Empty when no photo matches. match_status 4 态含 none
            （RecognitionResult 不存在即未注册审核）。
        """
        ...

    def detect_duplicates(self) -> "PluginDuplicateReport":
        """Return the duplicate-photo report across all loaded photos (read-only).

        暴露 DetectDuplicatesService.execute —— B1 落地后的查重编排，
        插件可取重复组做报表展示等读路径用例。

        Returns:
            PluginDuplicateReport DTO 含重复组结构（groups + counts）。
        """
        ...

    def import_people(self, command: "PluginImportPeopleCommand") -> "PluginImportResult":
        """Import people entities from plugin-supplied rows (write, ADR-028).

        阶段 3 写能力（ADR-028，裁决点 1=A）——暴露 ImportPeopleService.execute，
        插件可从外部 CSV/JSON 导入人员实体。推翻 B5-a 暂缓依据"YAGNI 当前无
        清晰用例"，真实用例已现。

        裁决点 3=C 双向 DTO 脱 Domain——入参 PluginImportPeopleCommand 持
        PluginImportPersonRow rows（不触 Domain Person/PersonImportRow），宿主
        Service 映射时补 row_number（元组序）；结果 PluginImportResult 持
        imported_count/skipped_count/imported_person_ids: tuple[str, ...]
        （非 UUID，脱 Domain 字面）/errors。

        裁决点 2=A 无宿主审批门——插件直调本方法，宿主仅渲染 ActionResult
        摘要（imported/skipped/errors）。

        Args:
            command: PluginImportPeopleCommand 持 rows: tuple[PluginImportPersonRow, ...]
                （name 必填 / identity/department/note 可选）。

        Returns:
            PluginImportResult DTO 含 imported_count/skipped_count/
            imported_person_ids（str 非 UUID）/errors。
        """
        ...
