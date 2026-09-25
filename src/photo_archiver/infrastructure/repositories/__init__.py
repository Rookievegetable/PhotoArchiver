"""Repository infrastructure implementations."""

from photo_archiver.infrastructure.repositories.in_memory_face_cluster_repository import (
    InMemoryFaceClusterRepository,
)
from photo_archiver.infrastructure.repositories.in_memory_folder_repository import (
    InMemoryFolderRepository,
)
from photo_archiver.infrastructure.repositories.in_memory_face_observation_repository import (
    InMemoryFaceObservationRepository,
)
from photo_archiver.infrastructure.repositories.in_memory_recognition_run_repository import (
    InMemoryRecognitionRunRepository,
)
from photo_archiver.infrastructure.repositories.in_memory_person_repository import (
    InMemoryPersonRepository,
)
from photo_archiver.infrastructure.repositories.in_memory_photo_repository import InMemoryPhotoRepository

__all__ = [
    "InMemoryFaceClusterRepository",
    "InMemoryFaceObservationRepository",
    "InMemoryFolderRepository",
    "InMemoryRecognitionRunRepository",
    "InMemoryPersonRepository",
    "InMemoryPhotoRepository",
]