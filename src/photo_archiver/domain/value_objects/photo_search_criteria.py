"""Photo search criteria value object (B2 搜索/筛选).

归 Domain 值对象——按裁决同 ADR-025 标准：跨用例复用的查询概念、零框架依赖
（DEP-022 dataclass 可用）。各字段均可选，组合后由 ``PhotoRepository.search``
下推到 SQLite WHERE 或 InMemory 内存过滤，对照测试守护一致性。

字段语义：
    person_id: 仅返回此人物相关的照片（JOIN recognition_results on person_id；
        status 轨独立由 match_status 字段约束，不附带 status=APPROVED）
    match_status: 仅返回此审核状态的照片（pending/approved/rejected）；NULL 照片不参与
    captured_from / captured_to: 按拍摄时刻 ``Photo.captured_at`` 区间筛选；
        NULL captured_at 的照片默认排除并文档化（见 PhotoRepository.search 契约）
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

# 从 recognition 子模块直导而非 entities/__init__——避免与 value_objects/__init__
# 反向 import 形成 circular（entities/__init__ 不 import value_objects，但
# value_objects/__init__ 被 domain/__init__ 触发时 entities 尚未就绪）。
from photo_archiver.domain.entities.recognition import MatchStatus


@dataclass(frozen=True, slots=True)
class PhotoSearchCriteria:
    """Criteria for filtering photos across person / status / date range.

    All fields optional; an unset field means "no constraint on this axis".
    Multiple fields combine by AND. The empty criteria (all None) matches
    every photo — equivalent to ``list_all`` but routed through the same
    search contract for UI consistency.

    ``match_status`` semantics over a photo:
        APPROVED  — has ≥1 recognition result with status APPROVED
        REJECTED  — has ≥1 recognition result with status REJECTED
        PENDING   — has ≥1 recognition result with status PENDING
        NULL      — photo with no recognition results at all (handled by
                    a sentinel rather than this enum; see PhotoRepository.search)
    """

    person_id: UUID | None = None
    match_status: MatchStatus | None = None
    captured_from: datetime | None = None
    captured_to: datetime | None = None
