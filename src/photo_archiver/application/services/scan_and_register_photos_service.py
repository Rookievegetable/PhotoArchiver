"""Service implementation for scanning and registering photos."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from loguru import logger

from photo_archiver.application.commands import ScanAndRegisterPhotosCommand
from photo_archiver.application.dtos import PhotoScanItem, ScanAndRegisterPhotosResult
from photo_archiver.application.ports import (
    PhotoFileScanner,
    PhotoMetadataReader,
    ProgressReporter,
    UnitOfWork,
)
from photo_archiver.application.use_cases import ScanAndRegisterPhotosUseCase
from photo_archiver.domain import Folder, FolderRepository, Photo, PhotoPath, PhotoPathBase, PhotoRepository

# Report progress at most every N items to avoid flooding the event stream.
# First and last items always report so small batches stay visible to the UI.
_PROGRESS_REPORT_INTERVAL = 10


class ScanAndRegisterPhotosService(ScanAndRegisterPhotosUseCase):
    """Scan a folder, register photos, and update folder counters."""

    def __init__(
        self,
        scanner: PhotoFileScanner,
        folder_repository: FolderRepository,
        photo_repository: PhotoRepository,
        metadata_reader: PhotoMetadataReader | None = None,
        progress_reporter: ProgressReporter | None = None,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize the service with ports and repositories."""
        self._scanner = scanner
        self._folder_repository = folder_repository
        self._photo_repository = photo_repository
        self._metadata_reader = metadata_reader
        self._progress_reporter = progress_reporter
        self._unit_of_work = unit_of_work

    def execute(self, command: ScanAndRegisterPhotosCommand) -> ScanAndRegisterPhotosResult:
        """Scan the command folder and persist each discovered photo."""
        folder_path = self._absolute_path(command.folder_path)

        try:
            scan_items = self._scanner.scan(
                folder_path,
                recursive=command.recursive,
                supported_extensions=command.supported_extensions,
            )
        except OSError as exc:
            logger.warning("Scan failed for {}: {}", folder_path, exc)
            return ScanAndRegisterPhotosResult(failed_count=1, errors=(str(exc),))

        if self._unit_of_work is not None:
            with self._unit_of_work:
                return self._scan_and_register(folder_path, command.folder_display_name, scan_items)

        return self._scan_and_register(folder_path, command.folder_display_name, scan_items)

    def _scan_and_register(
        self,
        folder_path: Path,
        display_name: str | None,
        scan_items: list[PhotoScanItem],
    ) -> ScanAndRegisterPhotosResult:
        """Run the registration loop within (or outside) a unit-of-work scope."""
        total = len(scan_items)
        folder = self._get_or_create_folder(folder_path, display_name)

        registered_count = 0
        skipped_count = 0
        errors: list[str] = []

        for index, item in enumerate(scan_items, start=1):
            photo_path = self._absolute_path(item.path)
            path_value = self._photo_path(photo_path)
            if self._photo_repository.find_by_path(path_value) is not None:
                skipped_count += 1
                self._report(index, total, "Skipping existing photo")
                continue

            metadata = None
            if self._metadata_reader is not None:
                try:
                    metadata = self._metadata_reader.read(photo_path)
                except (OSError, ValueError, RuntimeError) as exc:
                    errors.append(f"{photo_path}: {exc}")
                    self._report(index, total, "Failed to read metadata")
                    continue

            photo = Photo(
                path=path_value,
                folder_id=folder.id,
                metadata=metadata,
                original_name=item.original_name or photo_path.name,
            )
            self._photo_repository.add(photo)
            registered_count += 1
            self._report(index, total, "Registered photo")

        folder.total_photos = total
        folder.scanned_photos = registered_count + skipped_count
        self._folder_repository.add(folder)

        return ScanAndRegisterPhotosResult(
            folder_id=folder.id,
            discovered_count=total,
            registered_count=registered_count,
            skipped_count=skipped_count,
            failed_count=len(errors),
            errors=tuple(errors),
        )

    def _report(self, current: int, total: int, message: str) -> None:
        """Forward progress to the reporter when one is bound.

        Always reports the first and last items so small batches (total below
        the interval) still surface visible progress to the UI; intermediate
        items report every ``_PROGRESS_REPORT_INTERVAL`` steps to avoid flooding.
        """
        if self._progress_reporter is None:
            return
        is_boundary = current == 1 or current == total
        is_interval = current % _PROGRESS_REPORT_INTERVAL == 0
        if not (is_boundary or is_interval):
            return
        self._progress_reporter.report(current, total, message)

    @contextmanager
    def bind_progress_reporter(self, reporter: ProgressReporter) -> Iterator[None]:
        """Temporarily bind a progress reporter for the duration of a use case.

        Worker tasks use this to stream per-item progress through their own
        ``report`` adapter without permanently mutating the service configuration.
        The previous reporter (typically ``None``) is restored on exit.
        """
        previous = self._progress_reporter
        self._progress_reporter = reporter
        try:
            yield None
        finally:
            self._progress_reporter = previous

    def _get_or_create_folder(self, folder_path: Path, display_name: str | None) -> Folder:
        """Return the existing folder aggregate for the path, or create one."""
        path_value = self._photo_path(folder_path)
        folder = self._folder_repository.find_by_path(path_value)
        if folder is not None:
            if display_name is not None:
                folder.display_name = display_name
            return folder

        folder = Folder(path=path_value, display_name=display_name or folder_path.name)
        self._folder_repository.add(folder)
        return folder

    @staticmethod
    def _absolute_path(path: Path) -> Path:
        """Normalize a filesystem path without requiring it to exist."""
        return Path(path).expanduser().resolve(strict=False)

    @staticmethod
    def _photo_path(path: Path) -> PhotoPath:
        """Build an absolute domain photo path."""
        return PhotoPath(raw_path=path, base=PhotoPathBase.ABSOLUTE)
