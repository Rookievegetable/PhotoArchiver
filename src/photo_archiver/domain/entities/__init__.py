"""Domain entities."""

from photo_archiver.domain.entities.folder import Folder
from photo_archiver.domain.entities.person import Person
from photo_archiver.domain.entities.photo import Photo
from photo_archiver.domain.entities.recognition import MatchStatus, RecognitionResult

__all__ = [
    "Folder",
    "MatchStatus",
    "Person",
    "Photo",
    "RecognitionResult",
]