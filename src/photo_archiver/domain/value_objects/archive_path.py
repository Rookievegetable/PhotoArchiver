"""Archive path value object.

落 Phase 2 Step 11 裁决 #2 命名规则：
    {archive_root}/{person_name}/{event_or_date}/{original_name}

`event_or_date` 段由 ArchivePathBuilder 从 `Photo.captured_at` 取日期段
（格式 YYYY-MM-DD，跨平台文件名安全、字典序与时间序一致）。
`ArchivePath` 本身不拼接路径，只持四个段值；resolve() 才合成 pathlib.Path，
遵守 Domain 零文件系统副作用的约束（resolve 不创建目录，只算字符串）。

ADR-036 D4：person_name / event_or_date / original_name 三段在构造时经
Windows 文件名语义净化（非法字符/尾点尾空格/保留设备名）——纯字符串逻辑，
零文件系统调用；静默替换不拒绝，审计日志由 Application 层 builder 负责。
"""

from dataclasses import dataclass
from pathlib import PurePath

from photo_archiver.domain.exceptions import ValidationError

# 裁决 #2 落地：取不到 captured_at 时用此占位段，与 unknown-person 模式一致，
# 不抛异常、不跳过归档。
UNKNOWN_EVENT_SEGMENT = "unknown-date"
UNKNOWN_PERSON_SEGMENT = "unknown-person"

# ADR-036 D4：Windows 保留设备名（大小写不敏感；按文件名首个 '.' 前的词干匹配，
# 同时覆盖 con.jpg 与 con.txt.bak 两种形态——NT 保留名检查对首个点前部分生效）。
WINDOWS_RESERVED_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

# Windows 禁止出现在文件名中的字符（另加控制字符）；分隔符 / \ 不在此列——
# 它们属于"段不得逃逸层级"的校验错误，保持 raise 而非替换。
_WINDOWS_ILLEGAL_CHARS = ':*?"<>|'


def sanitize_windows_filename(name: str) -> str:
    """Return a Windows-safe filename (ADR-036 D4). Pure string logic.

    Rules (applied in order):
        1. illegal characters ``: * ? " < > |`` and control characters → ``_``;
        2. trailing dots and spaces removed (Windows rejects them silently);
        3. reserved device names (stem before the first dot, case-insensitive)
           prefixed with ``_`` so ``con.jpg`` → ``_con.jpg``.

    The result may be empty (e.g. ``"..."``) — callers decide whether that is
    acceptable. Does not touch separators: ``/`` and ``\\`` are a hierarchy-
    escape validation error handled by ``ArchivePath``, not a sanitizable flaw.
    """
    cleaned = "".join(
        "_" if ch in _WINDOWS_ILLEGAL_CHARS or ord(ch) < 32 or ord(ch) == 127 else ch
        for ch in name
    )
    cleaned = cleaned.rstrip(". ")
    if cleaned:
        stem = cleaned.split(".", 1)[0]
        if stem.upper() in WINDOWS_RESERVED_DEVICE_NAMES:
            cleaned = "_" + cleaned
    return cleaned


@dataclass(frozen=True, slots=True)
class ArchivePath:
    """Represent the planned destination path of an archived photo.

    Hold the four naming-rule segments separately so builders, planners, and
    UI previews can inspect each segment (e.g. "this photo will land under
    Alice/2024-05-01/photo.jpg") without re-parsing a joined string. ``resolve``
    only performs PurePath concatenation — it does NOT touch the filesystem —
    so the value object stays side-effect free inside the Domain layer.

    The three naming segments are sanitized at construction (ADR-036 D4): the
    stored values are the safe forms, so previews and archive records always
    show what will actually land on disk.
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

        # ADR-036 D4：净化后的安全名才是入库/预览/落盘的值。
        for name in ("person_name", "event_or_date", "original_name"):
            value = sanitize_windows_filename(segments[name].strip())
            if not value:
                raise ValidationError(
                    f"ArchivePath {name} segment is empty after Windows-name sanitization"
                )
            object.__setattr__(self, name, value)

        object.__setattr__(self, "archive_root", self.archive_root.strip())

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
