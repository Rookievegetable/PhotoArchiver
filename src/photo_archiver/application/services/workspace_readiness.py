"""Bounded workspace readiness query; no planning, scanning or mutations."""

from collections.abc import Callable
from pathlib import Path

from photo_archiver.application.dtos.workspace import ModelAvailability, WorkspaceStatus
from photo_archiver.domain import RecognitionRepository


class WorkspaceReadinessService:
    """Combine aggregate repository facts with an injected environment probe."""

    def __init__(
        self,
        recognition_repository: RecognitionRepository,
        *,
        archive_root_probe: Callable[[Path], bool],
        model_availability: ModelAvailability = ModelAvailability.UNKNOWN,
    ) -> None:
        """Capture pipeline availability at assembly; never recheck model files."""
        self._recognition_repository = recognition_repository
        self._archive_root_probe = archive_root_probe
        self._model_availability = model_availability

    def execute(self, archive_root: Path | None) -> WorkspaceStatus:
        """Read one database snapshot and probe only the proposed archive root.

        Repository/probe failures propagate rather than being disguised as action
        availability. A missing root preference is unavailable, without probing.
        """
        counts = self._recognition_repository.read_workspace_counts()
        return WorkspaceStatus(
            has_persons=counts.has_persons,
            has_photos=counts.has_photos,
            pending_match_count=counts.pending_match_count,
            pending_review_count=counts.pending_review_count,
            archivable_count=counts.archivable_count,
            archive_root_available=(
                archive_root is not None and self._archive_root_probe(archive_root)
            ),
            model_availability=self._model_availability,
        )
