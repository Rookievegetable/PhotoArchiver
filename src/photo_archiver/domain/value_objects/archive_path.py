"""Archive path value object.

落 Phase 2 Step 11 裁决 #2 命名规则：
    {archive_root}/{person_name}/{event_or_date}/{original_name}

`event_or_date` 段由 ArchivePathBuilder 从 `Photo.captured_at` 取日期段
（格式 YYYY-MM-DD，跨平台文件名安全、字典序与时间序一致）。
`ArchivePath` 本身不拼接路径，只持四个段值；resolve() 才合成 pathlib.Path，
遵守 Domain 零文件系统副作用的约束（resolve 不创建目录，只算字符串）。
"""

from dataclasses import dataclass
from pathlib import PurePath

from photo_archiver.domain.exceptions import ValidationError

# 裁决 #2 落地：取不到 captured_at 时用此占位段，与 unknown-person 模式一致，
# 不抛异常、不跳过归档。
UNKNOWN_EVENT_SEGMENT = "unknown-date"
UNKNOWN_PERSON_SEGMENT = "unknown-person"


@dataclass(frozen=True, slots=True)
class ArchivePath:
    """Represent the planned destination path of an archived photo.

    Hold the four naming-rule segments separately so builders, planners, and
    UI previews can inspect each segment (e.g. "this photo will land under
    Alice/2024-05-01/") without re-parsing a joined string. ``resolve`` only
    performs PurePath concatenation — it does NOT touch the filesystem — so
    the value object stays side-effect free inside the Domain layer.
    """

    archive_root: str
    person_name: str
    event_or_date: str
    original_name: str

    def __post_init__(self) -> None:
        """Validate segments without touching the filesystem.

        archive_root 是路径前缀（可含分隔符，如 /archive 或 D:/archive），
        仅做非空校验；person_name / event_or_date / original_name 是命名
        规则的"段"，段内不得含分隔符否则会逃逸层级结构。
        """
        segments = {
            "archive_root": self.archive_root,
            "person_name": self.person_name,
            "event_or_date": self.event_or_date,
            "original_name": self.original_name,
        }
        for name, value in segments.items():
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"ArchivePath {name} segment must not be empty")

        # 段内不得含路径分隔符——archive_root 豁免（它是路径前缀）。
        # review M-3 fix: also reject ".." so person_name/original_name cannot
        # escape the naming-rule hierarchy via parent-directory traversal even
        # when separators are absent (e.g. person_name=".." would climb out).
        for name in ("person_name", "event_or_date", "original_name"):
            value = segments[name].strip()
            if "/" in value or "\\" in value:
                raise ValidationError(
                    f"ArchivePath {name} segment must not contain path separators"
                )
            if value == ".." or value == ".":
                raise ValidationError(
                    f"ArchivePath {name} segment must not be a parent-directory reference"
                )

        object.__setattr__(self, "archive_root", self.archive_root.strip())
        object.__setattr__(self, "person_name", self.person_name.strip())
        object.__setattr__(self, "event_or_date", self.event_or_date.strip())
        object.__setattr__(self, "original_name", self.original_name.strip())

    @property
    def relative_path(self) -> PurePath:
        """Return the path below archive_root as a PurePath.

        Returning a PurePath (not pathlib.Path) makes the value object's
        "no filesystem" contract explicit — callers needing a real Path
        should use ``resolve`` at the Application/Infrastructure boundary.
        """
        return PurePath(self.person_name, self.event_or_date, self.original_name)

    def resolve(self) -> PurePath:
        """Return the full planned path as a PurePath.

        Side-effect free: no directory creation, no existence check. The
        ArchiveExecutor at the Application layer is responsible for any
        real filesystem operations.
        """
        return PurePath(self.archive_root, self.person_name, self.event_or_date, self.original_name)
