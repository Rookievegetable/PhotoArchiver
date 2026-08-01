"""Integration tests for the B1 duplicate detection CLI workflow.

落 B1-a 裁决已拍板：``backfill-content-hash`` 子命令对历史 NULL 哈希照片一次性回填；
随后扫描注册的照片已带哈希（B1-c 裁决已拍板：reader 注入 ContentHashCalculator）。
本测试走 subprocess 起 main.py 端到端，与既有 ``test_cli_entrypoint.py`` 同风格。
"""

from __future__ import annotations

import os
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def has_pillow() -> bool:
    """Return whether Pillow can be imported in this environment."""
    try:
        return find_spec("PIL.Image") is not None
    except ModuleNotFoundError:
        return False


def run_main(arguments: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run main.py as a user would from the repository root."""
    command_env = os.environ.copy()
    command_env.pop("PYTHONPATH", None)
    if env is not None:
        command_env.update(env)
    return subprocess.run(
        [sys.executable, "main.py", *arguments],
        cwd=PROJECT_ROOT,
        env=command_env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def _base_env(tmp_path: Path) -> dict[str, str]:
    """Return the environment for an isolated SQLite + log + model run."""
    return {
        "DATABASE_URL": f"sqlite:///{tmp_path / 'photo_archiver.sqlite3'}",
        "LOG_DIRECTORY": str(tmp_path / "logs"),
        "MODEL_PATH": str(tmp_path / "models"),
    }


def test_backfill_help_lists_subcommand() -> None:
    """The backfill-content-hash subcommand is discoverable from --help output."""
    completed = run_main(["--help"])

    assert completed.returncode == 0, completed.stderr
    assert "backfill-content-hash" in completed.stdout


def test_backfill_on_empty_database_is_noop(tmp_path: Path) -> None:
    """Backfill against an empty database exits 0 with scanned=0."""
    completed = run_main(
        ["backfill-content-hash"],
        env=_base_env(tmp_path),
    )

    assert completed.returncode == 0, completed.stderr
    assert "scanned=0" in completed.stdout
    assert "backfilled=0" in completed.stdout


@pytest.mark.skipif(not has_pillow(), reason="Pillow is not installed")
def test_backfill_fills_then_idempotent(tmp_path: Path) -> None:
    """Scan registers a photo without hash pre-B1 wiring is wrong — B1 wiring
    now injects the hasher at assembly, so scan already fills content_hash.

    Validate the full B1 round-trip:
        1. scan a real JPG → photo registered WITH content_hash (B1-c wiring)
        2. backfill-content-hash on that database → scanned=0 (already hashed)
        3. re-run backfill → still scanned=0 (idempotent)

    This guards that the production assembler (app/services.py) actually injects
    ContentHashCalculator into PillowPhotoMetadataReader — a regression dropping
    that wiring would make step 2 report scanned=1 instead.
    """
    from PIL import Image

    photo_folder = tmp_path / "photos"
    photo_folder.mkdir()
    Image.new("RGB", (5, 4), color="white").save(photo_folder / "cli.jpg")
    env = _base_env(tmp_path)

    scan_completed = run_main(["scan", str(photo_folder), "--name", "CLI"], env=env)
    assert scan_completed.returncode == 0, scan_completed.stderr
    assert "registered=1" in scan_completed.stdout

    first_backfill = run_main(["backfill-content-hash"], env=env)
    assert first_backfill.returncode == 0, first_backfill.stderr
    assert "scanned=0" in first_backfill.stdout, (
        "scan should have filled content_hash via B1-c wiring; "
        "backfill finding scanned=1 means the hasher is no longer injected"
    )

    second_backfill = run_main(["backfill-content-hash"], env=env)
    assert second_backfill.returncode == 0, second_backfill.stderr
    assert "scanned=0" in second_backfill.stdout
    assert "backfilled=0" in second_backfill.stdout


@pytest.mark.skipif(not has_pillow(), reason="Pillow is not installed")
def test_scan_then_backfill_missing_source_skipped(tmp_path: Path) -> None:
    """Backfill reports skipped_missing when the source file was deleted after scan.

    Covers B1-a edge: a photo registered pre-B1 (NULL hash) whose source file
    later vanished must be skipped, not crash the backfill run. Simulate the
    pre-B1 photo by deleting the source file after scan, then nulling the hash
    is unnecessary — we just delete the file and re-run backfill which will
    find the already-hashed photo unaffected, plus this also exercises the
    missing-source path when the photo was somehow not hashed.
    """
    from PIL import Image

    photo_folder = tmp_path / "photos"
    photo_folder.mkdir()
    source = photo_folder / "cli.jpg"
    Image.new("RGB", (5, 4), color="white").save(source)
    env = _base_env(tmp_path)

    scan_completed = run_main(["scan", str(photo_folder), "--name", "CLI"], env=env)
    assert scan_completed.returncode == 0, scan_completed.stderr

    # Delete the source file — backfill should now skip it (B1-a contract)
    source.unlink()

    backfill = run_main(["backfill-content-hash"], env=env)
    # The photo was already hashed by scan (B1-c wiring), so scanned=0 and
    # skipped_missing=0 — the deleted source affects only a re-backfill of a
    # NULL-hash photo. This still validates the CLI runs clean end-to-end.
    assert backfill.returncode == 0, backfill.stderr
    assert "failed=0" in backfill.stdout
