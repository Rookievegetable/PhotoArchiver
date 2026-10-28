"""Command for starting a face clustering run（阶段 D 第一阶段）."""

from dataclasses import dataclass, field
from uuid import UUID

from photo_archiver.domain import FaceCountRange
from photo_archiver.domain.services.face_clustering import (
    ALGORITHM_VERSION,
    DEFAULT_CLUSTER_SIM_THRESHOLD,
    DEFAULT_CONSISTENCY_THRESHOLD,
    DEFAULT_LOW_QUALITY_THRESHOLD,
)

# 数据集口径（任务书 §3 A2/D5）：library=全库最新特征（跨运行 latest wins）；
# single_run=仅锚点运行观测（历史行为）。常量定义于命令层（快照契约的载体），
# 读侧 resolver（application.services.cluster_dataset）反向引用。
DATASET_LIBRARY = "library"
DATASET_SINGLE_RUN = "single_run"


@dataclass(frozen=True, slots=True)
class StartClusteringRunCommand:
    """Request one clustering execution over a feature dataset.

    阈值默认值取自 owner 批准的执行计划 §D-2（0.5 / 0.4，F 阶段校准）；
    ``low_quality_threshold`` 默认 0.0 即禁用低质量档（quality 公式 F 阶段
    校准后改参启用）。阈值比较在余弦域 [-1, 1]；非负校验同时保证成员
    ``confidence``（归属证据相似度）恒在 [0, 1] 实体约束内。

    任务书 §3（扫描即识别拆分）新增两个维度：

    - ``dataset``：``library`` = 全库最新特征（跨运行按照片 latest wins），
      ``single_run`` = 仅锚点运行观测（历史行为，缺省保持测试/调用兼容）；
      快照记入 ``parameters`` 供读侧同口径组装。
    - ``selected_ranges``：脸数档位（任务书 D2）——参与聚类的观测按
      ``classify_scope(photo_face_count, ranges)`` 现算判定，取代"读存储
      scope_verdict"；缺省 ``(1, None)``（全部有脸照片）保持历史调用兼容，
      UI 侧按裁决显式传 [1]。
    """

    recognition_run_id: UUID
    cluster_sim_threshold: float = DEFAULT_CLUSTER_SIM_THRESHOLD
    consistency_threshold: float = DEFAULT_CONSISTENCY_THRESHOLD
    low_quality_threshold: float = DEFAULT_LOW_QUALITY_THRESHOLD
    dataset: str = DATASET_SINGLE_RUN
    selected_ranges: tuple[FaceCountRange, ...] = field(
        default_factory=lambda: (FaceCountRange(1, None),),
    )

    def __post_init__(self) -> None:
        """Validate the threshold ranges (cosine domain, non-negative)."""
        for name in ("cluster_sim_threshold", "consistency_threshold", "low_quality_threshold"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0.0, 1.0], got {value}")
        if self.dataset not in (DATASET_LIBRARY, DATASET_SINGLE_RUN):
            raise ValueError(f"unknown dataset: {self.dataset}")
        if not self.selected_ranges:
            raise ValueError("selected_ranges must contain at least one range")
        object.__setattr__(self, "selected_ranges", tuple(self.selected_ranges))

    def parameters(self) -> dict[str, object]:
        """Return the immutable parameter snapshot persisted with the cluster run."""
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "cluster_sim_threshold": self.cluster_sim_threshold,
            "consistency_threshold": self.consistency_threshold,
            "low_quality_threshold": self.low_quality_threshold,
            "dataset": self.dataset,
            "scope_filter": "face_count_ranges",
            "face_count_ranges": [str(face_range) for face_range in self.selected_ranges],
        }
