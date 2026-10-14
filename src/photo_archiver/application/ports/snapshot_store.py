"""Application port: immutable snapshot file storage (S-B-4)."""

from pathlib import Path
from typing import Protocol


class SnapshotStore(Protocol):
    """Atomic, overwrite-refusing storage for immutable snapshot files.

    S-B-4（D-SB-6）：文件 + SHA256 是必须交付的冻结层。Snapshot 一经发布
    即不可变（§15）——实现必须原子落位（同目录 ``.part`` + ``os.replace``，
    AUD-015 同款）并**拒绝覆盖已存在的 snapshot 文件**；变化 = 新 snapshot，
    而非改写旧文件。
    """

    def path_exists(self, path: Path) -> bool:
        """Return whether the snapshot file already exists."""
        ...

    def write_atomic(self, path: Path, data: bytes) -> None:
        """Publish a snapshot file atomically; refuse to overwrite.

        Raises:
            SnapshotAlreadyExistsError: the target path already exists —
                immutable snapshots are never overwritten.
        """
        ...

    def read_bytes(self, path: Path) -> bytes:
        """Return the snapshot file bytes (read-only)."""
        ...
