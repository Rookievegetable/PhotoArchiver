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
from photo_archiver.domain import (
    Folder,
    FolderRepository,
    Photo,
    PhotoMetadata,
    PhotoPath,
    PhotoPathBase,
    PhotoRepository,
)

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

    def enumerate_files(self, command: ScanAndRegisterPhotosCommand) -> list[PhotoScanItem]:
        """Enumerate candidate files for the command folder (ADR-041).

        Intended to be called on the **main thread** before submission: on
        macOS, directory enumeration from a background thread while the main
        thread runs the Qt event loop can segfault (LIMIT-006, see
        KNOWN_ISSUES.md). The controller pre-enumerates here and passes the
        result back via ``command.pre_enumerated_items`` so the worker thread
        never touches directory-enumeration or realpath syscalls.

        Raises:
            OSError: Propagated from the scanner — the caller (controller)
                surfaces it; unlike ``execute`` this does not wrap the error
                in a result, because the submission itself should not start.
        """
        folder_path = self._absolute_path(command.folder_path)
        return self._scanner.scan(
            folder_path,
            recursive=command.recursive,
            supported_extensions=command.supported_extensions,
        )

    def execute(self, command: ScanAndRegisterPhotosCommand) -> ScanAndRegisterPhotosResult:
        """Scan the command folder and persist each discovered photo."""
        if command.pre_enumerated_items is not None:
            # ADR-041: the controller enumerated on the main thread and
            # guarantees folder_path is resolved and every item path is a
            # real absolute path — the worker performs ZERO enumeration or
            # realpath syscalls (LIMIT-006 workaround).
            folder_path = command.folder_path
            scan_items = list(command.pre_enumerated_items)
            resolve_item_paths = False
        else:
            folder_path = self._absolute_path(command.folder_path)
            resolve_item_paths = True
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
                return self._scan_and_register(folder_path, command.folder_display_name, scan_items, resolve_item_paths)

        return self._scan_and_register(folder_path, command.folder_display_name, scan_items, resolve_item_paths)

    def _scan_and_register(
        self,
        folder_path: Path,
        display_name: str | None,
        scan_items: list[PhotoScanItem],
        resolve_item_paths: bool = True,
    ) -> ScanAndRegisterPhotosResult:
        """Run the registration loop within (or outside) a unit-of-work scope."""
        total = len(scan_items)
        folder = self._get_or_create_folder(folder_path, display_name)

        # Pre-fetch existing photos for this folder once to avoid N+1
        # find_by_path queries inside the scan loop (P1-b fix). Path comparison
        # happens in memory against the fetched mapping — E-5 重扫对账需要
        # path → 既有 Photo（拿既有 id 做元数据刷新）。
        existing_photos = {
            photo.path: photo
            for photo in self._photo_repository.list_by_folder_id(folder.id)  # type: ignore[arg-type]  # UUID | None guarantee
        }

        registered_count = 0
        updated_count = 0
        skipped_count = 0
        errors: list[str] = []

        for index, item in enumerate(scan_items, start=1):
            # ADR-041：预枚举条目已由主线程解析为真实绝对路径——worker 端
            # 跳过 per-item resolve（run #91 的段错误点）。
            photo_path = item.path if not resolve_item_paths else self._absolute_path(item.path)
            path_value = self._photo_path(photo_path)
            existing = existing_photos.get(path_value)
            if existing is not None:
                # Phase E E-5（ADR-034 D5）：重扫对账——内容变化（mtime /
                # content hash）刷新元数据；未变化者保持 skipped。读取失败
                # 或 reader 未绑定时保守视为未变化，不误更新登记。
                if self._update_if_changed(existing, photo_path):
                    updated_count += 1
                    self._report(index, total, "Updated changed photo metadata")
                else:
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
                captured_at=metadata.captured_at if metadata is not None else None,
            )
            self._photo_repository.add(photo)
            existing_photos[path_value] = photo
            registered_count += 1
            self._report(index, total, "Registered photo")

        folder.total_photos = total
        folder.scanned_photos = registered_count + updated_count + skipped_count
        self._folder_repository.add(folder)

        return ScanAndRegisterPhotosResult(
            folder_id=folder.id,
            discovered_count=total,
            registered_count=registered_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            failed_count=len(errors),
            errors=tuple(errors),
        )

    def _update_if_changed(self, photo: Photo, photo_path: Path) -> bool:
        """Refresh the registration metadata when the file content changed.

        Phase E E-5（ADR-034 D5）：比较 fresh 读与既有 metadata 的内容相关
        字段；变化则 ``PhotoRepository.update_metadata`` 刷新（只改 metadata
        列，快照列不动），返回 True。reader 缺失、读取失败或内容未变化时
        返回 False（保守：不误更新，保持 skipped 语义）。
        """
        if self._metadata_reader is None:
            return False
        try:
            fresh = self._metadata_reader.read(photo_path)
        except (OSError, ValueError, RuntimeError):
            logger.warning("Reconcile scan: failed to re-read {}, keeping existing metadata", photo_path)
            return False
        if self._metadata_unchanged(photo.metadata, fresh):
            return False
        self._photo_repository.update_metadata(photo.id, fresh)  # type: ignore[arg-type]  # UUID | None guarantee
        return True

    @staticmethod
    def _metadata_unchanged(old: PhotoMetadata | None, new: PhotoMetadata | None) -> bool:
        """Return whether content-relevant metadata is identical between reads.

        D5 语义："mtime 或 content hash 比对"。双方 content_hash 均可比时
        以 hash 为准（内容强等价）；任一方缺 hash 时退化为 mtime + file_size
        比对（弱信号，B1 回填前的历史照片适配）。
        """
        if old is None and new is None:
            return True
        if old is None or new is None:
            return False
        if old.content_hash is not None and new.content_hash is not None:
            return old.content_hash == new.content_hash
        return (
            old.modified_at == new.modified_at
            and old.file_size_bytes == new.file_size_bytes
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
