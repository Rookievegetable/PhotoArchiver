"""Mapping helpers between SQLite rows and domain entities."""

from datetime import datetime
from pathlib import Path
from sqlite3 import Row
from uuid import UUID

from photo_archiver.domain import Folder, Person, PersonIdentity, Photo, PhotoMetadata, PhotoPath
from photo_archiver.domain.value_objects import PhotoPathBase


def datetime_to_text(value: datetime) -> str:
    """Serialize a datetime value for SQLite storage."""
    return value.isoformat()


def text_to_datetime(value: str) -> datetime:
    """Deserialize a datetime value from SQLite storage."""
    return datetime.fromisoformat(value)


def path_to_columns(path: PhotoPath) -> tuple[str, str]:
    """Convert a PhotoPath to SQLite path columns."""
    return str(path.raw_path), str(path.base)


def columns_to_path(raw_path: str, path_base: str) -> PhotoPath:
    """Convert SQLite path columns to a PhotoPath value object."""
    return PhotoPath(Path(raw_path), PhotoPathBase(path_base))


def person_from_row(row: Row) -> Person:
    """Convert a SQLite row to a Person entity."""
    identity = PersonIdentity(row["identity"]) if row["identity"] is not None else None
    return Person(
        id=UUID(row["id"]),
        name=row["name"],
        identity=identity,
        department=row["department"],
        note=row["note"],
        created_at=text_to_datetime(row["created_at"]),
    )


def folder_from_row(row: Row) -> Folder:
    """Convert a SQLite row to a Folder entity."""
    return Folder(
        id=UUID(row["id"]),
        path=columns_to_path(row["raw_path"], row["path_base"]),
        display_name=row["display_name"],
        total_photos=row["total_photos"],
        scanned_photos=row["scanned_photos"],
        created_at=text_to_datetime(row["created_at"]),
    )


def photo_from_row(row: Row) -> Photo:
    """Convert a SQLite row to a Photo entity."""
    metadata = None
    if any(
        row[column] is not None
        for column in (
            "metadata_width",
            "metadata_height",
            "metadata_file_size_bytes",
            "metadata_modified_at",
            "metadata_content_hash",
        )
    ):
        metadata = PhotoMetadata(
            width=row["metadata_width"],
            height=row["metadata_height"],
            file_size_bytes=row["metadata_file_size_bytes"],
            modified_at=(
                text_to_datetime(row["metadata_modified_at"])
                if row["metadata_modified_at"] is not None
                else None
            ),
            content_hash=row["metadata_content_hash"],
        )

    folder_id = UUID(row["folder_id"]) if row["folder_id"] is not None else None
    return Photo(
        id=UUID(row["id"]),
        path=columns_to_path(row["raw_path"], row["path_base"]),
        folder_id=folder_id,
        metadata=metadata,
        original_name=row["original_name"],
        created_at=text_to_datetime(row["created_at"]),
    )
