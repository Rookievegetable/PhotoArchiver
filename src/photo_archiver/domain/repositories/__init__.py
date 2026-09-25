"""Domain repository interfaces."""

from photo_archiver.domain.repositories.archive_record_repository import ArchiveRecordRepository
from photo_archiver.domain.repositories.face_embedding_repository import FaceEmbeddingRepository
from photo_archiver.domain.repositories.face_cluster_repository import FaceClusterRepository
from photo_archiver.domain.repositories.face_observation_repository import FaceObservationRepository
from photo_archiver.domain.repositories.folder_repository import FolderRepository
from photo_archiver.domain.repositories.import_batch_repository import ImportBatchRepository
from photo_archiver.domain.repositories.person_repository import PersonRepository
from photo_archiver.domain.repositories.photo_repository import PhotoRepository
from photo_archiver.domain.repositories.recognition_repository import RecognitionRepository
from photo_archiver.domain.repositories.recognition_run_repository import RecognitionRunRepository

__all__ = [
    "ArchiveRecordRepository",
    "FaceClusterRepository",
    "FaceEmbeddingRepository",
    "FaceObservationRepository",
    "FolderRepository",
    "ImportBatchRepository",
    "PersonRepository",
    "PhotoRepository",
    "RecognitionRepository",
    "RecognitionRunRepository",
]