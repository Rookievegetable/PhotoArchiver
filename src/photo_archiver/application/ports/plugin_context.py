"""Plugin context port — 插件上下文只读门面（阶段 1 公共边界加固，ADR-026）.

按 ADR-026 拍板（前置门 2026-08-11，定稿草案 `docs/development/phase1-adr-draft.md`）：
- **只读 PluginContext**——只暴露 search_photos + detect_duplicates 读方法；
  import/export 写能力暂缓留后续轮单独裁决（YAGNI 当前无清晰用例）。
- **Plugin DTO 边界**——协议签名不再触 Domain 类型（PhotoSearchCriteria / Photo /
  DuplicateReport），改引用 Application 层 Plugin DTO（PluginPhotoQuery /
  PluginPhotoSummary / PluginDuplicateReport），加固 DEP-060 Plugins → Application only。
- **宿主渲染动作结果**——Plugin.execute_action 返 ActionResult 结构化对象，
  宿主负责渲染/展示；插件不直触 UI/文件系统。

归 Application port 边界（DEP-060 Plugins → Application only）。
门面非 Service 全集——禁暴露 Repository / UnitOfWork / ArchivePhotosService /
WorkerExecutor / ApplicationContext 引用（详见 docs/development/plugin-context-design.md §3）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from photo_archiver.application.dtos.plugin_context import (
        PluginDuplicateReport,
        PluginPhotoQuery,
        PluginPhotoSummary,
    )


class PluginContext(Protocol):
    """受限只读门面——插件经此访问 Application Service 读子集。

    阶段 1 加固（ADR-026）：协议签名改引用 Plugin DTO，插件不再触 Domain
    类型。仍只暴露 search_photos + detect_duplicates 读方法；写能力
    （import_people / export）暂缓留后续轮单独裁决。Context 不持 Repository
    实例 / UnitOfWork / ApplicationContext 引用——见方案文档 §3 禁止清单。
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
