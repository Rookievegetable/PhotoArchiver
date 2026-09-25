"""Domain entities."""

from photo_archiver.domain.entities.archive import ArchiveRecord, ArchiveStatus
from photo_archiver.domain.entities.face_cluster import (
    CLUSTER_STATUS_CONFIRMED,
    CLUSTER_STATUS_IGNORED,
    CLUSTER_STATUS_MERGED,
    CLUSTER_STATUS_PENDING,
    CLUSTER_STATUS_SPLIT,
    CLUSTER_STATUS_UNKNOWN,
    CLUSTER_STATUSES,
    CLUSTER_RUN_STATUSES,
    CLUSTER_RUN_STATUS_CANCELLED,
    CLUSTER_RUN_STATUS_COMPLETED,
    CLUSTER_RUN_STATUS_CREATED,
    CLUSTER_RUN_STATUS_FAILED,
    CLUSTER_RUN_STATUS_RUNNING,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    MEMBER_SOURCES,
    MEMBER_SOURCE_AUTO,
    MEMBER_SOURCE_MANUAL,
)
from photo_archiver.domain.entities.face_observation import (
    FaceObservation,
    SCOPE_VERDICT_IN_SELECTED_SCOPE,
    SCOPE_VERDICT_OUT_OF_SELECTED_SCOPE,
    classify_scope,
)
from photo_archiver.domain.entities.folder import Folder
from photo_archiver.domain.entities.import_batch import (
    BATCH_STATUS_CANCELLED,
    BATCH_STATUS_CONFIRMED,
    BATCH_STATUS_DRAFT,
    DRAFT_ACTION_CREATE,
    DRAFT_ACTION_MERGE_EXISTING,
    DRAFT_ACTION_SKIP,
    ImportBatch,
    ImportDraftRow,
)
from photo_archiver.domain.entities.person import Person
from photo_archiver.domain.entities.photo import Photo
from photo_archiver.domain.entities.recognition import MatchStatus, RecognitionResult
from photo_archiver.domain.entities.recognition_run import (
    RecognitionRun,
    RecognitionRunStats,
    RunPhotoSnapshot,
)

__all__ = [
    "ArchiveRecord",
    "ArchiveStatus",
    "BATCH_STATUS_CANCELLED",
    "BATCH_STATUS_CONFIRMED",
    "BATCH_STATUS_DRAFT",
    "DRAFT_ACTION_CREATE",
    "DRAFT_ACTION_MERGE_EXISTING",
    "DRAFT_ACTION_SKIP",
    "CLUSTER_STATUSES",
    "CLUSTER_STATUS_CONFIRMED",
    "CLUSTER_STATUS_IGNORED",
    "CLUSTER_STATUS_MERGED",
    "CLUSTER_STATUS_PENDING",
    "CLUSTER_STATUS_SPLIT",
    "CLUSTER_STATUS_UNKNOWN",
    "CLUSTER_RUN_STATUSES",
    "CLUSTER_RUN_STATUS_CANCELLED",
    "CLUSTER_RUN_STATUS_COMPLETED",
    "CLUSTER_RUN_STATUS_CREATED",
    "CLUSTER_RUN_STATUS_FAILED",
    "CLUSTER_RUN_STATUS_RUNNING",
    "FaceCluster",
    "FaceClusterMember",
    "FaceClusterRun",
    "FaceObservation",
    "MEMBER_SOURCES",
    "MEMBER_SOURCE_AUTO",
    "MEMBER_SOURCE_MANUAL",
    "SCOPE_VERDICT_IN_SELECTED_SCOPE",
    "SCOPE_VERDICT_OUT_OF_SELECTED_SCOPE",
    "classify_scope",
    "Folder",
    "ImportBatch",
    "ImportDraftRow",
    "MatchStatus",
    "Person",
    "Photo",
    "RecognitionResult",
    "RecognitionRun",
    "RecognitionRunStats",
    "RunPhotoSnapshot",
]