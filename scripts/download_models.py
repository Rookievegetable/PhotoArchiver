"""PhotoArchiver model fetcher.

Downloads the InsightFace ``buffalo_l`` model pack into
``resources/models/`` so :class:`photo_archiver.ai.InsightFaceDetector`
can load it without an automatic download at runtime.

Usage::

    python scripts/download_models.py                     # default buffalo_l
    python scripts/download_models.py --name antelopev2  # alternate pack

Integrity (P2-007): the downloaded zip is verified before extraction. When a
SHA-256 digest is pinned in ``EXPECTED_SHA256`` (or given via ``--sha256``) it
must match exactly or the script refuses to extract. While a pack has no
pinned digest the script refuses as well — pass ``--allow-unverified`` as a
first-bootstrap escape hatch, then pin the computed digest printed by the log.

The model files are intentionally **not** committed to git (see
``.gitignore``). CI pipelines should run this script before invoking
integration tests that exercise the real detector.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_ROOT = ROOT / "resources" / "models"
DEFAULT_MODEL_NAME = "buffalo_l"

# InsightFace publishes model packs as GitHub release assets. The URL below
# is the canonical buffalo_l archive published by deepinsight/insightface.
# antelopev2 and other packs live under the same release; pass --url to
# override for mirrors or alternate packs.
DEFAULT_MODEL_URL = (
    "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
)

# P2-007 (Phase 3 audit): integrity pinning. Map pack name -> the official
# SHA-256 hex digest of its release zip. An empty string means "not pinned
# yet": the script then refuses to extract unless ``--allow-unverified`` is
# passed (first-bootstrap escape hatch). Pin the digest printed by the log
# after verifying provenance once; CI must drop ``--allow-unverified`` then.
EXPECTED_SHA256: dict[str, str] = {
    # P0-8 (Phase B): buffalo_l pinned. Digest computed from an archive
    # fetched from the canonical release URL below; cross-checked against
    # third-party LFS mirrors of the same asset and against the extracted
    # pack that CI has been running the AI suite with.
    "buffalo_l": "80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f",
    "antelopev2": "",
}


def download(url: str, target: Path) -> None:
    """Stream ``url`` to ``target`` with a progress log."""
    logger.info("Downloading model pack from {}", url)
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, open(target, "wb") as out_file:
        shutil.copyfileobj(response, out_file)
    logger.info("Saved model pack to {} ({} bytes)", target, target.stat().st_size)


def sha256_of(path: Path) -> str:
    """Return the SHA-256 hex digest of ``path`` (streamed, constant memory)."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_integrity(
    zip_path: Path,
    name: str,
    expected_sha256: str | None,
    allow_unverified: bool,
) -> bool:
    """Verify the downloaded zip against a pinned SHA-256 digest.

    Returns ``True`` when verification passed. When no digest is pinned
    (neither in ``EXPECTED_SHA256`` nor via ``--sha256``) the download is
    unverified: extraction is refused unless ``allow_unverified`` is set.

    Always logs the computed digest so operators can pin it after checking
    provenance once.
    """
    computed = sha256_of(zip_path)
    logger.info("SHA-256 ({}): {}", name, computed)

    if expected_sha256 is None:
        expected_sha256 = EXPECTED_SHA256.get(name, "").strip().lower() or None

    if expected_sha256 is None:
        if allow_unverified:
            logger.warning(
                "No SHA-256 pinned for '{}' — proceeding UNVERIFIED via --allow-unverified. "
                "Pin the digest above in EXPECTED_SHA256 afterwards.",
                name,
            )
            return True
        logger.error(
            "No SHA-256 digest pinned for '{}' (computed {}). "
            "Refusing to extract untrusted archive. Pass --allow-unverified for the "
            "first bootstrap, then pin the digest in EXPECTED_SHA256.",
            name,
            computed,
        )
        return False

    if computed != expected_sha256.strip().lower():
        logger.error(
            "SHA-256 mismatch for '{}': expected {}, got {}. Archive rejected.",
            name,
            expected_sha256,
            computed,
        )
        return False

    logger.info("SHA-256 verified for '{}'", name)
    return True


def extract(zip_path: Path, dest_root: Path, name: str) -> Path:
    """Extract the model zip into ``dest_root`` and return the pack directory."""
    import zipfile

    pack_dir = dest_root / name
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(pack_dir)
    logger.info("Extracted model pack into {}", pack_dir)
    return pack_dir


def main() -> int:
    """Entry point: parse args, download, extract, verify."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--name",
        default=DEFAULT_MODEL_NAME,
        help="Model pack name (default: %(default)s)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_MODEL_URL,
        help="Model pack download URL (default: %(default)s)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_MODEL_ROOT,
        help="Destination model root directory (default: %(default)s)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when the model pack already exists",
    )
    parser.add_argument(
        "--sha256",
        default=None,
        help="Expected SHA-256 hex digest of the zip (overrides EXPECTED_SHA256)",
    )
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Extract without digest verification when no digest is pinned "
        "(first-bootstrap escape hatch; do not use in CI)",
    )
    args = parser.parse_args()

    root: Path = args.root
    name: str = args.name
    url: str = args.url

    pack_dir = root / name
    if pack_dir.exists() and not args.force:
        logger.info("Model pack already present at {}; pass --force to refresh", pack_dir)
        return 0

    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="photo_archiver_models_") as tmp:
        zip_path = Path(tmp) / f"{name}.zip"
        try:
            download(url, zip_path)
        except Exception as exc:
            logger.error("Download failed: {}", exc)
            return 1
        if not verify_integrity(zip_path, name, args.sha256, args.allow_unverified):
            return 1
        extract(zip_path, root, name)

    if not any(pack_dir.iterdir()):
        logger.error("Extraction produced an empty pack at {}", pack_dir)
        return 1

    logger.info("Model pack {} ready at {}", name, pack_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
