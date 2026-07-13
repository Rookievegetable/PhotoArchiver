"""Content hash calculator for duplicate photo detection during archival."""

from pathlib import Path
import hashlib


class ContentHashCalculator:
    """Compute a stable content hash for a photo file.

    Uses SHA-256 over the raw file bytes so identical files at different paths
    collapse to the same hash, supporting duplicate detection in the archival
    workflow (roadmap Step 11).
    """

    CHUNK_SIZE = 65536

    def calculate(self, source: Path) -> str:
        """Return the SHA-256 hex digest of the source file bytes.

        Args:
            source: Absolute path to the file to hash.

        Raises:
            FileNotFoundError: If the source file does not exist.
            OSError: If the file cannot be read.
        """
        digest = hashlib.sha256()
        with Path(source).open("rb") as handle:
            for chunk in iter(lambda: handle.read(self.CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest()
