"""InsightFace face recognizer backed by the same model pack as the detector.

This module wires the embedding-extraction half of :class:`FaceAnalysis` into
the :class:`FaceRecognizer` port defined in Step 8. Each detected face's
``embedding`` (a numpy array inside the InsightFace ``Face`` dict) is copied
into a plain :class:`FaceEmbedding` so the Domain layer keeps its zero-numpy
invariant.

The recognizer intentionally re-uses the detector's :class:`FaceAnalysis`
instance rather than building its own, because InsightFace loads the
recognition model pack together with detection — building a second
FaceAnalysis would double the model memory footprint.
"""

from pathlib import Path
from collections.abc import Sequence

import cv2
from insightface.app import FaceAnalysis  # type: ignore[import-untyped]
from loguru import logger

from photo_archiver.domain.value_objects import FaceBox, FaceEmbedding


class InsightFaceRecognizer:
    """Face recognizer conforming to the ``FaceRecognizer`` port.

    Construct with a pre-built :class:`FaceAnalysis` instance (typically the
    same one passed to :class:`InsightFaceDetector`) so the model is loaded
    only once per process.
    """

    def __init__(self, analysis: FaceAnalysis) -> None:
        """Store the configured FaceAnalysis instance.

        Args:
            analysis: Configured InsightFace FaceAnalysis model pack, with
                ``prepare`` already called by the caller.
        """
        self._analysis = analysis
        logger.debug("InsightFaceRecognizer ready")

    def extract(self, image: Path, box: FaceBox) -> FaceEmbedding:
        """Return the embedding for the face located at ``box`` in ``image``.

        InsightFace's ``FaceAnalysis.get`` returns all detected faces at
        once, so this method re-detects then finds the face whose bbox
        matches ``box`` (within a small tolerance) and returns its embedding.
        Step 10 may optimise by passing a batch of boxes; the current shape
        matches the :class:`FaceRecognizer` port.

        Args:
            image: Absolute path to the source image file.
            box: Bounding box of the face to encode.

        Returns:
            A :class:`FaceEmbedding` whose ``dimension`` is fixed by the
            loaded model pack (typically 512 for buffalo_l).

        Raises:
            ValueError: When no face in ``image`` matches ``box`` closely
                enough — the caller should treat this as a stale detection.
        """
        image_bytes = cv2.imread(str(image))
        if image_bytes is None:
            logger.warning("InsightFaceRecognizer could not read image: {}", image)
            raise ValueError(f"unreadable image: {image}")
        faces: Sequence = self._analysis.get(image_bytes, max_num=0)
        for face in faces:
            bbox = face["bbox"]
            if _boxes_match(bbox, box):
                embedding = face["embedding"]
                return FaceEmbedding(tuple(float(x) for x in embedding.tolist()))
        raise ValueError(f"no face in {image} matches box {box}")

    @staticmethod
    def embedding_dimension() -> int:
        """Return the embedding dimension produced by buffalo_l."""
        return 512


def _boxes_match(insight_bbox: Sequence[float], domain_box: FaceBox, tolerance: int = 5) -> bool:
    """Return whether an InsightFace bbox and a Domain FaceBox refer to the same face.

    InsightFace bboxes are ``[x1, y1, x2, y2]`` floats with the same origin
    convention as :class:`FaceBox`, so a small per-coordinate tolerance
    absorbs rounding differences from detection input resizing.
    """
    return (
        abs(int(insight_bbox[0]) - domain_box.x1) <= tolerance
        and abs(int(insight_bbox[1]) - domain_box.y1) <= tolerance
        and abs(int(insight_bbox[2]) - domain_box.x2) <= tolerance
        and abs(int(insight_bbox[3]) - domain_box.y2) <= tolerance
    )
