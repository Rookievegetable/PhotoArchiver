"""Roster table reader port — decodes a roster file into a raw table.

Stage A of the people-import redesign: the parse service works on a decoded
:class:`RawRosterTable` (encoding/delimiter already resolved by the
implementation) instead of the legacy fixed-4-column rows, so the preview can
show raw content and let the user remap fields before anything is written.
"""

from pathlib import Path
from typing import Protocol

from photo_archiver.application.dtos.import_draft import RawRosterTable


class RosterTableReader(Protocol):
    """Decode one roster file into a raw table.

    Implementations must resolve encoding (text files) and select the
    worksheet (workbooks) themselves, and raise a clear exception
    (``ValueError``/``OSError``) for unsupported or unreadable files rather
    than returning garbage rows.
    """

    def read_raw(
        self,
        source_path: Path,
        *,
        has_header: bool = True,
        sheet_name: str | None = None,
    ) -> RawRosterTable:
        """Decode the file; the first row is returned via ``header`` when ``has_header``."""
        ...

    def read_bytes(self, source_path: Path) -> bytes:
        """Return the raw file bytes（批次 file_hash 溯源用，AUD-010）。

        实现负责打开文件；调用方（parse 服务）对字节做纯计算（SHA-256）。
        """
        ...
