"""Face observation entity — 一次 run 中一张照片一张脸的检测记录（阶段 C）.

硬性约束落点（owner 任务书阶段 C）：

- 一张照片检测到 N 张脸，就保存 N 条 Observation（约束 3）；0 脸与不可读
  照片不建 Observation（约束 8/9），由 run 级 no_face / unreadable 统计覆盖。
- ``scope_verdict`` 是**照片级范围判断**（C-SEM-2）——同一照片的全部
  Observation 共享同一 verdict，由 ``classify_scope()`` 在检测之后计算
  （约束 5），范围外照片仍完整保存全部 Observation（约束 7）。
- ``face_index`` 确定性：det_score 降序、同分按 bbox ``(x1,y1,x2,y2)``
  字典序——同一输入重跑结果可确定。
- 实体不可变（frozen）；仓储经正常构造器重建，不用 ``__new__`` 反射。
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.value_objects import FaceBox, FaceCountRange, FaceEmbedding

SCOPE_VERDICT_IN_SELECTED_SCOPE = "in_selected_scope"
SCOPE_VERDICT_OUT_OF_SELECTED_SCOPE = "out_of_selected_scope"
SCOPE_VERDICTS = frozenset(
    {SCOPE_VERDICT_IN_SELECTED_SCOPE, SCOPE_VERDICT_OUT_OF_SELECTED_SCOPE}
)


@dataclass(frozen=True, slots=True)
class FaceObservation:
    """One detected face of one photo within one recognition run (immutable).

    ``photo_face_count`` 冗余存储所属照片在本 run 中检测到的总人脸数，
    使每条 Observation 自带范围判定上下文（C-SEM-2）；``face_index`` 是
    该照片内的确定性序号（0 ≤ face_index < photo_face_count）。
    """

    run_id: UUID
    photo_id: UUID
    face_index: int
    photo_face_count: int
    det_score: float
    box: FaceBox
    embedding: FaceEmbedding
    scope_verdict: str
    quality_score: float | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        """Validate observation invariants."""
        if self.face_index < 0:
            raise ValidationError("FaceObservation face_index must be >= 0")
        if self.photo_face_count < 1:
            raise ValidationError("FaceObservation photo_face_count must be >= 1")
        if self.face_index >= self.photo_face_count:
            raise ValidationError("FaceObservation face_index must be < photo_face_count")
        if not 0.0 <= self.det_score <= 1.0:
            raise ValidationError("FaceObservation det_score must be in [0.0, 1.0]")
        if self.quality_score is not None and not 0.0 <= self.quality_score <= 1.0:
            raise ValidationError("FaceObservation quality_score must be in [0.0, 1.0]")
        if self.scope_verdict not in SCOPE_VERDICTS:
            raise ValidationError(
                f"Unknown FaceObservation scope_verdict: {self.scope_verdict}"
            )


def classify_scope(photo_face_count: int, selected_ranges: Sequence[FaceCountRange]) -> str:
    """Return the photo-level scope verdict for a detected face count (C-SEM-2).

    照片人脸数命中任一选中范围即 ``in_selected_scope``，否则
    ``out_of_selected_scope``。同一照片的全部 Observation 必须共享本
    返回值——不得出现同一照片部分脸 in-scope、部分脸 out-of-scope。

    仅对检出人脸的照片调用：0 脸照片不建 Observation（约束 8），由 run
    级 no_face 统计覆盖，不属于本函数的定义域。
    """
    if photo_face_count < 1:
        raise ValidationError("classify_scope requires photo_face_count >= 1")
    if not selected_ranges:
        raise ValidationError("classify_scope requires at least one selected range")
    if any(face_range.contains(photo_face_count) for face_range in selected_ranges):
        return SCOPE_VERDICT_IN_SELECTED_SCOPE
    return SCOPE_VERDICT_OUT_OF_SELECTED_SCOPE
