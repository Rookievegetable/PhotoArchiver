"""Application-level service assembly."""

from dataclasses import dataclass

from photo_archiver.app.repositories import ApplicationRepositories
from photo_archiver.application import (
    ArchiveExecutor,
    ArchivePathBuilderService,
    ArchivePhotosService,
    ArchivePlanner,
    ImportPeopleService,
    RegisterPhotoService,
    ReviewRecognitionService,
    ScanAndRegisterPhotosService,
    ScanPhotoFolderService,
    SettingsService,
)
from photo_archiver.application.services.archive_photos_service import (
    DEFAULT_ARCHIVE_CONFLICT_STRATEGY,
)
from photo_archiver.infrastructure import (
    InMemoryUserSettingsStore,
    LocalPhotoFileScanner,
    PillowPhotoMetadataReader,
    SQLiteUnitOfWork,
    TxtPersonImportReader,
)


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    """Use case services assembled for application runtime."""

    import_people: ImportPeopleService
    register_photo: RegisterPhotoService
    scan_photo_folder: ScanPhotoFolderService
    scan_and_register_photos: ScanAndRegisterPhotosService
    archive_photos: ArchivePhotosService
    review_recognition: ReviewRecognitionService
    settings: SettingsService


def build_application_services(repositories: ApplicationRepositories) -> ApplicationServices:
    """Build application services using runtime repositories and adapters.

    ``ReviewRecognitionService`` is injected with the shared ``SQLiteUnitOfWork``
    so ISSUE-005 is closed: the in-memory ``approve()/reject()`` flip and the
    DB-side ``update_status`` commit atomically, mirroring ``ArchiveExecutor``.

    ``SettingsService`` uses an ``InMemoryUserSettingsStore`` here so CLI and
    CI contexts work without a Qt runtime; ``app/ui_assembly.py`` re-binds the
    desktop UI's service to a ``QSettingsUserSettingsStore`` after QSettings
    becomes available.
    """
    scanner = LocalPhotoFileScanner()
    metadata_reader = PillowPhotoMetadataReader()
    unit_of_work = SQLiteUnitOfWork(repositories._connection_provider)

    archive_path_builder = ArchivePathBuilderService()
    archive_planner = ArchivePlanner(
        path_builder=archive_path_builder,
        person_repository=repositories.people,
        photo_repository=repositories.photos,
        recognition_repository=repositories.recognition,
        archive_record_repository=repositories.archive_records,
    )
    archive_executor = ArchiveExecutor(
        repositories.archive_records,
        unit_of_work=unit_of_work,
    )
    archive_photos_service = ArchivePhotosService(
        planner=archive_planner,
        executor=archive_executor,
        default_conflict_strategy=DEFAULT_ARCHIVE_CONFLICT_STRATEGY,
    )
    review_service = ReviewRecognitionService(
        repositories.recognition,
        unit_of_work=unit_of_work,
    )
    settings_service = SettingsService(
        user_settings_store=InMemoryUserSettingsStore(),
        system_settings=None,
    )

    return ApplicationServices(
        import_people=ImportPeopleService(TxtPersonImportReader(), repositories.people),
        register_photo=RegisterPhotoService(repositories.photos, metadata_reader),
        scan_photo_folder=ScanPhotoFolderService(scanner),
        scan_and_register_photos=ScanAndRegisterPhotosService(
            scanner,
            repositories.folders,
            repositories.photos,
            metadata_reader,
            unit_of_work=unit_of_work,
        ),
        archive_photos=archive_photos_service,
        review_recognition=review_service,
        settings=settings_service,
    )
