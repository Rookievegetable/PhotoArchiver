"""Entry-point failure paths for corrupted databases (Phase B P0-6).

``main.py`` is the composition root; these tests pin the contract that every
entry (scan/archive/backfill CLI, GUI) reports Chinese guidance instead of a
traceback and exits with code 2.
"""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import main as main_module  # noqa: E402  # sys.path injection above is required
from photo_archiver.infrastructure.database.integrity import (  # noqa: E402
    BACKUP_DIRECTORY_NAME,
    CorruptedDatabaseError,
)


@pytest.mark.parametrize(
    "runner",
    [
        main_module.run_scan_command,
        main_module.run_archive_command,
        main_module.run_backfill_content_hash_command,
    ],
    ids=["scan", "archive", "backfill"],
)
def test_cli_writes_guidance_to_stderr_and_exits_2(
    runner: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI entries report recovery guidance on stderr and exit code 2."""
    database_path = tmp_path / "photo_archiver.db"
    error = CorruptedDatabaseError(database_path, ["failed to read page 2"])

    def fail_bootstrap() -> object:
        raise error

    monkeypatch.setattr(main_module, "bootstrap_application", fail_bootstrap)

    exit_code = runner(None)  # type: ignore[operator]

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "文件损坏" in captured.err
    assert "无法继续启动" in captured.err
    assert str(database_path.parent / BACKUP_DIRECTORY_NAME) in captured.err
    assert "failed to read page 2" in captured.err


def test_gui_shows_dialog_instead_of_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The GUI entry surfaces corruption through the modal dialog, exit code 2."""
    error = CorruptedDatabaseError(tmp_path / "photo_archiver.db", ["issue-x"])
    captured: dict[str, str] = {}

    def fail_bootstrap() -> object:
        raise error

    def fake_dialog(message: str) -> None:
        captured["message"] = message

    monkeypatch.setattr(main_module, "bootstrap_application", fail_bootstrap)
    monkeypatch.setattr(main_module, "show_corrupted_database_dialog", fake_dialog)

    exit_code = main_module.main([])

    assert exit_code == 2
    assert "文件损坏" in captured["message"]


def test_gui_startup_survives_backup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-8 round (F-1): a failing startup backup must not block GUI startup.

    The backup is best-effort by design (D-B3) — a full disk or an unwritable
    backup directory must degrade to a warning, never crash the launch the
    same commit was meant to harden.
    """
    constructed: list[str] = []

    class _FakeApplication:
        def __init__(self, argv, context) -> None:
            constructed.append("app")

        def run(self) -> int:
            return 0

    def succeed_bootstrap() -> object:
        return object()

    def fail_backup(database_path) -> None:
        raise RuntimeError("disk full while writing backup")

    monkeypatch.setattr(main_module, "bootstrap_application", succeed_bootstrap)
    monkeypatch.setattr(main_module, "backup_database", fail_backup)
    monkeypatch.setattr(main_module, "PhotoArchiverApplication", _FakeApplication)

    exit_code = main_module.main([])

    assert exit_code == 0
    assert constructed == ["app"]  # the application was still launched