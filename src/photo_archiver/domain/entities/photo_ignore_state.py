"""Photo ignore state entity — 界面优化：照片级忽略（FaceClusterRun + photo_id）.

Owner 冻结基线（§3.1）：

- 忽略对象是**一张照片在一个聚类代际内的参与资格**，不是簇、不是人员
  配对，也不代表照片异常。
- 状态跨应用重启持久保留，直到用户显式恢复（删除状态行）。
- 不自动修改其他聚类代际中的忽略状态——作用域键
  ``(cluster_run_id, photo_id)`` 由 UNIQUE 约束强制。
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class PhotoIgnoreState:
    """One photo's ignore record within one clustering generation."""

    cluster_run_id: UUID
    photo_id: UUID
    id: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        """Initialize generated values."""
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
