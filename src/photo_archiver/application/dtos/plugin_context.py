"""Plugin-facing DTOs for PluginContext（阶段 1 公共边界加固，ADR-026）.

插件经 PluginContext 暴露的读方法返这些 Application 层 DTO，**不触 Domain 类型**
（加固 DEP-060 Plugins → Application only）。

按 ADR-026 拍板（前置门 2026-08-11）：

- ``PluginPhotoQuery.match_status`` 3 态（pending/approved/rejected，与 Domain
  ``MatchStatus(str, Enum)`` 字面值一致）——**不含 none**。Query 不支持查
  "未参与匹配" 照片（Domain 无对应值）。
- ``PluginPhotoSummary.match_status`` 4 态含 none——RecognitionResult 不存在
  即"未注册审核"，是插件层聚合概念（Domain MatchStatus 三态无 none）。
- ``PluginDuplicateReport`` 暴露 photo_ids tuple + count，**不暴露 content_hash
  原值、不持 Photo 实体引用**——最小权限给统计插件足够信息但无不必要的文件细节。

不可变（frozen + slots）——DTO 经 Service 构造后插件不应改动。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

PluginMatchStatusQuery = Literal["pending", "approved", "rejected"]
PluginMatchStatusSummary = Literal["pending", "approved", "rejected", "none"]


@dataclass(frozen=True, slots=True)
class PluginPhotoQuery:
    """Read-only query parameters for ``PluginContext.search_photos``.

    Args mirror ``PhotoSearchCriteria`` but use ``date`` (not ``datetime``)
    for captured_from/to——phot photos query at day granularity, and decoupling
    from Domain type keeps plugins framework-independent.

    match_status 3 态不含 none——Domain MatchStatus 无对应值，"未参与匹配"
    照片无法直接查询，需取全集后客户端过滤（PluginPhotoSummary.match_status
    == "none"）。
    """

    person_id: UUID | None = None
    match_status: PluginMatchStatusQuery | None = None
    captured_from: date | None = None
    captured_to: date | None = None


@dataclass(frozen=True, slots=True)
class PluginPhotoSummary:
    """Read-only photo summary surfaced to plugins.

    Minimal privilege: 不暴露绝对文件路径、原始文件名、Domain ``Photo`` 实体、
    Repository 实例、人员实体、嵌入向量与内容哈希原值。

    match_status 4 态含 none——RecognitionResult 不存在即"未注册审核"。
    captured_at 为 None 即"未捕获拍摄日期"（MINOR-7 语义）。
    """

    photo_id: UUID
    captured_at: datetime | None
    registered_at: datetime
    match_status: PluginMatchStatusSummary


@dataclass(frozen=True, slots=True)
class PluginDuplicateGroup:
    """One group of duplicate photos (sharing content hash).

    不暴露 content_hash 原值——给统计插件足够信息（photo_ids + count）但无
    不必要的文件细节。
    """

    photo_ids: tuple[UUID, ...]
    count: int


@dataclass(frozen=True, slots=True)
class PluginDuplicateReport:
    """Aggregate result of ``PluginContext.detect_duplicates``.

    与 Domain-facing ``DuplicateReport`` 平行但脱 Photo 实体引用——
    groups 持 PluginDuplicateGroup（photo_ids + count），不持 content_hash。
    """

    groups: tuple[PluginDuplicateGroup, ...]
    duplicate_group_count: int
    duplicate_photo_count: int
