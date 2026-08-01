"""DTOs for the duplicate detection workflow (B1 重复图片检测).

DetectDuplicatesService 编排 ``PhotoRepository.list_duplicate_groups``
产此 DTO 返 Presentation 层。**首版只报告不删除**——删除用户文件属高危操作
（ai-rules §20），留后续版本裁决。

DTO 持 Domain ``Photo`` 实体引用而非拷贝——查重结果在 UI 展示阶段 photo 路径
与原始名需即时可读，且本 DTO 不跨进程序列化（无 pickle/JSON 落地），持引用
合规且零冗余。
"""

from dataclasses import dataclass

from photo_archiver.domain.entities import Photo


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """One group of photos sharing the same non-null content hash.

    Members are ordered by the repository implementation's stable order
    (SQLite: created_at + id; InMemory: same). The ``content_hash`` is the
    SHA-256 digest shared by all members; surfaced for logging / UI grouping
    display without forcing the caller to dereference metadata again.
    """

    content_hash: str
    members: tuple[Photo, ...]


@dataclass(frozen=True, slots=True)
class DuplicateReport:
    """Aggregate result of a duplicate detection run.

    group_count: How many distinct content hashes had ≥2 photos.
    photos_in_groups: Total photos across all groups (= sum of member counts).
    groups: The duplicate groups themselves, ordered by descending group size
        so the most duplicated files surface first in the UI report.
    """

    groups: tuple[DuplicateGroup, ...]

    @property
    def group_count(self) -> int:
        """Return the number of distinct duplicate groups."""
        return len(self.groups)

    @property
    def photos_in_groups(self) -> int:
        """Return the total number of photos across all duplicate groups."""
        return sum(len(g.members) for g in self.groups)

    @property
    def has_duplicates(self) -> bool:
        """Return whether any duplicate group was found."""
        return bool(self.groups)
