"""Command for importing people from an external file."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ImportPeopleCommand:
    """Request importing people from a tabular source such as Excel or TXT."""

    source_path: Path
    has_header: bool = True
    sheet_name: str | None = None