"""Domain value objects."""

from photo_archiver.domain.value_objects.archive_path import ArchivePath
from photo_archiver.domain.value_objects.face_box import FaceBox
from photo_archiver.domain.value_objects.face_box_embedding import FaceBoxEmbedding
from photo_archiver.domain.value_objects.face_embedding import FaceEmbedding
from photo_archiver.domain.value_objects.person_identity import PersonIdentity
from photo_archiver.domain.value_objects.photo_metadata import PhotoMetadata
from photo_archiver.domain.value_objects.photo_path import PhotoPath, PhotoPathBase
from photo_archiver.domain.value_objects.photo_search_criteria import PhotoSearchCriteria

__all__ = [
    "ArchivePath",
    "FaceBox",
    "FaceBoxEmbedding",
    "FaceEmbedding",
    "PersonIdentity",
    "PhotoMetadata",
    "PhotoPath",
    "PhotoPathBase",
    "PhotoSearchCriteria",
]