"""Port for reading people from external import sources."""

from pathlib import Path
from typing import Protocol

from photo_archiver.application.dtos import PersonImportRow


class PersonImportReader(Protocol):
    """Read normalized person rows from an external source."""

    def read(
        self,
        source_path: Path,
        *,
        has_header: bool = True,
        sheet_name: str | None = None,
    ) -> list[PersonImportRow]:
        """Read people from the given file path."""