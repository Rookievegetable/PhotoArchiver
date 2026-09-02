"""Unit tests for download_models.py integrity verification (P2-007).

The script lives in ``scripts/`` (not a package), so it is loaded via
``importlib`` from its file path. Only the pure verification helpers are
tested — no network access, no archive extraction.
"""

import importlib.util
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "download_models.py"
)


def _load_script():
    """Load download_models.py as a module without package machinery."""
    spec = importlib.util.spec_from_file_location(
        "download_models_under_test", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sha256_of_matches_hashlib(tmp_path: Path) -> None:
    """sha256_of streams the file and equals hashlib on the same bytes."""
    import hashlib

    dm = _load_script()
    f = tmp_path / "pack.zip"
    f.write_bytes(b"insightface buffalo_l archive bytes")

    assert dm.sha256_of(f) == hashlib.sha256(b"insightface buffalo_l archive bytes").hexdigest()


def test_verify_integrity_accepts_matching_pinned_digest(tmp_path: Path) -> None:
    """A pinned digest that matches the archive verifies OK."""
    import hashlib

    dm = _load_script()
    f = tmp_path / "pack.zip"
    f.write_bytes(b"model payload")
    digest = hashlib.sha256(b"model payload").hexdigest()

    assert dm.verify_integrity(f, "buffalo_l", digest, allow_unverified=False)


def test_verify_integrity_rejects_mismatched_digest(tmp_path: Path) -> None:
    """A pinned digest that does not match fails closed."""
    dm = _load_script()
    f = tmp_path / "pack.zip"
    f.write_bytes(b"tampered payload")

    assert not dm.verify_integrity(
        f, "buffalo_l", "0" * 64, allow_unverified=False
    )


def test_verify_integrity_unpinned_refuses_by_default(tmp_path: Path) -> None:
    """No pinned digest + no escape hatch -> refuse (fail closed)."""
    dm = _load_script()
    f = tmp_path / "pack.zip"
    f.write_bytes(b"unverified payload")

    assert not dm.verify_integrity(f, "buffalo_l", None, allow_unverified=False)


def test_verify_integrity_unpinned_allows_first_bootstrap(tmp_path: Path) -> None:
    """No pinned digest + --allow-unverified -> permitted first bootstrap.

    Uses ``antelopev2`` (still unpinned) — buffalo_l is pinned since P0-8 and
    now fails closed on unverified archives.
    """
    dm = _load_script()
    f = tmp_path / "pack.zip"
    f.write_bytes(b"unverified payload")

    assert dm.verify_integrity(f, "antelopev2", None, allow_unverified=True)


def test_verify_integrity_falls_back_to_expected_sha256_map(
    tmp_path: Path, monkeypatch
) -> None:
    """When --sha256 is absent the EXPECTED_SHA256 pin map is consulted."""
    import hashlib

    dm = _load_script()
    f = tmp_path / "pack.zip"
    f.write_bytes(b"pinned payload")
    digest = hashlib.sha256(b"pinned payload").hexdigest()
    monkeypatch.setitem(dm.EXPECTED_SHA256, "buffalo_l", digest)

    assert dm.verify_integrity(f, "buffalo_l", None, allow_unverified=False)


def test_verify_integrity_explicit_sha256_overrides_map(
    tmp_path: Path, monkeypatch
) -> None:
    """An explicit --sha256 takes precedence over the pin map."""
    dm = _load_script()
    f = tmp_path / "pack.zip"
    f.write_bytes(b"explicit payload")
    monkeypatch.setitem(dm.EXPECTED_SHA256, "buffalo_l", "0" * 64)

    import hashlib

    assert dm.verify_integrity(
        f, "buffalo_l", hashlib.sha256(b"explicit payload").hexdigest(),
        allow_unverified=False,
    )


def test_buffalo_l_digest_is_pinned_fail_closed() -> None:
    """P0-8: the production pin map must carry a real buffalo_l digest.

    Guards against the map regressing to fail-open (empty string), which
    would push CI back onto --allow-unverified.
    """
    import re

    dm = _load_script()

    pinned = dm.EXPECTED_SHA256["buffalo_l"]
    assert re.fullmatch(r"[0-9a-f]{64}", pinned), (
        "buffalo_l must stay pinned to a 64-hex-char SHA-256 digest"
    )


def test_verify_integrity_rejects_archive_not_matching_production_pin(
    tmp_path: Path,
) -> None:
    """An archive that does not match the PRODUCTION buffalo_l pin fails."""
    dm = _load_script()
    f = tmp_path / "pack.zip"
    f.write_bytes(b"payload that differs from the official release zip")

    assert not dm.verify_integrity(f, "buffalo_l", None, allow_unverified=False)
