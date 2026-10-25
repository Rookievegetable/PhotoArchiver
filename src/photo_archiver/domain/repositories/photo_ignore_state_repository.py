"""Photo ignore state repository interface."""

from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities.photo_ignore_state import PhotoIgnoreState


class PhotoIgnoreStateRepository(Protocol):
    """Define persistence operations for photo ignore states."""

    def add(self, state: PhotoIgnoreState) -> None:
        """Persist one ignore state (idempotent on the scoped unique key)."""

    def remove(self, cluster_run_id: UUID, photo_id: UUID) -> int:
        """Delete the scoped ignore state; return 1 when it existed."""

    def find(self, cluster_run_id: UUID, photo_id: UUID) -> PhotoIgnoreState | None:
        """Return the scoped ignore state or ``None``."""

    def list_photo_ids(self, cluster_run_id: UUID) -> tuple[UUID, ...]:
        """Return every ignored photo id of one clustering generation."""

    def list_ignore_run_ids(self, photo_id: UUID) -> tuple[UUID, ...]:
        """Return every cluster-run id that ignores the given photo."""

    def list_by_cluster_run(self, cluster_run_id: UUID) -> list[PhotoIgnoreState]:
        """Return every ignore state of one clustering generation."""
