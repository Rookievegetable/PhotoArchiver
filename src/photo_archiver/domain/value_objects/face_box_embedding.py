"""Face box plus embedding value object — single-detection result pair.

ISSUE-001 resolution: the Match pipeline used to detect faces and then
re-detect inside the recognizer just to extract the matching embedding,
doubling AI cost per photo. The new ``detect_with_embeddings`` path returns
``FaceBoxEmbedding`` pairs from a single InsightFace ``analysis.get()`` call,
so the Domain layer has a typed carrier for the combined result that keeps
the Application service free of numpy/Insightface coupling.
"""

from dataclasses import dataclass

from photo_archiver.domain.value_objects.face_box import FaceBox
from photo_archiver.domain.value_objects.face_embedding import FaceEmbedding


@dataclass(frozen=True, slots=True)
class FaceBoxEmbedding:
    """Bind a detected face box with its already-extracted embedding.

    Holding the pair as an immutable Domain value object lets the Application
    layer thread the single-detection result through the matching pipeline
    without re-touching the AI layer, halving the per-photo AI cost
    (ISSUE-001). Both fields are themselves Domain value objects, so this
    type stays framework-free per ADR-003/ADR-015.
    """

    box: FaceBox
    embedding: FaceEmbedding
