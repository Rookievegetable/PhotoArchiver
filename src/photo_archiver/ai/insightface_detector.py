"""InsightFace face detector backed by a pre-loaded ``FaceAnalysis`` instance.

Step 9 originally mixed model loading, filesystem probing and detection
behaviour in this module. The loading has moved to
:class:`photo_archiver.infrastructure.ai.InsightFaceLoader` so this module
now only performs the detection itself against a prepared analysis instance.
This respects DEP-050: ``ai`` depends on ``infrastructure`` for model wiring
and focuses on AI capability here.

ISSUE-001 resolution: ``detect_with_embeddings`` performs a single
``FaceAnalysis.get`` pass and returns ``FaceBoxEmbedding`` pairs so downstream
matching no longer re-detects the same image inside the recognizer. The
legacy ``detect`` method is retained for callers that only need boxes.
"""

from pathlib import Path
from typing import Any

import cv2
from insightface.app import FaceAnalysis  # type: ignore[import-untyped]
from loguru import logger

from photo_archiver.domain.value_objects import FaceBox, FaceBoxEmbedding, FaceEmbedding


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
        faces = self._read_and_detect(image)
        boxes = [_to_face_box(face) for face in faces]
        logger.debug("InsightFaceDetector found {} face(s) in {}", len(boxes), image)
        return boxes

    def detect_with_embeddings(self, image: Path) -> list[FaceBoxEmbedding]:
        """Return bounding boxes together with their embeddings from one detection pass.

        ISSUE-001 fix: InsightFace's ``FaceAnalysis.get`` already computes
        embeddings for every detected face, so extracting them at the same
        time avoids the recognizer's redundant second detection pass and
        halves the per-photo AI cost.

        Args:
            image: Absolute path to the source image file.

        Returns:
            A list of :class:`FaceBoxEmbedding` pairs, possibly empty. The
            order matches InsightFace's internal detection order for a given
            input and is consistent with :meth:`detect`.
        """
        faces = self._read_and_detect(image)
        pairs = [
            FaceBoxEmbedding(box=_to_face_box(face), embedding=_to_embedding(face))
            for face in faces
        ]
        logger.debug(
            "InsightFaceDetector detect_with_embeddings found {} face(s) in {}",
            len(pairs),
            image,
        )
        return pairs

    def _read_and_detect(self, image: Path) -> list[Any]:
        """Read the image bytes and run the model once, returning InsightFace faces.

        Shared by :meth:`detect` and :meth:`detect_with_embeddings` so the
        imread + ``analysis.get`` cost is paid exactly once per call. An
        unreadable image returns an empty list rather than raising so callers
        can treat "no face" and "unreadable" uniformly.
        """
        image_bytes = cv2.imread(str(image))
        if image_bytes is None:
            logger.warning("InsightFaceDetector could not read image: {}", image)
            return []
        return self._analysis.get(image_bytes, max_num=0)


def _to_face_box(face: Any) -> FaceBox:
    """Build a FaceBox from an InsightFace face dict."""
    bbox = face["bbox"]
    confidence = float(face["det_score"])
    return FaceBox(
        x1=int(bbox[0]),
        y1=int(bbox[1]),
        x2=int(bbox[2]),
        y2=int(bbox[3]),
        confidence=confidence,
    )


def _to_embedding(face: Any) -> FaceEmbedding:
    """Build a FaceEmbedding from an InsightFace face dict (numpy → tuple)."""
    embedding = face["embedding"]
    return FaceEmbedding(tuple(float(x) for x in embedding.tolist()))
