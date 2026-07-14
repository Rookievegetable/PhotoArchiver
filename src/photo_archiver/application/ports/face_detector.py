"""Face detection port for discovering faces in an image."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from photo_archiver.domain.value_objects import FaceBox


@runtime_checkable
class FaceDetector(Protocol):
    """Detect faces in a source image and return their bounding boxes.

    Implementations MUST be deterministic given the same image bytes and MUST
    return an empty list (rather than raising) when no faces are found, so the
    detection step never silently swallows a "no face" result.
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
