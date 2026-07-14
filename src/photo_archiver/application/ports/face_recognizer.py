"""Face recognition port for extracting face embeddings."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from photo_archiver.domain.value_objects import FaceBox, FaceEmbedding


@runtime_checkable
class FaceRecognizer(Protocol):
    """Extract a face embedding from a cropped face region.

    The recognizer takes a source image and a previously detected
    :class:`FaceBox` and returns the corresponding :class:`FaceEmbedding`.
    Implementations MUST normalize embeddings so cosine-similarity matching
    in Step 10 produces comparable scores.
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
