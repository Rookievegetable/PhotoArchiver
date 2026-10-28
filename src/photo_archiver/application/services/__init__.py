"""Application service implementations for use case boundaries."""

from photo_archiver.application.services.archive_executor import ArchiveExecutor
from photo_archiver.application.services.archive_path_builder_service import ArchivePathBuilderService
from photo_archiver.application.services.archive_photos_service import ArchivePhotosService
from photo_archiver.application.services.archive_planner import ArchivePlanner
from photo_archiver.application.services.backfill_capture_time_service import BackfillCaptureTimeService
from photo_archiver.application.services.backfill_content_hash_service import BackfillContentHashService
from photo_archiver.application.services.confirm_import_service import ConfirmImportService
from photo_archiver.application.services.delete_person_service import DeletePersonService
from photo_archiver.application.services.delete_photos_service import DeletePhotosService
from photo_archiver.application.services.detect_duplicates_service import DetectDuplicatesService
from photo_archiver.application.services.parse_import_draft_service import ParseImportDraftService
from photo_archiver.application.services.dispose_duplicates_service import DisposeDuplicatesService
from photo_archiver.application.services.export_service import ExportService
from photo_archiver.application.services.import_people_service import ImportPeopleService
from photo_archiver.application.services.list_persons_service import ListPersonsService
from photo_archiver.application.services.manage_people_service import ManagePeopleService
from photo_archiver.application.services.match_persons_service import MatchPersonsService
from photo_archiver.application.services.face_analysis_task import FaceAnalysisTask
from photo_archiver.application.services.cluster_faces_service import ClusterFacesService
from photo_archiver.application.services.backfill_historical_people_service import (
    BackfillHistoricalPeopleService,
)
from photo_archiver.application.services.cluster_results_service import ClusterResultsService
from photo_archiver.application.services.roster_cluster_stats_service import (
    RosterClusterStatsService,
)
from photo_archiver.application.services.recognition_failure_service import RecognitionFailureService
from photo_archiver.application.services.list_recognition_runs_service import ListRecognitionRunsService
from photo_archiver.application.services.pairing_workbench_service import PairingWorkbenchService
from photo_archiver.application.services.photo_ignore_service import PhotoIgnoreService
from photo_archiver.application.services.suggest_pairings_service import SuggestPairingsService
from photo_archiver.application.services.run_recognition_service import RunRecognitionService
from photo_archiver.application.services.plugin_context_service import PluginContextService
from photo_archiver.application.services.cleanup_thumbnail_cache_service import (
    CleanupThumbnailCacheService,
)
from photo_archiver.application.services.prune_missing_photos_service import PruneMissingPhotosService
from photo_archiver.application.services.reference_eligibility_service import ReferenceEligibilityService
from photo_archiver.application.services.reference_intake_service import ReferenceIntakeService
from photo_archiver.application.services.prediction_artifact_service import PredictionArtifactService
from photo_archiver.application.services.reference_snapshot_service import ReferenceSnapshotService
from photo_archiver.application.services.register_photo_service import RegisterPhotoService
from photo_archiver.application.services.review_recognition_service import ReviewRecognitionService
from photo_archiver.application.services.scan_and_register_photos_service import ScanAndRegisterPhotosService
from photo_archiver.application.services.scan_photo_folder_service import ScanPhotoFolderService
from photo_archiver.application.services.search_photos_service import SearchPhotosService
from photo_archiver.application.services.settings_service import SettingsService

from photo_archiver.application.services.workspace_readiness import WorkspaceReadinessService

__all__ = [
    "WorkspaceReadinessService",
    "ArchiveExecutor",
    "ArchivePathBuilderService",
    "ArchivePhotosService",
    "ArchivePlanner",
    "BackfillCaptureTimeService",
    "BackfillContentHashService",
    "DeletePersonService",
    "DeletePhotosService",
    "DetectDuplicatesService",
    "DisposeDuplicatesService",
    "ConfirmImportService",
    "ExportService",
    "ImportPeopleService",
    "ListPersonsService",
    "ManagePeopleService",
    "MatchPersonsService",
    "ClusterFacesService",
    "BackfillHistoricalPeopleService",
    "ClusterResultsService",
    "RosterClusterStatsService",
    "RecognitionFailureService",
    "ListRecognitionRunsService",
    "PairingWorkbenchService",
    "PhotoIgnoreService",
    "SuggestPairingsService",
    "RunRecognitionService",
    "FaceAnalysisTask",
    "ParseImportDraftService",
    "PluginContextService",
    "CleanupThumbnailCacheService",
    "PruneMissingPhotosService",
    "ReferenceEligibilityService",
    "ReferenceIntakeService",
    "PredictionArtifactService",
    "ReferenceSnapshotService",
    "RegisterPhotoService",
    "ReviewRecognitionService",
    "ScanAndRegisterPhotosService",
    "ScanPhotoFolderService",
    "SearchPhotosService",
    "SettingsService",
]