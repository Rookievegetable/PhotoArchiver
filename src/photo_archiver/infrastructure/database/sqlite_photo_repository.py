"""SQLite implementation of the photo repository interface."""

from uuid import UUID

from photo_archiver.domain import Photo, PhotoPath, PhotoRepository
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import (
    datetime_to_text,
    path_to_columns,
    photo_from_row,
)


class SQLitePhotoRepository(PhotoRepository):
    """Persist photos in SQLite."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def add(self, photo: Photo) -> None:
        """Persist a photo entity in SQLite using an idempotent upsert by id."""
        raw_path, path_base = path_to_columns(photo.path)
        metadata = photo.metadata
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO photos (
                    id,
                    raw_path,
                    path_base,
                    folder_id,
                    original_name,
                    created_at,
                    captured_at,
                    metadata_width,
                    metadata_height,
                    metadata_file_size_bytes,
                    metadata_modified_at,
                    metadata_content_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    raw_path = excluded.raw_path,
                    path_base = excluded.path_base,
                    folder_id = excluded.folder_id,
                    original_name = excluded.original_name,
                    created_at = excluded.created_at,
                    captured_at = excluded.captured_at,
                    metadata_width = excluded.metadata_width,
                    metadata_height = excluded.metadata_height,
                    metadata_file_size_bytes = excluded.metadata_file_size_bytes,
                    metadata_modified_at = excluded.metadata_modified_at,
                    metadata_content_hash = excluded.metadata_content_hash
                """,
                (
                    str(photo.id),
                    raw_path,
                    path_base,
                    str(photo.folder_id) if photo.folder_id is not None else None,
                    photo.original_name,
                    datetime_to_text(photo.created_at),  # type: ignore[arg-type]  # guaranteed non-None by __post_init__
                    datetime_to_text(photo.captured_at) if photo.captured_at is not None else None,
                    metadata.width if metadata is not None else None,
                    metadata.height if metadata is not None else None,
                    metadata.file_size_bytes if metadata is not None else None,
                    datetime_to_text(metadata.modified_at)
                    if metadata is not None and metadata.modified_at is not None
                    else None,
                    metadata.content_hash if metadata is not None else None,
                ),
            )

    def find_by_id(self, photo_id: UUID) -> Photo | None:
        """Find a photo by its domain identifier."""
        with self._connection_provider.connect() as connection:
            row = connection.execute("SELECT * FROM photos WHERE id = ?", (str(photo_id),)).fetchone()
        return photo_from_row(row) if row is not None else None

    def find_by_path(self, path: PhotoPath) -> Photo | None:
        """Find a photo by its path value."""
        raw_path, path_base = path_to_columns(path)
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM photos WHERE raw_path = ? AND path_base = ?",
                (raw_path, path_base),
            ).fetchone()
        return photo_from_row(row) if row is not None else None

    def list_all(self) -> list[Photo]:
        """Return all known photos."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute("SELECT * FROM photos ORDER BY created_at, id").fetchall()
        return [photo_from_row(row) for row in rows]

    def list_by_folder_id(self, folder_id: UUID) -> list[Photo]:
        """Return photos belonging to the given folder."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM photos WHERE folder_id = ? ORDER BY created_at, id",
                (str(folder_id),),
            ).fetchall()
        return [photo_from_row(row) for row in rows]
