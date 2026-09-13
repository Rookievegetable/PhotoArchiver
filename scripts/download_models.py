"""PhotoArchiver model fetcher (thin CLI wrapper).

Downloads the InsightFace ``buffalo_l`` model pack into
``resources/models/`` so :class:`photo_archiver.ai.InsightFaceDetector`
can load it without an automatic download at runtime.

Usage::

    python scripts/download_models.py                     # default buffalo_l
    python scripts/download_models.py --name antelopev2  # alternate pack

Integrity (P2-007): the downloaded zip is verified before extraction
(fail-closed against pinned SHA-256 digests). The core logic lives in
:mod:`photo_archiver.infrastructure.ai.model_deployment` (SSOT) so the
frozen desktop build bundles the same capability as the `download-models`
CLI subcommand; this script re-exports the core names for test
compatibility.

The model files are intentionally **not** committed to git (see
``.gitignore``). CI pipelines should run this script before invoking
integration tests that exercise the real detector.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 直接执行时（python scripts/download_models.py）src 不在 sys.path——
# 先引导再导入 SSOT 模块（frozen 构建无此问题，bundle 自含）。
ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

import certifi  # noqa: E402,F401  # re-exported: the download pins the TLS trust store

from photo_archiver.infrastructure.ai.model_deployment import (  # noqa: E402,F401
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_URL,
    EXPECTED_SHA256,
    download,
    download_model_pack,
    extract,
    sha256_of,
    verify_integrity,
)

DEFAULT_MODEL_ROOT = ROOT / "resources" / "models"


def main() -> int:
    """Entry point: parse args, download, extract, verify (SSOT in app package)."""
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

    return download_model_pack(
        name=args.name,
        url=args.url,
        root=args.root,
        force=args.force,
        sha256=args.sha256,
        allow_unverified=args.allow_unverified,
    )


if __name__ == "__main__":
    sys.exit(main())
