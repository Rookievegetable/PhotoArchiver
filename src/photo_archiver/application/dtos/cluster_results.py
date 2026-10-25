"""Cluster results read DTOs — D-4 聚类结果展示的只读视图.

全部字段来自持久化的 ``FaceClusterRun → FaceCluster → FaceClusterMember →
FaceObservation``（+ run_photos 快照的照片路径/拍摄时间），不含任何人员
归属信息——Person assignment 属 Stage E，展示层无此数据。
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from photo_archiver.domain import FaceClusterRun


@dataclass(frozen=True, slots=True)
class ClusterMemberDetail:
    """One cluster member rendered from persisted observation + snapshot data."""

    observation_id: UUID
    cluster_id: UUID
    photo_id: UUID | None
    photo_path: str
    face_index: int
    det_score: float
    confidence: float
    quality_score: float | None = None
    captured_at: datetime | None = None
    photo_face_count: int = 1
    # 界面优化 §6.3：照片级处理结果（历史 run 为 None=未知，不伪造 0 脸）。
    photo_outcome: str | None = None


@dataclass(frozen=True, slots=True)
class ClusterDetailView:
    """One cluster of one generation with its ordered member details."""

    cluster_id: UUID
    ordinal: int
    status: str
    member_count: int
    first_captured_at: datetime | None
    members: tuple[ClusterMemberDetail, ...]
    photo_count: int = 0
    # 界面优化 §5.2/§5.3：照片数 = 簇内不同照片数（按 photo_id 去重）。
    ignored_photo_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class ClusterRunResults:
    """One generation's full read view: the run row plus its clusters."""

    cluster_run: FaceClusterRun
    clusters: tuple[ClusterDetailView, ...]
