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
    ScanAndRegisterPhotosService,
    ScanPhotoFolderService,
)
from photo_archiver.application.services.archive_photos_service import (
    DEFAULT_ARCHIVE_CONFLICT_STRATEGY,
)
from photo_archiver.infrastructure import (
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


def build_application_services(repositories: ApplicationRepositories) -> ApplicationServices:
    """Build application services using runtime repositories and adapters."""
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
    )
