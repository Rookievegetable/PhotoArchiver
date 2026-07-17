"""Domain value objects."""

from photo_archiver.domain.value_objects.archive_path import ArchivePath
from photo_archiver.domain.value_objects.face_box import FaceBox
from photo_archiver.domain.value_objects.face_embedding import FaceEmbedding
from photo_archiver.domain.value_objects.person_identity import PersonIdentity
from photo_archiver.domain.value_objects.photo_metadata import PhotoMetadata
from photo_archiver.domain.value_objects.photo_path import PhotoPath, PhotoPathBase

__all__ = [
    "ArchivePath",
    "FaceBox",
    "FaceEmbedding",
    "PersonIdentity",
    "PhotoMetadata",
    "PhotoPath",
    "PhotoPathBase",
]