"""SQLite repository implementation tests."""

from datetime import datetime
from pathlib import Path
import sqlite3

import pytest

from photo_archiver.domain import (
    FaceEmbedding,
    Folder,
    MatchStatus,
    Person,
    PersonIdentity,
    Photo,
    PhotoMetadata,
    PhotoPath,
    RecognitionResult,
)
from photo_archiver.infrastructure import (
    SQLiteConnectionProvider,
    SQLiteFaceEmbeddingRepository,
    SQLiteFolderRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRepository,
)


def create_provider(tmp_path: Path) -> SQLiteConnectionProvider:
    """Create and initialize a temporary SQLite database provider."""
    provider = SQLiteConnectionProvider(tmp_path / "photo_archiver.sqlite3")
    provider.initialize_schema()
    return provider


def test_sqlite_person_repository_round_trips_people(tmp_path: Path) -> None:
    """Persist and retrieve people through the SQLite repository."""
    repository = SQLitePersonRepository(create_provider(tmp_path))
    person = Person(
        name=" Alice ",
        identity=PersonIdentity(" A001 "),
        department=" Archive ",
        note=" Team lead ",
    )

    repository.add(person)

    assert repository.find_by_id(person.id) == person
    assert repository.find_by_identity(PersonIdentity("A001")) == person
    assert repository.list_all() == [person]


def test_sqlite_schema_sets_user_version(tmp_path: Path) -> None:
    """Initialize SQLite schema with a version marker for future migrations."""
    provider = create_provider(tmp_path)

    with provider.connect() as connection:
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert user_version == 3


def test_sqlite_person_repository_upserts_by_id(tmp_path: Path) -> None:
    """Adding the same aggregate id replaces persisted person fields."""
    repository = SQLitePersonRepository(create_provider(tmp_path))
    person = Person(name="Alice", identity=PersonIdentity("A001"))
    repository.add(person)
    updated_person = Person(
        id=person.id,
        name="Alice Updated",
        identity=PersonIdentity("A002"),
        department="Archive",
        created_at=person.created_at,
    )

    repository.add(updated_person)

    assert repository.find_by_id(person.id) == updated_person
    assert repository.find_by_identity(PersonIdentity("A001")) is None
    assert repository.find_by_identity(PersonIdentity("A002")) == updated_person


def test_sqlite_folder_repository_round_trips_folders(tmp_path: Path) -> None:
    """Persist and retrieve folders through the SQLite repository."""
    repository = SQLiteFolderRepository(create_provider(tmp_path))
    folder = Folder(
        path=PhotoPath("school"),
        display_name=" School Album ",
        total_photos=3,
        scanned_photos=1,
    )

    repository.add(folder)

    assert repository.find_by_id(folder.id) == folder
    assert repository.find_by_path(PhotoPath("school")) == folder
    assert repository.list_all() == [folder]


def test_sqlite_folder_repository_rejects_duplicate_paths(tmp_path: Path) -> None:
    """Unique folder paths are enforced by SQLite constraints."""
    repository = SQLiteFolderRepository(create_provider(tmp_path))
    repository.add(Folder(path=PhotoPath("school"), total_photos=1))

    with pytest.raises(sqlite3.IntegrityError):
        repository.add(Folder(path=PhotoPath("school"), total_photos=2))


def test_sqlite_photo_repository_round_trips_photos_and_metadata(tmp_path: Path) -> None:
    """Persist and retrieve photos with folder references and metadata."""
    provider = create_provider(tmp_path)
    folder_repository = SQLiteFolderRepository(provider)
    photo_repository = SQLitePhotoRepository(provider)
    folder = Folder(path=PhotoPath("school"), total_photos=1)
    folder_repository.add(folder)
    metadata = PhotoMetadata(
        width=640,
        height=480,
        file_size_bytes=12345,
        modified_at=datetime(2026, 7, 7, 18, 0, 0),
        content_hash=" abc123 ",
    )
    photo = Photo(
        path=PhotoPath("school/event.jpg"),
        folder_id=folder.id,
        metadata=metadata,
        original_name=" event.jpg ",
    )

    photo_repository.add(photo)

    assert photo_repository.find_by_id(photo.id) == photo
    assert photo_repository.find_by_path(PhotoPath("school/event.jpg")) == photo
    assert photo_repository.list_all() == [photo]
    assert photo_repository.list_by_folder_id(folder.id) == [photo]


def test_sqlite_photo_repository_rejects_duplicate_paths(tmp_path: Path) -> None:
    """Unique photo paths are enforced by SQLite constraints."""
    repository = SQLitePhotoRepository(create_provider(tmp_path))
    repository.add(Photo(path=PhotoPath("school/event.jpg")))

    with pytest.raises(sqlite3.IntegrityError):
        repository.add(Photo(path=PhotoPath("school/event.jpg")))


def test_sqlite_photo_folder_foreign_key_sets_folder_id_to_null(tmp_path: Path) -> None:
    """Deleting a folder row preserves photos and clears their folder reference."""
    provider = create_provider(tmp_path)
    folder_repository = SQLiteFolderRepository(provider)
    photo_repository = SQLitePhotoRepository(provider)
    folder = Folder(path=PhotoPath("school"), total_photos=1)
    folder_repository.add(folder)
    photo = Photo(path=PhotoPath("school/event.jpg"), folder_id=folder.id)
    photo_repository.add(photo)

    with provider.connect() as connection:
        connection.execute("DELETE FROM folders WHERE id = ?", (str(folder.id),))

    persisted_photo = photo_repository.find_by_id(photo.id)
    assert persisted_photo is not None
    assert persisted_photo.folder_id is None


def test_sqlite_recognition_repository_round_trips_result(tmp_path: Path) -> None:
    """Persist and retrieve recognition results through the SQLite repository."""
    provider = create_provider(tmp_path)
    folder_repository = SQLiteFolderRepository(provider)
    photo_repository = SQLitePhotoRepository(provider)
    recognition_repository = SQLiteRecognitionRepository(provider)

    folder = Folder(path=PhotoPath("school"), total_photos=1)
    folder_repository.add(folder)
    photo = Photo(path=PhotoPath("school/event.jpg"), folder_id=folder.id)
    photo_repository.add(photo)

    result = RecognitionResult(photo_id=photo.id, confidence=0.8)
    recognition_repository.add(result)

    assert recognition_repository.find_by_id(result.id) == result
    assert recognition_repository.list_by_photo(photo.id) == [result]
    assert recognition_repository.list_pending() == [result]


def test_sqlite_recognition_repository_upserts_by_id(tmp_path: Path) -> None:
    """Adding the same result id replaces persisted fields."""
    provider = create_provider(tmp_path)
    folder_repository = SQLiteFolderRepository(provider)
    photo_repository = SQLitePhotoRepository(provider)
    recognition_repository = SQLiteRecognitionRepository(provider)

    folder = Folder(path=PhotoPath("school"), total_photos=1)
    folder_repository.add(folder)
    photo = Photo(path=PhotoPath("school/event.jpg"), folder_id=folder.id)
    photo_repository.add(photo)

    result = RecognitionResult(photo_id=photo.id, confidence=0.7)
    recognition_repository.add(result)
    updated = RecognitionResult(
        id=result.id,
        photo_id=photo.id,
        confidence=0.9,
        created_at=result.created_at,
    )
    recognition_repository.add(updated)

    assert recognition_repository.find_by_id(result.id) == updated


def test_sqlite_recognition_repository_update_status(tmp_path: Path) -> None:
    """update_status must persist the new review status."""
    provider = create_provider(tmp_path)
    folder_repository = SQLiteFolderRepository(provider)
    photo_repository = SQLitePhotoRepository(provider)
    recognition_repository = SQLiteRecognitionRepository(provider)

    folder = Folder(path=PhotoPath("school"), total_photos=1)
    folder_repository.add(folder)
    photo = Photo(path=PhotoPath("school/event.jpg"), folder_id=folder.id)
    photo_repository.add(photo)

    result = RecognitionResult(photo_id=photo.id, confidence=0.8)
    recognition_repository.add(result)
    recognition_repository.update_status(result.id, MatchStatus.APPROVED)

    persisted = recognition_repository.find_by_id(result.id)
    assert persisted is not None
    assert persisted.status is MatchStatus.APPROVED
    assert recognition_repository.list_pending() == []


def test_sqlite_recognition_repository_list_pending_filters_status(tmp_path: Path) -> None:
    """list_pending must only return PENDING results."""
    provider = create_provider(tmp_path)
    folder_repository = SQLiteFolderRepository(provider)
    photo_repository = SQLitePhotoRepository(provider)
    recognition_repository = SQLiteRecognitionRepository(provider)

    folder = Folder(path=PhotoPath("school"), total_photos=2)
    folder_repository.add(folder)
    photo1 = Photo(path=PhotoPath("school/a.jpg"), folder_id=folder.id)
    photo2 = Photo(path=PhotoPath("school/b.jpg"), folder_id=folder.id)
    photo_repository.add(photo1)
    photo_repository.add(photo2)

    pending = RecognitionResult(photo_id=photo1.id, confidence=0.6)
    approved = RecognitionResult(photo_id=photo2.id, confidence=0.9)
    approved.approve()
    recognition_repository.add(pending)
    recognition_repository.add(approved)

    assert recognition_repository.list_pending() == [pending]


def test_sqlite_face_embedding_repository_round_trips_embedding(tmp_path: Path) -> None:
    """Persist and retrieve a face embedding through the SQLite repository."""
    provider = create_provider(tmp_path)
    person_repo = SQLitePersonRepository(provider)
    embedding_repo = SQLiteFaceEmbeddingRepository(provider)

    person = Person(name="Alice")
    person_repo.add(person)
    embedding = FaceEmbedding((0.1, 0.2, 0.3, 0.4))
    embedding_repo.save(person.id, embedding)

    retrieved = embedding_repo.find_by_person(person.id)
    assert retrieved is not None
    assert retrieved.vector == embedding.vector
    assert retrieved.dimension == 4


def test_sqlite_face_embedding_repository_upserts_by_person(tmp_path: Path) -> None:
    """Saving the same person twice must replace the embedding."""
    provider = create_provider(tmp_path)
    person_repo = SQLitePersonRepository(provider)
    embedding_repo = SQLiteFaceEmbeddingRepository(provider)

    person = Person(name="Bob")
    person_repo.add(person)
    embedding_repo.save(person.id, FaceEmbedding((0.1, 0.2)))
    embedding_repo.save(person.id, FaceEmbedding((0.9, 0.8)))

    retrieved = embedding_repo.find_by_person(person.id)
    assert retrieved is not None
    assert retrieved.vector == (0.9, 0.8)


def test_sqlite_face_embedding_repository_find_missing_returns_none(tmp_path: Path) -> None:
    """find_by_person must return None when no embedding is stored."""
    provider = create_provider(tmp_path)
    embedding_repo = SQLiteFaceEmbeddingRepository(provider)
    from uuid import uuid4

    assert embedding_repo.find_by_person(uuid4()) is None


def test_sqlite_face_embedding_repository_list_all(tmp_path: Path) -> None:
    """list_all must return every persisted embedding keyed by person_id."""
    provider = create_provider(tmp_path)
    person_repo = SQLitePersonRepository(provider)
    embedding_repo = SQLiteFaceEmbeddingRepository(provider)

    person1 = Person(name="Carol")
    person2 = Person(name="Dave")
    person_repo.add(person1)
    person_repo.add(person2)
    e1 = FaceEmbedding((0.1, 0.2))
    e2 = FaceEmbedding((0.3, 0.4))
    embedding_repo.save(person1.id, e1)
    embedding_repo.save(person2.id, e2)

    all_embeddings = embedding_repo.list_all()
    assert len(all_embeddings) == 2
    assert all_embeddings[person1.id] == e1
    assert all_embeddings[person2.id] == e2
