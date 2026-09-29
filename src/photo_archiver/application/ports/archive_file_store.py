"""Archive file store port — filesystem capabilities for the archive flow.

AUD-010（Stage 12E）：ArchiveExecutor 的全部文件系统触点经本端口进行——
端口表达**归档业务能力**（包含校验、原子复制、兄弟名协商），而非 os API
封套；实现位于 ``infrastructure/filesystem``（组合根装配）。DEP §17 的
"仅 Infrastructure 可访问文件系统"由此在 application 层维持：服务只依赖
本 Protocol，直接 stdlib 文件 I/O 被架构守卫禁止。
"""

from pathlib import Path
from typing import Protocol


class ArchiveFileStore(Protocol):
    """Filesystem capabilities the archive executor needs, stated semantically."""

    def path_exists(self, path: Path) -> bool:
        """Return whether ``path`` exists (source presence / target conflict checks)."""
        ...

    def ensure_parent_directory(self, target: Path) -> None:
        """Create the parent directory of ``target`` (including ancestors) if missing."""
        ...

    def verify_target_containment(self, archive_root: Path, target: Path) -> str | None:
        """Return an error string when ``target`` would escape ``archive_root``.

        Implementations must enforce both lexical containment and
        filesystem-level containment (symlink/junction resolution) and must
        reject writing through a symlinked target. ``None`` means safe.
        """
        ...

    def copy_atomically(self, source: Path, target: Path) -> None:
        """Copy ``source`` to ``target`` so the target is never partially written.

        Implementations must preserve metadata (mtime/mode) and guarantee that
        a crash leaves either no target or a complete target (temporary-file
        + atomic replace); failure must clean up any temporary artifact.
        """
        ...

    def find_available_sibling(
        self, target: Path, conflict_suffix: str,
    ) -> Path:
        """Return the first non-existing sibling of ``target`` under ``conflict_suffix``.

        Deterministic under repeated calls with the same directory state —
        the rename strategy relies on it for stable ``.dup-N`` numbering.
        """
        ...
