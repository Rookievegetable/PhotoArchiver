"""Domain entities."""

from photo_archiver.domain.entities.archive import ArchiveRecord, ArchiveStatus
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
    "FaceObservation",
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