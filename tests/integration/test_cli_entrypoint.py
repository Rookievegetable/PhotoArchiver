"""Integration tests for the command-line entrypoint."""

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


def test_main_help_runs_from_repository_root() -> None:
    """The local source tree is importable when running python main.py directly."""
    completed = run_main(["--help"])

    assert completed.returncode == 0, completed.stderr
    assert "usage: photo-archiver" in completed.stdout
    assert "scan" in completed.stdout


def test_main_scan_reports_missing_folder(tmp_path: Path) -> None:
    """The scan CLI exits non-zero and prints scanner errors to stderr."""
    missing_folder = tmp_path / "missing"

    completed = run_main(
        ["scan", str(missing_folder)],
        env={
            "DATABASE_URL": f"sqlite:///{tmp_path / 'photo_archiver.sqlite3'}",
            "LOG_DIRECTORY": str(tmp_path / "logs"),
            "MODEL_PATH": str(tmp_path / "models"),
        },
    )

    assert completed.returncode == 1
    assert "discovered=0" in completed.stdout
    assert "failed=1" in completed.stdout
    assert "Photo folder does not exist" in completed.stderr


def test_main_scan_empty_folder_succeeds(tmp_path: Path) -> None:
    """An empty folder is a successful scan with zero counts."""
    photo_folder = tmp_path / "photos"
    photo_folder.mkdir()

    completed = run_main(
        ["scan", str(photo_folder)],
        env={
            "DATABASE_URL": f"sqlite:///{tmp_path / 'photo_archiver.sqlite3'}",
            "LOG_DIRECTORY": str(tmp_path / "logs"),
            "MODEL_PATH": str(tmp_path / "models"),
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "discovered=0" in completed.stdout
    assert "registered=0" in completed.stdout
    assert "skipped=0" in completed.stdout
    assert "failed=0" in completed.stdout


@pytest.mark.skipif(not has_pillow(), reason="Pillow is not installed")
def test_main_scan_command_runs_end_to_end(tmp_path: Path) -> None:
    """The scan CLI can register a real image into a temporary SQLite database."""
    from PIL import Image

    photo_folder = tmp_path / "photos"
    photo_folder.mkdir()
    Image.new("RGB", (5, 4), color="white").save(photo_folder / "cli.jpg")

    completed = run_main(
        ["scan", str(photo_folder), "--name", "CLI"],
        env={
            "DATABASE_URL": f"sqlite:///{tmp_path / 'photo_archiver.sqlite3'}",
            "LOG_DIRECTORY": str(tmp_path / "logs"),
            "MODEL_PATH": str(tmp_path / "models"),
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "discovered=1" in completed.stdout
    assert "registered=1" in completed.stdout
    assert "failed=0" in completed.stdout