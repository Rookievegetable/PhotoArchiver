"""DTOs for the deletion management workflow (Phase E E-3, ADR-034).

删除管理四个用例（照片删除 / 人员删除 / 失联清理 / 重复处置）的预览与结果
DTO。ADR-034 通用裁决：**删除必经确认流**——``preview()`` 产级联计数预览
供确认对话框展示，``execute()`` 仅在调用方确认后执行。计数语义：

- 照片删除：``recognition_count`` / ``archive_count`` = 随照片删除被外键
  CASCADE 清除的行数（D1）；
- 人员删除：``embedding_count`` = 随删 CASCADE 的人脸嵌入数；
  ``recognition_count`` = 归属将被置空（行保留，D2）的识别结果数。

预览计数走 ``list_by_photo_ids`` 批量下推（E-2 既有 Protocol 方法），无 N+1、
无 SQL——Application 层零 SQL（DEP-012/013）。
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PhotoDeletionPreview:
    """Confirmation preview for deleting photos from the registry (D1).

    photo_ids: Deduplicated ids that exist in the library and will be removed.
    missing_ids: Requested ids absent from the library (idempotent no-ops).
    recognition_count: Recognition rows the FK will CASCADE away.
    archive_count: Archive record rows the FK will CASCADE away.
    """

    photo_ids: tuple[UUID, ...]
    missing_ids: tuple[UUID, ...]
    recognition_count: int
    archive_count: int

    @property
    def photo_count(self) -> int:
        """Return how many photos will be removed."""
        return len(self.photo_ids)

    @property
    def missing_count(self) -> int:
        """Return how many requested ids were not found (idempotent part)."""
        return len(self.missing_ids)

    @property
    def cascade_count(self) -> int:
        """Return the total number of rows cascaded away with the photos."""
        return self.recognition_count + self.archive_count

    @property
    def is_empty(self) -> bool:
        """Return whether there is nothing to delete."""
        return not self.photo_ids


@dataclass(frozen=True, slots=True)
class PhotoDeletionResult:
    """Outcome of a confirmed photo deletion run.

    ``recognition_cascade`` / ``archive_cascade`` carry the preview-computed
    cascade counts: after the delete the cascaded rows no longer exist, so the
    preview snapshot is the authoritative audit figure (loguru 审计行引用同值).
    """

    requested: int
    removed: int
    missing: int
    recognition_cascade: int
    archive_cascade: int

    @property
    def succeeded(self) -> bool:
        """Return whether every requested id was either removed or absent."""
        return self.removed + self.missing == self.requested


@dataclass(frozen=True, slots=True)
class PersonDeletionPreview:
    """Confirmation preview for deleting people from the registry (D2).

    Photos are NEVER removed by person deletion (D2: 人员是归属维度) — the
    preview therefore has no photo count. ``recognition_count`` is the number
    of recognition rows that stay but lose their person attribution (SET NULL
    → "未知人员"), NOT rows being deleted.

    ``assignment_count`` / ``sample_count``（界面优化 P2）：该人员的身份决策行
    与多样本库行数——两者均按外键 CASCADE 随人员删除，确认流必须如实披露。
    """

    person_ids: tuple[UUID, ...]
    missing_ids: tuple[UUID, ...]
    embedding_count: int
    recognition_count: int
    assignment_count: int = 0
    sample_count: int = 0

    @property
    def person_count(self) -> int:
        """Return how many people will be removed."""
        return len(self.person_ids)

    @property
    def missing_count(self) -> int:
        """Return how many requested ids were not found (idempotent part)."""
        return len(self.missing_ids)

    @property
    def is_empty(self) -> bool:
        """Return whether there is nothing to delete."""
        return not self.person_ids


@dataclass(frozen=True, slots=True)
class PersonDeletionResult:
    """Outcome of a confirmed person deletion run."""

    requested: int
    removed: int
    missing: int
    embedding_cascade: int
    recognition_orphaned: int
    assignment_cascade: int = 0
    sample_cascade: int = 0

    @property
    def succeeded(self) -> bool:
        """Return whether every requested id was either removed or absent."""
        return self.removed + self.missing == self.requested
@dataclass(frozen=True, slots=True)
class MissingPhotoItem:
    """One registry entry whose disk file is gone (D5 失联登记).

    disk_path: The resolved absolute path the registry expects the file at —
    surfaced so the user can double-check the file is really gone (e.g. an
    unmounted drive) before confirming the prune.
    """

    photo_id: UUID
    disk_path: Path


@dataclass(frozen=True, slots=True)
class PruneMissingPreview:
    """Preview of registry entries whose files are missing on disk (D5).

    scanned: Total photos in the library.
    items: Missing-on-disk entries eligible for pruning.
    unresolvable: Photos whose registered path cannot be resolved against the
        filesystem (relative path without a photo root, PROJECT_ROOT base) —
        they are conservatively NEVER treated as missing.
    """

    scanned: int
    items: tuple[MissingPhotoItem, ...]
    unresolvable: int

    @property
    def missing_count(self) -> int:
        """Return how many registry entries are missing on disk."""
        return len(self.items)

    @property
    def is_empty(self) -> bool:
        """Return whether nothing is missing."""
        return not self.items


@dataclass(frozen=True, slots=True)
class PruneMissingResult:
    """Outcome of a confirmed prune-missing run."""

    scanned: int
    missing: int
    requested: int
    pruned: int
    rejected: int
    unresolvable: int

    @property
    def succeeded(self) -> bool:
        """Return whether every requested id was pruned or explicitly rejected."""
        return self.pruned + self.rejected == self.requested


@dataclass(frozen=True, slots=True)
class DuplicateDisposalGroup:
    """One duplicate group with its disposal proposal (D6).

    keep_photo_id: The surviving registration — earliest ``created_at`` with
        ``id`` as the deterministic tiebreak (ADR-034 D6).
    remove_photo_ids: The other group members proposed for registry deletion.
    recognition_count / archive_count: Cascade rows the removal will take.
    """

    content_hash: str
    keep_photo_id: UUID
    remove_photo_ids: tuple[UUID, ...]
    recognition_count: int
    archive_count: int

    @property
    def remove_count(self) -> int:
        """Return how many registrations this group proposes to remove."""
        return len(self.remove_photo_ids)


@dataclass(frozen=True, slots=True)
class DuplicateDisposalPreview:
    """Preview of the duplicate disposal proposal over all duplicate groups."""

    groups: tuple[DuplicateDisposalGroup, ...]

    @property
    def group_count(self) -> int:
        """Return the number of duplicate groups."""
        return len(self.groups)

    @property
    def photo_count(self) -> int:
        """Return the total registrations proposed for removal."""
        return sum(group.remove_count for group in self.groups)

    @property
    def recognition_count(self) -> int:
        """Return the total recognition rows the proposal would cascade."""
        return sum(group.recognition_count for group in self.groups)

    @property
    def archive_count(self) -> int:
        """Return the total archive rows the proposal would cascade."""
        return sum(group.archive_count for group in self.groups)

    @property
    def is_empty(self) -> bool:
        """Return whether there are no duplicate groups."""
        return not self.groups


@dataclass(frozen=True, slots=True)
class DuplicateDisposalResult:
    """Outcome of a confirmed duplicate disposal run."""

    requested: int
    removed: int
    rejected: int
    groups_affected: int



@dataclass(frozen=True, slots=True)
class BatchRosterDeletionPreview:
    """Confirmation preview for deleting one import batch's people（§4.3）.

    people: The batch's *current* members at preview time (name + id for the
    explicit list display). ``merge_note`` reflects that merged people may
    have been re-attributed to this batch by later imports.
    batch_record_found / draft_row_count: Present only when the optional
    batch-record cleanup is being considered.
    """

    person_ids: tuple[UUID, ...]
    people_names: tuple[str, ...]
    missing_ids: tuple[UUID, ...]
    embedding_count: int
    recognition_count: int
    batch_record_found: bool
    draft_row_count: int
    assignment_count: int = 0
    sample_count: int = 0

    @property
    def person_count(self) -> int:
        """Return how many people will be removed."""
        return len(self.person_ids)

    @property
    def is_empty(self) -> bool:
        """Return whether there is nothing to delete."""
        return not self.person_ids


@dataclass(frozen=True, slots=True)
class BatchRosterDeletionResult:
    """Outcome of a confirmed batch/clear-all people deletion run（§4.3）."""

    requested: int
    removed: int
    missing: int
    embedding_cascade: int
    recognition_orphaned: int
    batch_record_deleted: int
    draft_rows_deleted: int
    assignment_cascade: int = 0
    sample_cascade: int = 0

    @property
    def succeeded(self) -> bool:
        """Return whether every requested id was removed or absent."""
        return self.removed + self.missing == self.requested


# ── 识别运行级删除（批次删除功能 D1~D5） ─────────────────────────────────


@dataclass(frozen=True, slots=True)
class RunPeopleDeletionPreview:
    """删除某识别运行"名单及记录"的确认预览（D2）。

    该运行的"名单"= 其各聚类代际的决策行中出现过的**人员**（执行时点重算）。
    计数口径：

    - ``assignment_count`` / ``sample_count`` / ``embedding_count``：**随人员
      删除被外键 CASCADE 清除**的行数（决策行跨所有代际计数）；
    - ``recognition_count`` / ``archive_count`` / ``ground_truth_count``：
      **行保留但失去人员指向**的行数（SET NULL）；
    - ``blocked_reasons`` 非空时该操作**硬阻断**（D5：归档记录 / GT 裁定 /
      样本库任一非空即拒绝执行——这些证据删掉后无法靠重新识别还原）。
    """

    run_found: bool
    run_created_at: datetime | None
    run_status: str
    cluster_count: int
    decision_count: int
    person_ids: tuple[UUID, ...]
    people_names: tuple[str, ...]
    embedding_count: int
    recognition_count: int
    assignment_count: int
    sample_count: int
    archive_count: int
    ground_truth_count: int
    blocked_reasons: tuple[str, ...] = ()

    @property
    def person_count(self) -> int:
        """Return how many people the run points at."""
        return len(self.person_ids)

    @property
    def is_empty(self) -> bool:
        """Return whether the run points at nobody."""
        return not self.person_ids

    @property
    def is_blocked(self) -> bool:
        """Return whether irrecoverable evidence blocks the deletion."""
        return bool(self.blocked_reasons)


@dataclass(frozen=True, slots=True)
class RunPeopleDeletionResult:
    """确认后的运行级名单删除结果（A3 删人员 / A1 仅解除匹配）。"""

    requested: int
    removed: int
    missing: int
    unassigned: int
    embedding_cascade: int
    recognition_orphaned: int
    assignment_cascade: int
    sample_cascade: int
    archive_orphaned: int
    ground_truth_orphaned: int

    @property
    def succeeded(self) -> bool:
        """Return whether the requested scope was fully processed."""
        return self.removed + self.missing + self.unassigned >= self.requested


@dataclass(frozen=True, slots=True)
class RunPhotosDeletionPreview:
    """删除某识别运行"照片及记录"的确认预览（D4）。

    照片范围 = 该运行的输入快照（``recognition_run_photos``）。计数口径：

    - ``recognition_count`` / ``archive_count`` / ``observation_count`` /
      ``sample_count`` / ``member_count``：**随照片删除被外键 CASCADE 清除**；
    - ``other_run_snapshot_count``：**其它运行**引用同一批照片的快照行数——
      同样会被级联抹掉，且不可重建（重跑会产生新的运行与 id）；
    - ``ground_truth_count``：该运行簇上的 GT 裁定行数——B1 模式下裁定行保留
      但簇已无照片支撑；若同时清理聚类代际（B2）则随簇级联删除；
    - ``blocked_reasons`` 非空即**硬阻断**（D5）。
    """

    run_found: bool
    run_created_at: datetime | None
    run_status: str
    photo_count: int
    recognition_count: int
    archive_count: int
    observation_count: int
    sample_count: int
    member_count: int
    other_run_snapshot_count: int
    cluster_count: int
    decision_count: int
    ground_truth_count: int
    blocked_reasons: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """Return whether the run has no photo snapshot to delete."""
        return self.photo_count == 0

    @property
    def is_blocked(self) -> bool:
        """Return whether irrecoverable evidence blocks the deletion."""
        return bool(self.blocked_reasons)


@dataclass(frozen=True, slots=True)
class RunPhotosDeletionResult:
    """确认后的运行级照片删除结果。"""

    requested: int
    removed: int
    missing: int
    recognition_cascade: int
    archive_cascade: int
    observation_cascade: int
    sample_cascade: int
    member_cascade: int
    other_run_snapshot_cascade: int
    unassigned_decisions: int
    clusters_recounted: int
    generations_purged: int
    ground_truth_orphaned: int
    run_removed: int = 0

    @property
    def succeeded(self) -> bool:
        """Return whether every requested photo was removed or absent."""
        return self.removed + self.missing == self.requested


@dataclass(frozen=True, slots=True)
class RunRecordDeletionPreview:
    """删除某识别运行"残留记录"的确认预览（功能 C，追加轮 21）。

    可达前提＝该运行照片登记已清空（``photo_count == 0``）——照片有专门
    的披露级联入口（D4-B）。计数口径：

    - ``generation_count`` / ``cluster_count`` / ``decision_count``：残留
      聚类代际及其簇与决策行——随记录删除级联清除（D4-B2 同语义）；
    - ``ground_truth_count``：残留代际簇上的 GT 裁定——**硬阻断**（D5：
      校准侧无删除口，阻断避免不可恢复的证据损失）；
    - ``observation_count`` / ``snapshot_count``：残留观测与输入快照行
      （正常路径为 0，兜底扫尾如实计数）。
    """

    run_found: bool
    run_created_at: datetime | None
    run_status: str
    photo_count: int
    generation_count: int
    cluster_count: int
    decision_count: int
    ground_truth_count: int
    observation_count: int
    snapshot_count: int
    blocked_reasons: tuple[str, ...] = ()

    @property
    def is_blocked(self) -> bool:
        """Return whether irrecoverable evidence blocks the deletion."""
        return bool(self.blocked_reasons)


@dataclass(frozen=True, slots=True)
class RunRecordDeletionResult:
    """确认后的运行记录清理结果。"""

    run_removed: int
    generations_purged: int
    decision_cascade: int
    observation_cascade: int
    snapshot_cascade: int
