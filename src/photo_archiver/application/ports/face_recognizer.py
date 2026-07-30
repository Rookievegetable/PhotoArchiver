"""Face recognition port for extracting face embeddings."""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from photo_archiver.domain.value_objects import FaceBox, FaceEmbedding


@runtime_checkable
class FaceRecognizer(Protocol):
    """Extract a face embedding from a cropped face region.

    The recognizer takes a source image and a previously detected
    :class:`FaceBox` and returns the corresponding :class:`FaceEmbedding`.
    Implementations MUST normalize embeddings so cosine-similarity matching
    in Step 10 produces comparable scores.

    ISSUE-001 optimization: callers on the matching pipeline SHOULD prefer
    :meth:`extract_from` with faces from
    :meth:`FaceDetector.detect_with_embeddings` so the recognizer does not
    re-detect the same image. :meth:`extract` is retained for callers that
    only hold an image path + box.
    """

    def extract(self, image: Path, box: FaceBox) -> FaceEmbedding:
        """Return the embedding for the face located at ``box`` in ``image``.

        Args:
            image: Absolute path to the source image file.
            box: Bounding box of the face to encode.

        Returns:
            A :class:`FaceEmbedding` whose ``dimension`` is fixed for a given
            recognizer implementation.
        """
        ...

    def extract_from(self, box: FaceBox, faces: Any) -> FaceEmbedding:
        """Return the embedding for ``box`` from an already-detected face list.

        Reuses the detector's detection pass so the recognizer no longer
        re-detects the image (ISSUE-001). ``faces`` is the face sequence
        produced by the detector's underlying ``FaceAnalysis.get`` call or a
        compatible stub carrying ``bbox`` and ``embedding`` entries.

        Args:
            box: Bounding box of the face to encode.
            faces: Pre-detected face dicts from the detector.

        Returns:
            The :class:`FaceEmbedding` for the face matching ``box``.

        Raises:
            ValueError: When no face in ``faces`` matches ``box``.
        """
        ...
