"""Application-level service assembly."""

from dataclasses import dataclass

from photo_archiver.app.repositories import ApplicationRepositories
from photo_archiver.application import (
    ImportPeopleService,
    RegisterPhotoService,
    ScanAndRegisterPhotosService,
    ScanPhotoFolderService,
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


def build_application_services(repositories: ApplicationRepositories) -> ApplicationServices:
    """Build application services using runtime repositories and adapters."""
    scanner = LocalPhotoFileScanner()
    metadata_reader = PillowPhotoMetadataReader()
    unit_of_work = SQLiteUnitOfWork(repositories._connection_provider)
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
    )
