"""Application-level service assembly."""

from dataclasses import dataclass

from photo_archiver.app.repositories import ApplicationRepositories
from photo_archiver.application import (
    ArchiveExecutor,
    ArchivePathBuilderService,
    ArchivePhotosService,
    ArchivePlanner,
    BackfillContentHashService,
    DetectDuplicatesService,
    ExportService,
    ImportPeopleService,
    ListPersonsService,
    MatchPersonsService,
    RegisterPhotoService,
    ReviewRecognitionService,
    ScanAndRegisterPhotosService,
    ScanPhotoFolderService,
    SearchPhotosService,
    SettingsService,
)
from photo_archiver.infrastructure import (
    DispatchingPersonImportReader,
    ExcelPersonImportReader,
    InMemoryUserSettingsStore,
    LocalPhotoFileScanner,
    PillowPhotoMetadataReader,
    SQLiteUnitOfWork,
    TxtPersonImportReader,
)
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.infrastructure.image import ContentHashCalculator


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    """Use case services assembled for application runtime."""

    import_people: ImportPeopleService
    register_photo: RegisterPhotoService
    scan_photo_folder: ScanPhotoFolderService
    scan_and_register_photos: ScanAndRegisterPhotosService
    match_persons: MatchPersonsService
    archive_photos: ArchivePhotosService
    review_recognition: ReviewRecognitionService
    settings: SettingsService
    export: ExportService
    detect_duplicates: DetectDuplicatesService
    backfill_content_hash: BackfillContentHashService
    search_photos: SearchPhotosService
    list_persons: ListPersonsService


def build_application_services(
    repositories: ApplicationRepositories,
    settings: AppSettings,
) -> ApplicationServices:
    """Build application services using runtime repositories and adapters.

    ``MatchPersonsService`` wires the recognition pipeline (detector → recognizer
    → matcher → face_embedding / recognition repos) that Step 8-10 shipped but
    never assembled. The matcher receives ``settings.match_threshold`` so the
    Step 13 system-level bound is honored at runtime, not only validated.

    ``ReviewRecognitionService`` is injected with the shared ``SQLiteUnitOfWork``
    so ISSUE-005 is closed: the in-memory ``approve()/reject()`` flip and the
    DB-side ``update_status`` commit atomically, mirroring ``ArchiveExecutor``.

    ``SettingsService`` uses an ``InMemoryUserSettingsStore`` here so CLI and
    CI contexts work without a Qt runtime; ``app/ui_assembly.py`` re-binds the
    desktop UI's service to a ``QSettingsUserSettingsStore`` after QSettings
    becomes available.

    Model pack availability: ``InsightFaceLoader`` raises ``ModelPackMissing``
    when the model directory is absent or empty. We catch that and construct a
    ``MatchPersonsService`` with placeholder ports so the UI still boots (Scan /
    Import / Archive / Settings all work without recognition); the Match action
    surfaces the error to the user. This keeps dev / CI environments without the
    ~500MB model pack runnable for every other feature.
    """
    scanner = LocalPhotoFileScanner()
    # B1 重复图片检测：向 PillowPhotoMetadataReader 注入 ContentHashCalculator，
    # 让注册照片的同一 pass 内顺手算 SHA-256 填 PhotoMetadata.content_hash。既有
    # CLI/单测路径未注入 hasher 时 reader 不算哈希保持向后兼容——生产装配在此注入。
    metadata_reader = PillowPhotoMetadataReader(
        content_hasher=ContentHashCalculator(),
        # P2-002 fix: propagate the decompression-bomb guard from settings so
        # oversized images are refused with a clear per-photo error instead of
        # exhausting memory during scans.
        max_image_pixels=settings.max_image_pixels,
    )
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
        default_conflict_strategy=settings.archive_conflict_strategy,
    )
    review_service = ReviewRecognitionService(
        repositories.recognition,
        unit_of_work=unit_of_work,
    )
    settings_service = SettingsService(
        user_settings_store=InMemoryUserSettingsStore(),
        system_settings=None,
    )
    match_service = _build_match_service(repositories, settings)
    export_service = ExportService(
        person_repository=repositories.people,
        photo_repository=repositories.photos,
        recognition_repository=repositories.recognition,
        archive_record_repository=repositories.archive_records,
    )
    detect_duplicates_service = DetectDuplicatesService(repositories.photos)
    # 一次性回填服务复用已注入 hasher 的 metadata_reader，
    # 让历史 NULL 哈希照片经 CLI 子命令补齐。reader 装配含 ContentHashCalculator
    # （上文已注入），故本服务调 reader.read 即可拿到含哈希的 fresh metadata。
    backfill_content_hash_service = BackfillContentHashService(
        repositories.photos,
        metadata_reader,
    )
    search_photos_service = SearchPhotosService(repositories.photos)
    # Phase 9 FEAT-P9-2: read-only person catalog for the FilterBar person axis
    # (Presentation never touches the repository directly — DEP-003/DEP-004).
    list_persons_service = ListPersonsService(repositories.people)

    return ApplicationServices(
        # P0-3: extension dispatch routes .xlsx/.xlsm to the openpyxl reader —
        # before this wiring only the TXT reader was injected and the import
        # UI's Excel option fed binary workbooks to the csv parser.
        import_people=ImportPeopleService(
            DispatchingPersonImportReader(
                excel_reader=ExcelPersonImportReader(),
                text_reader=TxtPersonImportReader(),
            ),
            repositories.people,
        ),
        register_photo=RegisterPhotoService(repositories.photos, metadata_reader),
        scan_photo_folder=ScanPhotoFolderService(scanner),
        scan_and_register_photos=ScanAndRegisterPhotosService(
            scanner,
            repositories.folders,
            repositories.photos,
            metadata_reader,
            unit_of_work=unit_of_work,
        ),
        match_persons=match_service,
        archive_photos=archive_photos_service,
        review_recognition=review_service,
        settings=settings_service,
        export=export_service,
        detect_duplicates=detect_duplicates_service,
        backfill_content_hash=backfill_content_hash_service,
        search_photos=search_photos_service,
        list_persons=list_persons_service,
    )


def _build_match_service(
    repositories: ApplicationRepositories,
    settings: AppSettings,
) -> MatchPersonsService:
    """Assemble the recognition pipeline, falling back when the model pack is absent.

    Imported lazily so CLI / CI / unit-test contexts that never call Match do not
    pay the ~3s InsightFace import + model prepare cost, and so environments
    without the model pack do not crash at bootstrap. The Match service is
    constructed against the real InsightFace detector / recognizer only when
    the pack is available; otherwise a placeholder service raises
    ``ModelPackMissing`` on first execute() so the UI can surface the error
    honestly rather than crashing startup.
    """
    from photo_archiver.ai import InsightFaceDetector, InsightFaceRecognizer
    from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
    from photo_archiver.infrastructure.ai import InsightFaceLoader

    loader = InsightFaceLoader(model_root=settings.model_path)
    if not loader.is_available():
        return _UnavailableMatchService(
            ModelPackMissing(
                f"InsightFace model pack not found at {loader.pack_path}; "
                "run scripts/download_models.py to fetch it"
            )
        )
    analysis = loader.load()
    detector = InsightFaceDetector(analysis)
    recognizer = InsightFaceRecognizer(analysis)
    matcher = CosinePersonMatcher(threshold=settings.match_threshold)
    return MatchPersonsService(
        detector=detector,
        recognizer=recognizer,
        matcher=matcher,
        face_embedding_repository=repositories.face_embeddings,
        recognition_repository=repositories.recognition,
        max_workers=settings.max_workers,
    )


class ModelPackMissing(Exception):
    """Raised when the InsightFace model pack is absent and Match cannot run."""


class _UnavailableMatchService(MatchPersonsService):
    """Placeholder MatchPersonsService that raises on execute() when model pack is absent.

    Subclassing MatchPersonsService keeps the ApplicationServices dataclass field
    type honest (callers get a MatchPersonsService, not a Union). The constructor
    bypasses real detector/recognizer/matcher wiring by passing lightweight
    stand-ins; only execute() is overridden to raise the captured ModelPackMissing.
    """

    def __init__(self, error: ModelPackMissing) -> None:
        """Store the error to raise on execute(); wire stand-in ports to satisfy base."""
        from uuid import uuid4

        from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
        from photo_archiver.application.dtos import MatchResult

        # Stand-in ports never exercised because execute() is overridden to raise.
        class _NoOpDetector:
            def detect(self, image):  # noqa: ANN001
                return []

        class _NoOpRecognizer:
            def extract(self, image, box):  # noqa: ANN001
                return None

        super().__init__(
            detector=_NoOpDetector(),  # type: ignore[arg-type]
            recognizer=_NoOpRecognizer(),  # type: ignore[arg-type]
            matcher=CosinePersonMatcher(threshold=-1.0),
            face_embedding_repository=_NoOpFaceEmbeddingRepository(),  # type: ignore[arg-type]  # mock repo
            recognition_repository=_NoOpRecognitionRepository(),  # type: ignore[arg-type]  # mock repo
        )
        self._error = error
        self._MatchResult = MatchResult  # keep import reachable for type checks
        self._uuid4 = uuid4

    def execute(self, command):  # noqa: ANN001
        """Raise the captured ModelPackMissing so the UI surfaces it honestly."""
        raise self._error


class _NoOpFaceEmbeddingRepository:
    """Stand-in repository returning empty candidates so base __init__ survives."""

    def list_all(self) -> dict:
        """Return empty mapping; never exercised because execute() raises."""
        return {}


class _NoOpRecognitionRepository:
    """Stand-in repository accepting add() so base __init__ survives."""

    def add(self, result) -> None:
        """No-op; never exercised because execute() raises."""

    def add_many(self, results) -> None:
        """No-op batch variant kept symmetric with ``add``."""
