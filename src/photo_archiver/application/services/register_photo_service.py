"""Service implementation for registering photos."""

from pathlib import Path

from photo_archiver.application.commands import RegisterPhotoCommand
from photo_archiver.application.dtos import RegisterPhotoResult
from photo_archiver.application.ports import PhotoMetadataReader
from photo_archiver.application.use_cases import RegisterPhotoUseCase
from photo_archiver.domain import Photo, PhotoPath, PhotoPathBase, PhotoRepository


class RegisterPhotoService(RegisterPhotoUseCase):
    """Register discovered photos through a photo repository."""

    def __init__(
        self,
        repository: PhotoRepository,
        metadata_reader: PhotoMetadataReader | None = None,
    ) -> None:
        """Initialize the service with repository and optional metadata reader."""
        self._repository = repository
        self._metadata_reader = metadata_reader

    def execute(self, command: RegisterPhotoCommand) -> RegisterPhotoResult:
        """Register one photo, returning an existing photo when already known."""
        photo_path = self._build_photo_path(command.path)
        existing_photo = self._repository.find_by_path(photo_path)
        if existing_photo is not None:
            return RegisterPhotoResult(photo_id=existing_photo.id, created=False)

        metadata = None
        if self._metadata_reader is not None:
            metadata = self._metadata_reader.read(command.path)

        photo = Photo(
            path=photo_path,
            folder_id=command.folder_id,
            metadata=metadata,
            original_name=command.original_name,
        )
        self._repository.add(photo)
        return RegisterPhotoResult(photo_id=photo.id, created=True)

    @staticmethod
    def _build_photo_path(path: Path) -> PhotoPath:
        """Build a domain photo path with the correct path base.

        Absolute paths are resolved (expanduser + non-strict resolve) so drive
        letter / symlink forms normalize. Relative paths are kept relative —
        only expanduser + lexical normalize — so the PHOTO_ROOT base stays
        meaningful and cross-platform separator handling stays consistent
        (P2-d fix: avoid as_posix mismatch between absolute/relative branches).
        """
        raw = Path(path)
        if raw.is_absolute():
            normalized = raw.expanduser().resolve(strict=False)
            base = PhotoPathBase.ABSOLUTE
        else:
            normalized = raw.expanduser()
            base = PhotoPathBase.PHOTO_ROOT
        return PhotoPath(raw_path=normalized, base=base)