"""S1-F 审核身份决策命令契约."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ConfirmReviewDecisionCommand:
    """审核中心「通过」的人类身份决策请求。

    ``result_id`` 是被批准的识别期 pending 占位行（复用为投影载体，D-3）；
    ``photo_id`` / ``person_id`` 是该决策的业务锚点。
    """

    result_id: UUID
    photo_id: UUID
    person_id: UUID
    cluster_id: UUID | None = None
    """决策锚点簇（S1-F 语义修正）。

    照片在最新聚类代际中只有一个簇时可为 None（自动定锚）；多簇合影必须显式
    指定，否则抛 :class:`ReviewAnchorAmbiguousError`（fail-closed，禁止 Top-1
    det_score 之类的隐藏猜测规则）。
    """
