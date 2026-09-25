"""Face cluster aggregates — 人物聚类容器与成员关系（阶段 D 第一阶段）.

owner 裁决（2026-09-25，两段式 + 低质量阈值默认禁用）落点的数据地基：

- ``FaceClusterRun``：一次聚类执行的可追溯容器，镜像 ``RecognitionRun``
  生命周期（created → running → completed / failed / cancelled，终态不可
  回退）。同一 recognition run 可重复聚类——每次执行新开一个 cluster
  run，历史 cluster set 原样保留（重跑不覆盖）。``parameters`` 是执行
  开始时的不可变参数快照（算法版本、三阈值、scope_filter）；聚类结果
  统计写独立列，不混入 parameters。
- ``FaceCluster``：同一人物的一组人脸（**不是** Person——自动认定属
  Stage E）。``status`` 六态按方案 §3.2 定义，本阶段只产生 ``pending``；
  ``ordinal``/``sort_key``/``first_captured_at`` 是方案 §D-3 的稳定排序
  字段（最早非空 captured_at 升序、无时间排末、路径键稳定）。
- ``FaceClusterMember``：Cluster ↔ Observation 的可追溯归属
  （``source=auto`` 为算法自动归属，``manual`` 预留人工合并/拆分）；
  ``confidence`` 是归属证据相似度（seed=1.0，入簇=簇心相似度，并簇=
  跨簇两两最小相似度）。同一观测在同一 cluster run 内至多归属一个
  cluster（算法保证 + 服务层校验）。
"""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from photo_archiver.domain.exceptions import ValidationError

CLUSTER_RUN_STATUS_CREATED = "created"
CLUSTER_RUN_STATUS_RUNNING = "running"
CLUSTER_RUN_STATUS_COMPLETED = "completed"
CLUSTER_RUN_STATUS_FAILED = "failed"
CLUSTER_RUN_STATUS_CANCELLED = "cancelled"

CLUSTER_RUN_STATUSES = frozenset(
    {
        CLUSTER_RUN_STATUS_CREATED,
        CLUSTER_RUN_STATUS_RUNNING,
        CLUSTER_RUN_STATUS_COMPLETED,
        CLUSTER_RUN_STATUS_FAILED,
        CLUSTER_RUN_STATUS_CANCELLED,
    }
)
_TERMINAL_CLUSTER_RUN_STATUSES = frozenset(
    {CLUSTER_RUN_STATUS_COMPLETED, CLUSTER_RUN_STATUS_FAILED, CLUSTER_RUN_STATUS_CANCELLED}
)
_ALLOWED_CLUSTER_RUN_TRANSITIONS = {
    CLUSTER_RUN_STATUS_CREATED: frozenset({CLUSTER_RUN_STATUS_RUNNING}),
    CLUSTER_RUN_STATUS_RUNNING: _TERMINAL_CLUSTER_RUN_STATUSES,
}

CLUSTER_STATUS_PENDING = "pending"
CLUSTER_STATUS_CONFIRMED = "confirmed"
CLUSTER_STATUS_UNKNOWN = "unknown"
CLUSTER_STATUS_IGNORED = "ignored"
CLUSTER_STATUS_SPLIT = "split"
CLUSTER_STATUS_MERGED = "merged"
CLUSTER_STATUSES = frozenset(
    {
        CLUSTER_STATUS_PENDING,
        CLUSTER_STATUS_CONFIRMED,
        CLUSTER_STATUS_UNKNOWN,
        CLUSTER_STATUS_IGNORED,
        CLUSTER_STATUS_SPLIT,
        CLUSTER_STATUS_MERGED,
    }
)

MEMBER_SOURCE_AUTO = "auto"
MEMBER_SOURCE_MANUAL = "manual"
MEMBER_SOURCES = frozenset({MEMBER_SOURCE_AUTO, MEMBER_SOURCE_MANUAL})


@dataclass(slots=True)  # NOT frozen: start()/complete()/fail()/cancel() 迁移状态
class FaceClusterRun:
    """One clustering execution over one recognition run's observations."""

    recognition_run_id: UUID
    algorithm_version: str
    parameters: dict[str, Any] = field(default_factory=dict)
    status: str = CLUSTER_RUN_STATUS_CREATED
    id: UUID | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    cluster_count: int = 0
    member_count: int = 0
    excluded_count: int = 0

    def __post_init__(self) -> None:
        """Initialize generated values and validate status / algorithm version."""
        if not self.algorithm_version:
            raise ValidationError("FaceClusterRun algorithm_version must not be empty")
        if self.id is None:
            self.id = uuid4()
        if self.created_at is None:
            self.created_at = datetime.now()
        object.__setattr__(self, "parameters", MappingProxyType(deepcopy(dict(self.parameters))))
        if self.status not in CLUSTER_RUN_STATUSES:
            raise ValidationError(f"Unknown FaceClusterRun status: {self.status}")

    def start(self) -> None:
        """Move the run from created to running."""
        self._transition_to(CLUSTER_RUN_STATUS_RUNNING)

    def complete(self, cluster_count: int, member_count: int, excluded_count: int) -> None:
        """Finish the run successfully and record the result statistics."""
        self._transition_to(CLUSTER_RUN_STATUS_COMPLETED)
        self.cluster_count = cluster_count
        self.member_count = member_count
        self.excluded_count = excluded_count
        self.finished_at = datetime.now()

    def fail(self, error: str | None = None) -> None:
        """Finish the run with an unrecoverable error."""
        self._transition_to(CLUSTER_RUN_STATUS_FAILED)
        self.error = error
        self.finished_at = datetime.now()

    def cancel(
        self,
        cluster_count: int | None = None,
        member_count: int | None = None,
        excluded_count: int | None = None,
    ) -> None:
        """Mark the run as cancelled; already-persisted clusters are kept.

        计数参数缺省保持当前值——算法阶段取消无落库数据（保持 0），
        持久化后取消则携带已落库规模。
        """
        self._transition_to(CLUSTER_RUN_STATUS_CANCELLED)
        if cluster_count is not None:
            self.cluster_count = cluster_count
        if member_count is not None:
            self.member_count = member_count
        if excluded_count is not None:
            self.excluded_count = excluded_count
        self.finished_at = datetime.now()

    def _transition_to(self, target: str) -> None:
        """Transition to ``target``, enforcing 终态不可回退."""
        if self.status in _TERMINAL_CLUSTER_RUN_STATUSES:
            raise ValidationError(f"FaceClusterRun already finalized as {self.status}")
        if target not in _ALLOWED_CLUSTER_RUN_TRANSITIONS.get(self.status, frozenset()):
            raise ValidationError(
                f"FaceClusterRun cannot transition from {self.status} to {target}"
            )
        self.status = target


@dataclass(slots=True)
class FaceCluster:
    """One person group produced by one cluster run（不等于 Person）."""

    cluster_run_id: UUID
    run_id: UUID
    ordinal: int
    member_count: int
    sort_key: str
    status: str = CLUSTER_STATUS_PENDING
    first_captured_at: datetime | None = None
    id: UUID | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate invariants (status vocabulary, ordinal, member count)."""
        if self.id is None:
            self.id = uuid4()
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.status not in CLUSTER_STATUSES:
            raise ValidationError(f"Unknown FaceCluster status: {self.status}")
        if self.ordinal < 0:
            raise ValidationError("FaceCluster ordinal must be >= 0")
        if self.member_count < 1:
            raise ValidationError("FaceCluster member_count must be >= 1")
        if not self.sort_key:
            raise ValidationError("FaceCluster sort_key must not be empty")


@dataclass(frozen=True, slots=True)
class FaceClusterMember:
    """Traceable Cluster ↔ Observation membership with its evidence confidence."""

    cluster_id: UUID
    observation_id: UUID
    source: str = MEMBER_SOURCE_AUTO
    confidence: float = 1.0
    id: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate source vocabulary and the confidence bound."""
        if self.source not in MEMBER_SOURCES:
            raise ValidationError(f"Unknown FaceClusterMember source: {self.source}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValidationError("FaceClusterMember confidence must be in [0.0, 1.0]")
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
