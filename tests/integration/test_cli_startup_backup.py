"""CLI startup backup parity — ADR-036 D8 (Phase F F-6).

修订 ``docs/development/configuration.md`` 既定的 "CLI 不生成启动备份" 行为：
CLI 写库子命令与 GUI 一样先做 ``VACUUM INTO`` 快照（best-effort，失败只告警）。
真实 bootstrap + 真实 scan 命令端到端验证备份落盘。
"""

import pytest

pytest.importorskip("pytestqt")

import main as main_module
from PIL import Image


def _write_real_jpeg(path) -> None:
    Image.new("RGB", (4, 4), color=(200, 100, 50)).save(path, format="JPEG")


def test_cli_scan_command_generates_startup_backup(tmp_path, monkeypatch) -> None:
    """D8: a CLI write command snapshots the database before touching it."""
    database_path = tmp_path / "data" / "cli_backup_drill.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")

    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _write_real_jpeg(photos_dir / "one.jpg")

    exit_code = main_module.main(["scan", str(photos_dir)])

    assert exit_code == 0
    assert database_path.exists(), "scan registered against the explicit DATABASE_URL"
    backups = list((database_path.parent / "backups").glob("photo_archiver_*.db"))
    assert len(backups) == 1, "CLI command must produce one startup snapshot (D8)"


def test_cli_backup_failure_does_not_block_command(tmp_path, monkeypatch) -> None:
    """Best-effort semantics (D-B3): a failing backup only warns, never blocks."""
    database_path = tmp_path / "data" / "cli_backup_fail.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")

    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _write_real_jpeg(photos_dir / "one.jpg")

    def _boom(path):  # noqa: ANN001
        raise OSError("simulated backup failure (disk full)")

    monkeypatch.setattr(main_module, "backup_database", _boom)

    exit_code = main_module.main(["scan", str(photos_dir)])

    assert exit_code == 0, "backup failure must not block the CLI command"
