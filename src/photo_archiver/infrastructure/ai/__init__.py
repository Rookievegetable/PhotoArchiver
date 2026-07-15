"""Infrastructure AI model loading adapters.

This package hosts technology adapters that load InsightFace model packs from
disk and configure ``FaceAnalysis`` instances. Keeping the loading here rather
than in the ``ai/`` layer respects DEP-050: ``ai`` depends on ``infrastructure``
for model wiring, and ``infrastructure`` owns filesystem access (ARC-015).
"""

from photo_archiver.infrastructure.ai.insightface_loader import (
    InsightFaceLoader,
    ModelPackMissing,
)

__all__ = ["InsightFaceLoader", "ModelPackMissing"]
