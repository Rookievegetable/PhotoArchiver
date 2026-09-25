"""Command for starting a face clustering run（阶段 D 第一阶段）."""

from dataclasses import dataclass
from uuid import UUID

from photo_archiver.domain.services.face_clustering import (
    ALGORITHM_VERSION,
    DEFAULT_CLUSTER_SIM_THRESHOLD,
    DEFAULT_CONSISTENCY_THRESHOLD,
    DEFAULT_LOW_QUALITY_THRESHOLD,
)


@dataclass(frozen=True, slots=True)
class StartClusteringRunCommand:
    """Request one clustering execution over one recognition run's observations.

    阈值默认值取自 owner 批准的执行计划 §D-2（0.5 / 0.4，F 阶段校准）；
    ``low_quality_threshold`` 默认 0.0 即禁用低质量档（quality 公式 F 阶段
    校准后改参启用）。阈值比较在余弦域 [-1, 1]；非负校验同时保证成员
    ``confidence``（归属证据相似度）恒在 [0, 1] 实体约束内。
    """

    recognition_run_id: UUID
    cluster_sim_threshold: float = DEFAULT_CLUSTER_SIM_THRESHOLD
    consistency_threshold: float = DEFAULT_CONSISTENCY_THRESHOLD
    low_quality_threshold: float = DEFAULT_LOW_QUALITY_THRESHOLD

    def __post_init__(self) -> None:
        """Validate the threshold ranges (cosine domain, non-negative)."""
        for name in ("cluster_sim_threshold", "consistency_threshold", "low_quality_threshold"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0.0, 1.0], got {value}")

    def parameters(self) -> dict[str, object]:
        """Return the immutable parameter snapshot persisted with the cluster run."""
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "cluster_sim_threshold": self.cluster_sim_threshold,
            "consistency_threshold": self.consistency_threshold,
            "low_quality_threshold": self.low_quality_threshold,
            "scope_filter": "in_selected_scope",
        }
