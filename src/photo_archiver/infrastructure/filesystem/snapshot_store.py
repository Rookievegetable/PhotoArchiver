"""Filesystem implementation of the immutable snapshot store (S-B-4)."""

import os
from pathlib import Path

from photo_archiver.domain.exceptions import SnapshotAlreadyExistsError


class FilesystemSnapshotStore:
    """Atomic, overwrite-refusing snapshot files via ``.part`` + ``os.replace``."""

    def path_exists(self, path: Path) -> bool:
        """Return whether the snapshot file already exists."""
        return Path(path).is_file()

    def write_atomic(self, path: Path, data: bytes) -> None:
        """Publish a snapshot atomically; refuse to overwrite an existing file.

        AUD-015（Stage 12D）同款原子模式：mid-write 崩溃只遗留 ``.part``
        兄弟（无害残留，不发布半成品）；``os.replace`` 不穿越符号链接。
        覆盖已存在的 snapshot 违反不可变性（D-SB-6/§15）——fail-closed。
        """
        target = Path(path)
        if target.is_file():
            raise SnapshotAlreadyExistsError(
                f"snapshot file already exists (immutable): {target}"
            )
        temp = target.with_name(target.name + ".part")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            temp.write_bytes(data)
            os.replace(temp, target)
        finally:
            if temp.exists():
                temp.unlink()

    def read_bytes(self, path: Path) -> bytes:
        """Return the snapshot file bytes (read-only)."""
        return Path(path).read_bytes()
