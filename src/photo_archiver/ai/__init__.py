"""PhotoArchiver AI capabilities package."""

from photo_archiver.ai.insightface_detector import (
    InsightFaceDetector,
    ModelNotFound,
)
from photo_archiver.ai.insightface_recognizer import InsightFaceRecognizer
from photo_archiver.ai.similarity_matcher import CosinePersonMatcher

__all__ = [
    "CosinePersonMatcher",
    "InsightFaceDetector",
    "InsightFaceRecognizer",
    "ModelNotFound",
]
