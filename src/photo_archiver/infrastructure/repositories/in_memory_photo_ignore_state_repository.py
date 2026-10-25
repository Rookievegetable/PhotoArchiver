"""In-memory implementation of the photo ignore state repository（测试替身）."""

from uuid import UUID

from photo_archiver.domain.entities.photo_ignore_state import PhotoIgnoreState
from photo_archiver.domain.repositories.photo_ignore_state_repository import (
    PhotoIgnoreStateRepository,
)


class InMemoryPhotoIgnoreStateRepository(PhotoIgnoreStateRepository):
    """Store photo ignore states in memory keyed by (cluster_run_id, photo_id)."""

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._states: dict[tuple[UUID, UUID], PhotoIgnoreState] = {}

    def add(self, state: PhotoIgnoreState) -> None:
        """Persist one ignore state (idempotent on the scoped unique key)."""
        self._states.setdefault(
            (state.cluster_run_id, state.photo_id), state,
        )

    def remove(self, cluster_run_id: UUID, photo_id: UUID) -> int:
        """Delete the scoped ignore state; return 1 when it existed."""
        return 1 if self._states.pop((cluster_run_id, photo_id), None) else 0

    def find(self, cluster_run_id: UUID, photo_id: UUID) -> PhotoIgnoreState | None:
        """Return the scoped ignore state or ``None``."""
        return self._states.get((cluster_run_id, photo_id))

    def list_photo_ids(self, cluster_run_id: UUID) -> tuple[UUID, ...]:
        """Return every ignored photo id of one clustering generation."""
        return tuple(
            photo_id
            for run_id, photo_id in self._states
            if run_id == cluster_run_id
        )

    def list_ignore_run_ids(self, photo_id: UUID) -> tuple[UUID, ...]:
        """Return every cluster-run id that ignores the given photo."""
        return tuple(
            run_id
            for run_id, ignored_photo in self._states
            if ignored_photo == photo_id
        )

    def list_by_cluster_run(self, cluster_run_id: UUID) -> list[PhotoIgnoreState]:
        """Return every ignore state of one clustering generation."""
        return [
            state
            for (run_id, _), state in self._states.items()
            if run_id == cluster_run_id
        ]
