"""Single-photo AI work item for the traceable recognition pipeline.

This task is deliberately free of repository writes.  It is submitted to a
ThreadPoolExecutor by :class:`RunRecognitionService`; all database writes are
performed by the consuming/main thread.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from photo_archiver.domain import FaceBoxEmbedding
from photo_archiver.domain.exceptions import ImageUnreadableError


class FaceAnalysisDetector(Protocol):
    def detect_with_embeddings(self, image: Path) -> list[FaceBoxEmbedding]: ...


@dataclass(frozen=True, slots=True)
class FaceAnalysisResult:
    """Pure result of analyzing one photo, including item-level failure."""

    photo_id: UUID
    faces: tuple[FaceBoxEmbedding, ...] = ()
    unreadable: bool = False
    error: str | None = None


class FaceAnalysisTask:
    """Callable adapter that isolates detector failures to one photo."""

    def __init__(self, detector: FaceAnalysisDetector) -> None:
        self._detector = detector

    def __call__(self, photo_id: UUID, image: Path) -> FaceAnalysisResult:
        try:
            faces = tuple(self._detector.detect_with_embeddings(image))
        except ImageUnreadableError as exc:
            return FaceAnalysisResult(photo_id, unreadable=True, error=str(exc))
        except Exception as exc:  # single-photo failure isolation
            return FaceAnalysisResult(photo_id, error=str(exc))
        return FaceAnalysisResult(photo_id=photo_id, faces=faces)
