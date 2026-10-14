"""Application port: content hashing for the S-B reference isolation guard."""

from pathlib import Path
from typing import Protocol


class PhotoContentHasher(Protocol):
    """Compute a stable content hash over raw photo file bytes.

    S-B-2（D-SB-8）二级守卫端口：主隔离不变量是 ``photo_id``，本端口提供的
    SHA-256 字节级哈希只作**辅助证据**——拦截"同字节、新路径、新 photo_id"
    的评估照片副本。实现方为 infrastructure 层的
    :class:`~photo_archiver.infrastructure.image.ContentHashCalculator`。
    """

    def calculate(self, source: Path) -> str:
        """Return the SHA-256 hex digest of the source file bytes."""
        ...
