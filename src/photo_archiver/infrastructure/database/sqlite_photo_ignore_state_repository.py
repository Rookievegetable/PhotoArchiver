"""SQLite implementation of the photo ignore state repository."""

from uuid import UUID

from photo_archiver.domain.entities.photo_ignore_state import PhotoIgnoreState
from photo_archiver.domain.repositories.photo_ignore_state_repository import (
    PhotoIgnoreStateRepository,
)
from photo_archiver.infrastructure.database.sqlite_connection import (
    SQLiteConnectionProvider,
)
from photo_archiver.infrastructure.database.sqlite_mappers import text_to_datetime


class SQLitePhotoIgnoreStateRepository(PhotoIgnoreStateRepository):
    """Persist photo ignore states scoped by (cluster_run_id, photo_id)."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def add(self, state: PhotoIgnoreState) -> None:
        """Persist one ignore state; re-inserting the same scope is a no-op."""
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO photo_ignore_states (id, cluster_run_id, photo_id, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cluster_run_id, photo_id) DO NOTHING
                """,
                (
                    str(state.id),
                    str(state.cluster_run_id),
                    str(state.photo_id),
                    state.created_at.isoformat() if state.created_at else None,
                ),
            )

    def remove(self, cluster_run_id: UUID, photo_id: UUID) -> int:
        """Delete the scoped ignore state; return 1 when it existed."""
        with self._connection_provider.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM photo_ignore_states "
                "WHERE cluster_run_id = ? AND photo_id = ?",
                (str(cluster_run_id), str(photo_id)),
            )
            return cursor.rowcount

    def find(self, cluster_run_id: UUID, photo_id: UUID) -> PhotoIgnoreState | None:
        """Return the scoped ignore state or ``None``."""
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM photo_ignore_states "
                "WHERE cluster_run_id = ? AND photo_id = ?",
                (str(cluster_run_id), str(photo_id)),
            ).fetchone()
        return self._state_from_row(row) if row is not None else None

    def list_photo_ids(self, cluster_run_id: UUID) -> tuple[UUID, ...]:
        """Return every ignored photo id of one clustering generation."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT photo_id FROM photo_ignore_states WHERE cluster_run_id = ?",
                (str(cluster_run_id),),
            ).fetchall()
        return tuple(UUID(row["photo_id"]) for row in rows)

    def list_ignore_run_ids(self, photo_id: UUID) -> tuple[UUID, ...]:
        """Return every cluster-run id that ignores the given photo."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT cluster_run_id FROM photo_ignore_states WHERE photo_id = ?",
                (str(photo_id),),
            ).fetchall()
        return tuple(UUID(row["cluster_run_id"]) for row in rows)

    def list_by_cluster_run(self, cluster_run_id: UUID) -> list[PhotoIgnoreState]:
        """Return every ignore state of one clustering generation."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM photo_ignore_states WHERE cluster_run_id = ? "
                "ORDER BY created_at, id",
                (str(cluster_run_id),),
            ).fetchall()
        return [self._state_from_row(row) for row in rows]

    @staticmethod
    def _state_from_row(row) -> PhotoIgnoreState:  # noqa: ANN001 - sqlite3.Row
        """Rebuild the entity from a persisted row."""
        return PhotoIgnoreState(
            cluster_run_id=UUID(row["cluster_run_id"]),
            photo_id=UUID(row["photo_id"]),
            id=UUID(row["id"]),
            created_at=(
                text_to_datetime(row["created_at"])
                if row["created_at"] is not None
                else None
            ),
        )
