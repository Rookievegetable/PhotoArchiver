"""PhotoArchiver AI capabilities package.

The ``ai/`` layer only performs detection, recognition and matching against
pre-loaded model instances. Model loading and filesystem probing live in
``photo_archiver.infrastructure.ai`` per DEP-050.
"""

from photo_archiver.ai.insightface_detector import InsightFaceDetector
from photo_archiver.ai.insightface_recognizer import InsightFaceRecognizer
from photo_archiver.ai.similarity_matcher import CosinePersonMatcher

__all__ = [
    "CosinePersonMatcher",
    "InsightFaceDetector",
    "InsightFaceRecognizer",
]
