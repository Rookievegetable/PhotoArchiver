"""Command for starting a traceable recognition run."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from pathlib import Path
from typing import Any
from uuid import UUID

from photo_archiver.domain import FaceCountRange


@dataclass(frozen=True, slots=True)
class StartRecognitionRunCommand:
    """Request one recognition run over an explicit photo snapshot.

    ``images`` is the immutable input snapshot used by the detector.  The
    service also records the corresponding ``RunPhotoSnapshot`` rows, so a
    later re-run never mutates this run or its observations.
    """

    photo_ids: tuple[UUID, ...]
    images: tuple[Path, ...]
    selected_ranges: tuple[FaceCountRange, ...] = (FaceCountRange(1, None),)
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.photo_ids) != len(self.images):
            raise ValueError("photo_ids and images must have the same length")
        if not self.selected_ranges:
            raise ValueError("selected_ranges must contain at least one range")
        # MappingProxyType is intentionally avoided here: repositories and JSON
        # serialization need a plain mapping, while the frozen command prevents
        # field replacement.  The service takes a deep copy before persistence.
        object.__setattr__(self, "photo_ids", tuple(self.photo_ids))
        object.__setattr__(self, "images", tuple(self.images))
        object.__setattr__(self, "selected_ranges", tuple(self.selected_ranges))
        object.__setattr__(self, "parameters", MappingProxyType(deepcopy(dict(self.parameters))))
