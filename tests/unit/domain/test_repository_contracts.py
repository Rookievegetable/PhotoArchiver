"""Tests for repository protocol contracts."""

from uuid import UUID

from photo_archiver.domain import (
    Folder,
    FolderRepository,
    Person,
    PersonIdentity,
    PersonRepository,
    Photo,
    PhotoPath,
    PhotoRepository,
)


class InMemoryFolderRepository:
    """Test double implementing the folder repository protocol."""

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._folders: dict[UUID, Folder] = {}

    def add(self, folder: Folder) -> None:
        """Persist a folder in memory."""
        assert folder.id is not None
        self._folders[folder.id] = folder

    def find_by_id(self, folder_id: UUID) -> Folder | None:
        """Find a folder by identifier."""
        return self._folders.get(folder_id)

    def find_by_path(self, path: PhotoPath) -> Folder | None:
        """Find a folder by path."""
        for folder in self._folders.values():
            if folder.path == path:
                return folder
        return None

    def list_all(self) -> list[Folder]:
        """Return all folders."""
        return list(self._folders.values())


class InMemoryPersonRepository:
    """Test double implementing the person repository protocol."""

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._people: dict[UUID, Person] = {}

    def add(self, person: Person) -> None:
        """Persist a person in memory."""
        assert person.id is not None
        self._people[person.id] = person

    def find_by_id(self, person_id: UUID) -> Person | None:
        """Find a person by identifier."""
        return self._people.get(person_id)

    def find_by_identity(self, identity: PersonIdentity) -> Person | None:
        """Find a person by external identity."""
        for person in self._people.values():
            if person.identity == identity:
                return person
        return None

    def list_all(self) -> list[Person]:
        """Return all people."""
        return list(self._people.values())


class InMemoryPhotoRepository:
    """Test double implementing the photo repository protocol."""

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._photos: dict[UUID, Photo] = {}

    def add(self, photo: Photo) -> None:
        """Persist a photo in memory."""
        assert photo.id is not None
        self._photos[photo.id] = photo

    def find_by_id(self, photo_id: UUID) -> Photo | None:
        """Find a photo by identifier."""
        return self._photos.get(photo_id)

    def find_by_path(self, path: PhotoPath) -> Photo | None:
        """Find a photo by path."""
        for photo in self._photos.values():
            if photo.path == path:
                return photo
        return None

    def list_all(self) -> list[Photo]:
        """Return all photos."""
        return list(self._photos.values())

    def list_by_folder_id(self, folder_id: UUID) -> list[Photo]:
        """Return photos belonging to a folder."""
        return [photo for photo in self._photos.values() if photo.folder_id == folder_id]


def test_folder_repository_protocol_accepts_test_double() -> None:
    """Folder repository interfaces can be implemented without database dependencies."""
    repository: FolderRepository = InMemoryFolderRepository()
    path = PhotoPath("school")
    folder = Folder(path=path)

    repository.add(folder)

    assert folder.id is not None
    assert repository.find_by_id(folder.id) == folder
    assert repository.find_by_path(path) == folder
    assert repository.list_all() == [folder]


def test_person_repository_protocol_accepts_test_double() -> None:
    """Repository interfaces can be implemented without database dependencies."""
    repository: PersonRepository = InMemoryPersonRepository()
    person = Person(name="Alice", identity=PersonIdentity("A001"))

    repository.add(person)

    assert person.id is not None
    assert repository.find_by_id(person.id) == person
    assert repository.find_by_identity(PersonIdentity("A001")) == person
    assert repository.list_all() == [person]


def test_photo_repository_protocol_accepts_test_double() -> None:
    """Photo repository interfaces can be implemented without database dependencies."""
    repository: PhotoRepository = InMemoryPhotoRepository()
    folder = Folder(path=PhotoPath("school"))
    path = PhotoPath("school/event.jpg")
    photo = Photo(path=path, folder_id=folder.id)

    repository.add(photo)

    assert photo.id is not None
    assert folder.id is not None
    assert repository.find_by_id(photo.id) == photo
    assert repository.find_by_path(path) == photo
    assert repository.list_all() == [photo]
    assert repository.list_by_folder_id(folder.id) == [photo]