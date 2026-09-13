"""Model pack deployment — download, verify, extract (P-3, ADR-042).

SSOT for model-pack acquisition: the CLI subcommand ``download-models`` and
the legacy ``scripts/download_models.py`` wrapper both delegate here. The
logic lives inside the application package so the frozen (PyInstaller) build
bundles it — ``scripts/`` is not available in the installed form.

Integrity (P2-007): downloaded zips are verified against pinned SHA-256
digests before extraction; fail-closed semantics are unchanged.
"""

from __future__ import annotations

import hashlib
import shutil
import ssl
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import certifi
from loguru import logger

DEFAULT_MODEL_NAME = "buffalo_l"

# InsightFace publishes model packs as GitHub release assets. The URL below
# is the canonical buffalo_l archive published by deepinsight/insightface.
# antelopev2 and other packs live under the same release; pass a custom URL
# to override for mirrors or alternate packs.
DEFAULT_MODEL_URL = (
    "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
)

# P2-007 (Phase 3 audit): integrity pinning. Map pack name -> the official
# SHA-256 hex digest of its release zip. An empty string means "not pinned
# yet": download then refuses to extract unless ``allow_unverified`` is set
# (first-bootstrap escape hatch).
EXPECTED_SHA256: dict[str, str] = {
    # P0-8 (Phase B): buffalo_l pinned. Digest computed from an archive
    # fetched from the canonical release URL below; cross-checked against
    # third-party LFS mirrors of the same asset and against the extracted
    # pack that CI has been running the AI suite with.
    "buffalo_l": "80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f",
    # ISSUE-024 (体检 N-7) 2026-09-12: antelopev2 pinned. Digest computed from
    # the canonical release asset (v0.7, 360662982 bytes; zip integrity
    # verified with zipfile.testzip before hashing).
    "antelopev2": "8e182f14fc6e80b3bfa375b33eb6cff7ee05d8ef7633e738d1c89021dcf0c5c5",
}


def download(url: str, target: Path) -> None:
    """Stream ``url`` to ``target`` with a progress log.

    P0-8 release blocker: the TLS context is explicitly anchored to
    certifi's CA bundle — CPython's default CA loading failed on a clean
    Windows VM (no issuer for the github.com chain in the Windows store).
    Certificate and hostname verification stay fully enabled.
    """
    logger.info("Downloading model pack from {}", url)
    target.parent.mkdir(parents=True, exist_ok=True)
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(url, context=ssl_context) as response, open(target, "wb") as out_file:
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
    (neither in ``EXPECTED_SHA256`` nor passed explicitly) the download is
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
                "No SHA-256 pinned for '{}' — proceeding UNVERIFIED via allow-unverified. "
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
    pack_dir = dest_root / name
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(pack_dir)
    logger.info("Extracted model pack into {}", pack_dir)
    return pack_dir


def download_model_pack(
    name: str = DEFAULT_MODEL_NAME,
    url: str = DEFAULT_MODEL_URL,
    root: Path | None = None,
    *,
    force: bool = False,
    sha256: str | None = None,
    allow_unverified: bool = False,
) -> int:
    """Download, verify and extract one model pack. Returns a process exit code.

    Skips entirely when the pack is already present and ``force`` is unset.
    """
    root = Path(root) if root is not None else Path("resources") / "models"
    pack_dir = root / name
    if pack_dir.exists() and not force:
        logger.info("Model pack already present at {}; pass force to refresh", pack_dir)
        return 0

    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="photo_archiver_models_") as tmp:
        zip_path = Path(tmp) / f"{name}.zip"
        try:
            download(url, zip_path)
        except Exception as exc:
            logger.error("Download failed: {}", exc)
            return 1
        if not verify_integrity(zip_path, name, sha256, allow_unverified):
            return 1
        extract(zip_path, root, name)

    if not any(pack_dir.iterdir()):
        logger.error("Extraction produced an empty pack at {}", pack_dir)
        return 1

    logger.info("Model pack {} ready at {}", name, pack_dir)
    return 0
