"""Recognition run aggregate — 一次识别执行的可追溯容器（阶段 C）.

owner 任务书阶段 C（多脸检测、识别范围选择与可重跑）Commit 1 数据地基：

- 重跑 = 新 ``RecognitionRun``——每次执行新建一行，不覆盖旧 run（C-SEM-1）。
- 生命周期：created → running → completed / failed / cancelled，终态不可回退。
- ``parameters`` 是**运行开始时确定且不可变的配置快照**（C-SEM-3）：
  detector/model 标识、质量分公式版本等。运行结果统计（faces / unreadable /
  no_face / in_scope / out_of_scope）属运行结果，写入独立统计列——
  实体不提供修改 parameters 的方法，仓储 ``update_run`` 也不更新该列。
- ``RunPhotoSnapshot`` 记录 run 创建时的处理输入快照（C-SEM-4）；
  照片删除时按 FK CASCADE 一并删除，不为绕过照片删除而永久保存。
"""

from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from photo_archiver.domain.exceptions import ValidationError

RUN_STATUS_CREATED = "created"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_CANCELLED = "cancelled"

RUN_STATUSES = frozenset(
    {
        RUN_STATUS_CREATED,
        RUN_STATUS_RUNNING,
        RUN_STATUS_COMPLETED,
        RUN_STATUS_FAILED,
        RUN_STATUS_CANCELLED,
    }
)
_TERMINAL_RUN_STATUSES = frozenset(
    {RUN_STATUS_COMPLETED, RUN_STATUS_FAILED, RUN_STATUS_CANCELLED}
)
_ALLOWED_RUN_TRANSITIONS = {
    RUN_STATUS_CREATED: frozenset({RUN_STATUS_RUNNING}),
    RUN_STATUS_RUNNING: _TERMINAL_RUN_STATUSES,
}


@dataclass(frozen=True, slots=True)
class RecognitionRunStats:
    """运行结果统计——与 parameters 配置快照分离的独立结构（C-SEM-3）.

    五个计数器对应任务书 Summary 字段：faces / unreadable / no_face /
    error / in_scope / out_of_scope（processed 由仓储按 run_photos 快照求得，
    不重复存储）。仅允许非负整数。
    """

    face_count: int = 0
    unreadable_count: int = 0
    no_face_count: int = 0
    error_count: int = 0
    in_scope_photo_count: int = 0
    out_of_scope_photo_count: int = 0

    def __post_init__(self) -> None:
        """Validate that every counter is non-negative."""
        for field_name in (
            "face_count",
            "unreadable_count",
            "no_face_count",
            "error_count",
            "in_scope_photo_count",
            "out_of_scope_photo_count",
        ):
            if getattr(self, field_name) < 0:
                raise ValidationError(f"RecognitionRunStats {field_name} must be >= 0")


@dataclass(slots=True)  # NOT frozen: start()/complete()/fail()/cancel() 迁移状态
class RecognitionRun:
    """One recognition execution over a chosen photo scope.

    ``parameters`` 为创建时写入的不可变配置快照（C-SEM-3）——本实体刻意
    不提供任何修改入口；统计结果只能经 ``RecognitionRunStats`` 在
    完成/失败/取消时写入独立计数字段。
    """

    parameters: dict[str, Any] = field(default_factory=dict)
    status: str = RUN_STATUS_CREATED
    id: UUID | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    face_count: int = 0
    unreadable_count: int = 0
    no_face_count: int = 0
    error_count: int = 0
    in_scope_photo_count: int = 0
    out_of_scope_photo_count: int = 0

    def __post_init__(self) -> None:
        """Initialize generated values and validate the status word."""
        if self.id is None:
            self.id = uuid4()
        if self.created_at is None:
            self.created_at = datetime.now()
        object.__setattr__(self, "parameters", MappingProxyType(deepcopy(dict(self.parameters))))
        if self.status not in RUN_STATUSES:
            raise ValidationError(f"Unknown RecognitionRun status: {self.status}")

    def start(self) -> None:
        """Move the run from created to running."""
        self._transition_to(RUN_STATUS_RUNNING)

    def complete(self, stats: RecognitionRunStats) -> None:
        """Finish the run successfully and record the final statistics."""
        self._transition_to(RUN_STATUS_COMPLETED)
        self._apply_stats(stats)
        self.finished_at = datetime.now()

    def fail(
        self, error: str | None = None, stats: RecognitionRunStats | None = None
    ) -> None:
        """Finish the run with an unrecoverable error.

        已 flush 的 Observation 不因失败而人为清空；``stats`` 可携带失败前
        已处理部分的结果统计（缺省保持当前计数）。
        """
        self._transition_to(RUN_STATUS_FAILED)
        if stats is not None:
            self._apply_stats(stats)
        self.error = error
        self.finished_at = datetime.now()

    def cancel(self, stats: RecognitionRunStats | None = None) -> None:
        """Mark the run as cancelled by the user; flushed data is kept."""
        self._transition_to(RUN_STATUS_CANCELLED)
        if stats is not None:
            self._apply_stats(stats)
        self.finished_at = datetime.now()

    def _apply_stats(self, stats: RecognitionRunStats) -> None:
        """Copy the statistics counters onto the run."""
        self.face_count = stats.face_count
        self.unreadable_count = stats.unreadable_count
        self.no_face_count = stats.no_face_count
        self.error_count = stats.error_count
        self.in_scope_photo_count = stats.in_scope_photo_count
        self.out_of_scope_photo_count = stats.out_of_scope_photo_count

    def _transition_to(self, target: str) -> None:
        """Transition to ``target``, enforcing 终态不可回退."""
        if self.status in _TERMINAL_RUN_STATUSES:
            raise ValidationError(f"RecognitionRun already finalized as {self.status}")
        if target not in _ALLOWED_RUN_TRANSITIONS.get(self.status, frozenset()):
            raise ValidationError(
                f"RecognitionRun cannot transition from {self.status} to {target}"
            )
        self.status = target


@dataclass(frozen=True, slots=True)
class RunPhotoSnapshot:
    """run 创建时的照片处理输入快照（C-SEM-4）.

    仅记录 run 启动时刻的处理输入（路径 / 拍摄时刻）——不是为绕过照片
    删除而永久保存 Observation；照片删除时本快照按 FK CASCADE 一并删除。
    """

    run_id: UUID
    photo_id: UUID
    raw_path: str
    captured_at: datetime | None = None
