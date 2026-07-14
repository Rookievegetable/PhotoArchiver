"""Stub InsightFace face detector for Step 8.

This module provides a placeholder :class:`InsightFaceDetector` that conforms
to the :class:`FaceDetector` port without loading any real model. Step 9 will
replace the ``detect`` body with an actual InsightFace / ONNX Runtime call
while keeping the same signature, so downstream callers need no changes.

The stub deliberately raises :class:`FaceDetectionUnavailable` on every
``detect`` call so no consumer can mistake the stub for a working detector
during Step 8 wiring.
"""

from pathlib import Path

from loguru import logger

from photo_archiver.domain.exceptions import PhotoArchiverDomainError
from photo_archiver.domain.value_objects import FaceBox


class FaceDetectionUnavailable(PhotoArchiverDomainError):
    """Raised when the stub detector is asked to detect faces.

    The stub cannot detect faces because no InsightFace model is loaded yet.
    Step 9 will replace this behaviour with a real detector and remove the
    raise, so callers should treat this as a temporary guard rather than a
    permanent runtime exception.
    """


class InsightFaceDetector:
    """Placeholder detector conforming to the ``FaceDetector`` port.

    The constructor intentionally accepts a ``model_path`` argument so Step 9
    can wire it to ``resources/models/`` without changing the public API. It
    logs the stub state once at construction so downstream bootstrap code can
    confirm the detector was reached.
    """

    def __init__(self, model_path: Path | None = None) -> None:
        """Initialize the stub detector without loading any model.

        Args:
            model_path: Reserved path to the InsightFace model directory, used
                by Step 9. Ignored by the stub.
        """
        self._model_path = model_path
        logger.warning(
            "InsightFaceDetector is a stub (Step 8); face detection unavailable"
        )

    def detect(self, image: Path) -> list[FaceBox]:
        """Reject detection requests while in stub mode.

        Args:
            image: Absolute path to the source image file.

        Returns:
            Nothing — always raises :class:`FaceDetectionUnavailable`.

        Raises:
            FaceDetectionUnavailable: Always, until Step 9 wires the real model.
        """
        raise FaceDetectionUnavailable(
            "Face detection is unavailable in stub mode; Step 9 will load the model"
        )
