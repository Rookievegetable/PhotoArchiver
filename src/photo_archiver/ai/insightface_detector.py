"""InsightFace face detector backed by the buffalo_l model pack.

This module wires :class:`insightface.app.FaceAnalysis` into the
:class:`FaceDetector` port defined in Step 8. The detector loads the model
pack from ``model_path`` (resolved against :class:`AppSettings.model_path`,
default ``resources/models``) and emits :class:`FaceBox` value objects
without leaking any InsightFace or numpy types back to the caller.

Callers MUST instantiate through :meth:`from_model_path` so the detector is
only built when the model pack actually exists on disk — otherwise a
:class:`ModelNotFound` is raised early so the Application layer can skip
detection gracefully instead of crashing inside a worker thread.
"""

from collections.abc import Sequence
from pathlib import Path
import shutil

import cv2
from insightface.app import FaceAnalysis  # type: ignore[import-untyped]
from loguru import logger

from photo_archiver.domain.exceptions import PhotoArchiverDomainError
from photo_archiver.domain.value_objects import FaceBox

_DEFAULT_MODEL_NAME = "buffalo_l"
_DEFAULT_DET_SIZE = (640, 640)
_DEFAULT_DET_THRESHOLD = 0.5


class ModelNotFound(PhotoArchiverDomainError):
    """Raised when the requested InsightFace model pack is missing on disk."""


class InsightFaceDetector:
    """Face detector conforming to the ``FaceDetector`` port.

    The constructor intentionally accepts a pre-built :class:`FaceAnalysis`
    instance rather than loading the model itself, so Step 9 unit tests can
    inject a stub analysis object without touching the filesystem. Use
    :meth:`from_model_path` for production wiring.
    """

    def __init__(
        self,
        analysis: FaceAnalysis,
        det_size: tuple[int, int] = _DEFAULT_DET_SIZE,
        det_threshold: float = _DEFAULT_DET_THRESHOLD,
    ) -> None:
        """Store the configured FaceAnalysis instance and detection parameters.

        Args:
            analysis: Configured InsightFace FaceAnalysis model pack.
            det_size: Detection input size in pixels, larger is slower but
                finds smaller faces.
            det_threshold: Minimum detection confidence kept, in ``[0.0, 1.0]``.
        """
        self._analysis = analysis
        self._det_size = det_size
        self._det_threshold = det_threshold
        self._analysis.prepare(ctx_id=0, det_thresh=det_threshold, det_size=det_size)
        logger.debug(
            "InsightFaceDetector ready (det_size={}, det_thresh={})",
            det_size,
            det_threshold,
        )

    @classmethod
    def from_model_path(
        cls,
        model_path: Path,
        name: str = _DEFAULT_MODEL_NAME,
        det_size: tuple[int, int] = _DEFAULT_DET_SIZE,
        det_threshold: float = _DEFAULT_DET_THRESHOLD,
    ) -> "InsightFaceDetector":
        """Build a detector from a model directory on disk.

        Args:
            model_path: Directory containing the InsightFace model pack. The
                pack is loaded by :class:`FaceAnalysis` from a subdirectory
                named after ``name`` (e.g. ``model_path/buffalo_l``).
            name: Model pack name recognised by InsightFace.
            det_size: Detection input size in pixels.
            det_threshold: Minimum detection confidence kept.

        Raises:
            ModelNotFound: When ``model_path`` does not exist or is empty.

        Returns:
            A configured :class:`InsightFaceDetector` instance.
        """
        if not model_path.exists() or not any(model_path.iterdir()):
            raise ModelNotFound(
                f"InsightFace model pack not found at {model_path}; run "
                "scripts/download_models.py to fetch it"
            )
        analysis = FaceAnalysis(name=name, root=str(model_path.parent))
        return cls(analysis, det_size=det_size, det_threshold=det_threshold)

    def detect(self, image: Path) -> list[FaceBox]:
        """Return the bounding boxes of all faces found in ``image``.

        Args:
            image: Absolute path to the source image file.

        Returns:
            A list of :class:`FaceBox` instances, possibly empty. The order
            matches InsightFace's internal detection order for a given input.
        """
        image_bytes = cv2.imread(str(image))
        if image_bytes is None:
            logger.warning("InsightFaceDetector could not read image: {}", image)
            return []
        faces: Sequence = self._analysis.get(image_bytes, max_num=0)
        boxes: list[FaceBox] = []
        for face in faces:
            bbox = face["bbox"]
            confidence = float(face["det_score"])
            boxes.append(
                FaceBox(
                    x1=int(bbox[0]),
                    y1=int(bbox[1]),
                    x2=int(bbox[2]),
                    y2=int(bbox[3]),
                    confidence=confidence,
                )
            )
        logger.debug("InsightFaceDetector found {} face(s) in {}", len(boxes), image)
        return boxes

    @staticmethod
    def model_available(model_path: Path, name: str = _DEFAULT_MODEL_NAME) -> bool:
        """Return whether the named model pack is present under ``model_path``.

        Used by the Application layer to decide whether to enqueue detection
        work or short-circuit with a logged warning.
        """
        return model_path.exists() and (model_path / name).exists() and bool(
            list((model_path / name).iterdir())
        )

    @staticmethod
    def cleanup_cache() -> None:
        """Remove the per-user InsightFace cache directory if present.

        InsightFace writes a ``~/.insightface`` cache when it downloads
        auxiliary data. Step 9 forbids automatic model download, so this
        helper lets bootstrap code keep the environment clean.
        """
        cache = Path.home() / ".insightface"
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)
            logger.debug("Removed InsightFace cache at {}", cache)
