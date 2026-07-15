"""InsightFace face detector backed by a pre-loaded ``FaceAnalysis`` instance.

Step 9 originally mixed model loading, filesystem probing and detection
behaviour in this module. The loading has moved to
:class:`photo_archiver.infrastructure.ai.InsightFaceLoader` so this module
now only performs the detection itself against a prepared analysis instance.
This respects DEP-050: ``ai`` depends on ``infrastructure`` for model wiring
and focuses on AI capability here.
"""

from collections.abc import Sequence
from pathlib import Path

import cv2
from insightface.app import FaceAnalysis  # type: ignore[import-untyped]
from loguru import logger

from photo_archiver.domain.value_objects import FaceBox


class InsightFaceDetector:
    """Face detector conforming to the ``FaceDetector`` port.

    Construct with a pre-built :class:`FaceAnalysis` instance (typically
    obtained from :class:`photo_archiver.infrastructure.ai.InsightFaceLoader`)
    so the ``ai/`` layer stays free of filesystem access and model loading.
    """

    def __init__(self, analysis: FaceAnalysis) -> None:
        """Store the prepared FaceAnalysis instance.

        Args:
            analysis: Configured and prepared InsightFace FaceAnalysis model pack.
        """
        self._analysis = analysis
        logger.debug("InsightFaceDetector ready")

    @property
    def analysis(self) -> FaceAnalysis:
        """Expose the underlying FaceAnalysis for recognizer reuse.

        Step 10 integration tests and the recognizer benefit from sharing the
        single loaded analysis instance. Exposing it as a property rather than
        letting callers peek ``_analysis`` keeps the coupling documented.
        """
        return self._analysis

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
