"""Face detection port for discovering faces in an image."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from photo_archiver.domain.value_objects import FaceBox, FaceBoxEmbedding


@runtime_checkable
class FaceDetector(Protocol):
    """Detect faces in a source image and return their bounding boxes.

    Implementations MUST be deterministic given the same image bytes and MUST
    return an empty list (rather than raising) when no faces are found, so the
    detection step never silently swallows a "no face" result.

    ISSUE-001 optimization: callers on the matching pipeline SHOULD prefer
    :meth:`detect_with_embeddings` so the recognizer does not re-detect the
    same image. :meth:`detect` is retained for callers that only need boxes.
    """

    def detect(self, image: Path) -> list[FaceBox]:
        """Return the bounding boxes of all faces found in ``image``.

        Args:
            image: Absolute path to the source image file.

        Returns:
            A list of :class:`FaceBox` instances, possibly empty. The order
            is implementation-defined but stable for a given input.
        """
        ...

    def detect_with_embeddings(self, image: Path) -> list[FaceBoxEmbedding]:
        """Return bounding boxes together with their embeddings from one detection pass.

        Implementations MUST compute embeddings in the same pass as detection
        so downstream matching avoids a redundant second detection (ISSUE-001).
        Empty result when no faces are found, matching :meth:`detect` semantics.

        Args:
            image: Absolute path to the source image file.

        Returns:
            A list of :class:`FaceBoxEmbedding` pairs, possibly empty. The
            order is implementation-defined but stable for a given input and
            consistent with :meth:`detect` for the same image.
        """
        ...
