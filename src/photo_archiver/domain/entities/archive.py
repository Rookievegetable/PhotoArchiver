"""Archive record entity — persisted outcome of one archive operation."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from photo_archiver.domain.exceptions import ValidationError


class ArchiveStatus(str, Enum):
    """Lifecycle states for one archived photo.

    Inheriting from ``str`` keeps the enum JSON-serializable without extra
    adapters, matching the convention used by ``MatchStatus`` in
    ``recognition.py``. SQLite persistence in Step 11 stores these values
    verbatim in the ``archive_records`` table.
    """

    PLANNED = "planned"      # ArchivePlan 已生成，Executor 尚未执行
    ARCHIVED = "archived"    # copy/move 成功落盘
    SKIPPED = "skipped"      # conflict_strategy=skip 且目标已存在
    RENAMED = "renamed"      # conflict_strategy=rename 触发了重命名
    OVERWRITTEN = "overwritten"  # conflict_strategy=overwrite 覆盖了既有文件
    DRY_RUN = "dry_run"      # dry-run 模式只 log 不落盘
    FAILED = "failed"        # 文件系统异常（权限 / 源缺失 / IO 错）


@dataclass(slots=True)
class ArchiveRecord:
    """Represent the persisted outcome of archiving one photo.

    One ``ArchiveRecord`` ties one ``Photo`` to the target ``ArchivePath``
    (以纯字符串段形式持，避免在 Domain 持 PurePath 这种 pathlib 类型)
    plus a ``status`` plus an optional ``error`` message. The aggregate is
    created in the ``PLANNED`` state by ArchivePlanner and transitioned by
    ArchiveExecutor as the file operation completes.

    Fragility note: ``target_*`` 字段拆段存储以保持 Domain 零 pathlib.Path 依赖，
    与 ``ArchivePath`` 值对象一一对应；SQLite mapper 必须按序落七列。
    """

    photo_id: UUID
    target_archive_root: str
    target_person_name: str
    target_event_or_date: str
    target_original_name: str
    status: ArchiveStatus
    id: UUID | None = None
    archived_at: datetime | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        """Validate fields and initialize generated values."""
        if not isinstance(self.status, ArchiveStatus):
            raise ValidationError("ArchiveRecord status must be an ArchiveStatus enum")
        for name, value in {
            "target_archive_root": self.target_archive_root,
            "target_person_name": self.target_person_name,
            "target_event_or_date": self.target_event_or_date,
            "target_original_name": self.target_original_name,
        }.items():
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"ArchiveRecord {name} must not be empty")
        if self.id is None:
            self.id = uuid4()
        if self.archived_at is None and self.status is ArchiveStatus.PLANNED:
            # PLANNED 状态是规划阶段，尚无落盘时刻；其余状态由 Executor 显式设。
            pass
        if self.error is not None:
            normalized = self.error.strip()
            self.error = normalized or None

    def mark_archived(self) -> None:
        """Transition to ARCHIVED with a current timestamp."""
        self._assert_executable_state()
        self.status = ArchiveStatus.ARCHIVED
        self.archived_at = datetime.now()
        self.error = None

    def mark_skipped(self) -> None:
        """Transition to SKIPPED — target already existed, conflict_strategy=skip."""
        self._assert_executable_state()
        self.status = ArchiveStatus.SKIPPED
        self.archived_at = datetime.now()
        self.error = None

    def mark_renamed(self) -> None:
        """Transition to RENAMED — conflict_strategy=rename produced a sibling name."""
        self._assert_executable_state()
        self.status = ArchiveStatus.RENAMED
        self.archived_at = datetime.now()
        self.error = None

    def mark_overwritten(self) -> None:
        """Transition to OVERWRITTEN — conflict_strategy=overwrite replaced target."""
        self._assert_executable_state()
        self.status = ArchiveStatus.OVERWRITTEN
        self.archived_at = datetime.now()
        self.error = None

    def mark_dry_run(self) -> None:
        """Transition to DRY_RUN — no filesystem operation performed."""
        self._assert_executable_state()
        self.status = ArchiveStatus.DRY_RUN
        self.archived_at = datetime.now()
        self.error = None

    def mark_failed(self, error: str) -> None:
        """Transition to FAILED with the captured error message.

        Args:
            error: The filesystem or persistence error that prevented archive.
        """
        self._assert_executable_state()
        normalized = error.strip()
        if not normalized:
            raise ValidationError("ArchiveRecord FAILED transition requires a non-empty error")
        self.status = ArchiveStatus.FAILED
        self.archived_at = datetime.now()
        self.error = normalized

    def _assert_executable_state(self) -> None:
        """Raise if the record has already been finalized by the Executor.

        Once ArchiveExecutor transitions a record past PLANNED, it cannot be
        re-transitioned — this keeps the per-photo archive outcome honest
        under retries (a second run should plan a fresh record rather than
        mutate the historical one).
        """
        if self.status is not ArchiveStatus.PLANNED:
            raise ValidationError(
                f"ArchiveRecord already finalized as {self.status.value}"
            )
