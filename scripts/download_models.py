"""PhotoArchiver model fetcher.

Downloads the InsightFace ``buffalo_l`` model pack into
``resources/models/`` so :class:`photo_archiver.ai.InsightFaceDetector`
can load it without an automatic download at runtime.

Usage::

    python scripts/download_models.py                     # default buffalo_l
    python scripts/download_models.py --name antelopev2  # alternate pack

The model files are intentionally **not** committed to git (see
``.gitignore``). CI pipelines should run this script before invoking
integration tests that exercise the real detector.
"""

from __future__ import annotations

import argparse
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


def download(url: str, target: Path) -> None:
    """Stream ``url`` to ``target`` with a progress log."""
    logger.info("Downloading model pack from {}", url)
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, open(target, "wb") as out_file:
        shutil.copyfileobj(response, out_file)
    logger.info("Saved model pack to {} ({} bytes)", target, target.stat().st_size)


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
        extract(zip_path, root, name)

    if not any(pack_dir.iterdir()):
        logger.error("Extraction produced an empty pack at {}", pack_dir)
        return 1

    logger.info("Model pack {} ready at {}", name, pack_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
