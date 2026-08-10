"""Plugin context port — B5 插件上下文门面（v2 收敛版）.

按裁决前置门拍板（2026-08-10）：
- **只读 PluginContext**——只暴露 search_photos + detect_duplicates 读方法；
  import/export 写能力暂缓留后续轮单独裁决（YAGNI 当前无清晰用例）。
- **可选上下文注入**——Plugin.enable(context=None) 兼容纯声明插件（HelloPlugin）。
- **宿主渲染动作结果**——Plugin.execute_action 返 ActionResult 结构化对象，
  宿主负责渲染/展示；插件不直触 UI/文件系统。

归 Application port 边界（DEP-060 Plugins → Application only）。
门面非 Service 全集——禁暴露 Repository / UnitOfWork / ArchivePhotosService /
WorkerExecutor / ApplicationContext 引用（详见 docs/development/plugin-context-design.md §3）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from photo_archiver.application.dtos import DuplicateReport
    from photo_archiver.domain import Photo, PhotoSearchCriteria


class PluginContext(Protocol):
    """受限只读门面——插件经此访问 Application Service 读子集。

    v2 收敛：仅暴露 search_photos + detect_duplicates 读方法。写能力
    （import_people / export）暂缓留后续轮单独裁决。Context 不持 Repository
    实例 / UnitOfWork / ApplicationContext 引用——见方案文档 §3 禁止清单。
    """

    def search_photos(self, criteria: "PhotoSearchCriteria") -> list["Photo"]:
        """Return photos matching the supplied search criteria (read-only).

        暴露 SearchPhotosService.execute —— B2 落地后的查询编排，插件
        可据 person/status/date 区间取照片做统计报表等读路径用例。

        Args:
            criteria: PhotoSearchCriteria 持 person_id/match_status/
                captured_from/captured_to 均可选 AND 组合。

        Returns:
            A list of matching Photo aggregates ordered by created_at + id.
            Empty when no photo matches.
        """
        ...

    def detect_duplicates(self) -> "DuplicateReport":
        """Return the duplicate-photo report across all loaded photos (read-only).

        暴露 DetectDuplicatesService.execute —— B1 落地后的查重编排，
        插件可取重复组做报表展示等读路径用例。

        Returns:
            DuplicateReport DTO 含重复组结构（groups + counts）。
        """
        ...
