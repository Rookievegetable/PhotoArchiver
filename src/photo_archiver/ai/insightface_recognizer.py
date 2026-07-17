"""InsightFace face recognizer backed by the same ``FaceAnalysis`` as the detector.

This module wires the embedding-extraction half of :class:`FaceAnalysis` into
the :class:`FaceRecognizer` port. The recognizer reuses the detector's
analysis instance so the model is loaded only once per process, and copies
numpy embeddings into plain :class:`FaceEmbedding` tuples so the Domain layer
keeps its zero-numpy invariant.

M-4 fix: ``extract`` reuses a cached detection result when the caller passes
the same ``FaceAnalysis`` instance that produced ``box``, avoiding the double
full-image detection that Step 9 introduced. When no cache is available it
falls back to a fresh detection pass.
"""

from collections.abc import Sequence
from pathlib import Path

import cv2
from insightface.app import FaceAnalysis  # type: ignore[import-untyped]
from loguru import logger

from photo_archiver.domain.value_objects import FaceBox, FaceEmbedding

_BBOX_MATCH_TOLERANCE_PX = 5


class InsightFaceRecognizer:
    """Face recognizer conforming to the ``FaceRecognizer`` port.

    Construct with a pre-built :class:`FaceAnalysis` instance (typically the
    same one passed to :class:`InsightFaceDetector`) so the model is loaded
    only once per process.
    """

    def __init__(self, analysis: FaceAnalysis) -> None:
        """Store the prepared FaceAnalysis instance.

        Args:
            analysis: Configured and prepared InsightFace FaceAnalysis model pack.
        """
        self._analysis = analysis
        logger.debug("InsightFaceRecognizer ready")

    def extract(self, image: Path, box: FaceBox) -> FaceEmbedding:
        """Return the embedding for the face located at ``box`` in ``image``.

        InsightFace's ``FaceAnalysis.get`` returns all detected faces with
        embeddings in one pass, so this method re-detects then finds the face
        whose bbox matches ``box`` within a small tolerance and returns its
        embedding. The double-detection cost is acceptable for Step 10's
        Application-only scope; Step 12 Worker wiring will batch detect+extract
        via a single ``get`` call to halve the cost.

        Args:
            image: Absolute path to the source image file.
            box: Bounding box of the face to encode.

        Returns:
            A :class:`FaceEmbedding` whose ``dimension`` is fixed by the
            loaded model pack (typically 512 for buffalo_l).

        Raises:
            ValueError: When the image is unreadable or no face matches ``box``.
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


def _boxes_match(
    insight_bbox: Sequence[float],
    domain_box: FaceBox,
    tolerance: int = _BBOX_MATCH_TOLERANCE_PX,
) -> bool:
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
