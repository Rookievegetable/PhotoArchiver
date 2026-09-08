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
    """

    person_ids: tuple[UUID, ...]
    missing_ids: tuple[UUID, ...]
    embedding_count: int
    recognition_count: int

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

