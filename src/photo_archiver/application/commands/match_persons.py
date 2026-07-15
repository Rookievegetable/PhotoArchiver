"""Command for matching detected faces against known persons."""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MatchPersonsCommand:
    """Request detecting, extracting and matching faces for a batch of photos."""

    photo_ids: tuple[UUID, ...]
    images: tuple[Path, ...]
