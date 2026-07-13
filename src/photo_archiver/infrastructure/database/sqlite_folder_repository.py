"""SQLite implementation of the folder repository interface."""

from uuid import UUID

from photo_archiver.domain import Folder, FolderRepository, PhotoPath
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import (
    datetime_to_text,
    folder_from_row,
    path_to_columns,
)


class SQLiteFolderRepository(FolderRepository):
    """Persist folders in SQLite."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def add(self, folder: Folder) -> None:
        """Persist a folder entity in SQLite using an idempotent upsert by id."""
        raw_path, path_base = path_to_columns(folder.path)
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO folders (
                    id, raw_path, path_base, display_name, total_photos, scanned_photos, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    raw_path = excluded.raw_path,
                    path_base = excluded.path_base,
                    display_name = excluded.display_name,
                    total_photos = excluded.total_photos,
                    scanned_photos = excluded.scanned_photos,
                    created_at = excluded.created_at
                """,
                (
                    str(folder.id),
                    raw_path,
                    path_base,
                    folder.display_name,
                    folder.total_photos,
                    folder.scanned_photos,
                    datetime_to_text(folder.created_at),
                ),
            )

    def find_by_id(self, folder_id: UUID) -> Folder | None:
        """Find a folder by its domain identifier."""
        with self._connection_provider.connect() as connection:
            row = connection.execute("SELECT * FROM folders WHERE id = ?", (str(folder_id),)).fetchone()
        return folder_from_row(row) if row is not None else None

    def find_by_path(self, path: PhotoPath) -> Folder | None:
        """Find a folder by its path value."""
        raw_path, path_base = path_to_columns(path)
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM folders WHERE raw_path = ? AND path_base = ?",
                (raw_path, path_base),
            ).fetchone()
        return folder_from_row(row) if row is not None else None

    def list_all(self) -> list[Folder]:
        """Return all known folders."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute("SELECT * FROM folders ORDER BY created_at, id").fetchall()
        return [folder_from_row(row) for row in rows]
