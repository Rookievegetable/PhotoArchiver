"""Tests for legacy database migration hints (Phase F F-2, ADR-035).

默认数据库锚定用户数据目录后，检测"启动目录下存在旧 CWD 库而锚定位置无库"
的迁移时机——仅提示引导，绝不自动搬库（数据安全原则）。
"""

from pathlib import Path

import pytest

from photo_archiver.app.bootstrap import legacy_database_migration_hints
from photo_archiver.infrastructure.config import AppSettings


@pytest.fixture
def anchored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point the anchored defaults at a temporary directory."""
    import photo_archiver.infrastructure.config.settings as settings_module

    anchor_data = tmp_path / "anchor-data"
    monkeypatch.setattr(settings_module, "APP_DATA_DIR", anchor_data)
    return anchor_data


def _legacy_db(tmp_path: Path) -> Path:
    """Materialize a legacy CWD database at the old default location."""
    legacy = tmp_path / "data" / "photo_archiver.db"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"legacy-db")
    return legacy


def test_legacy_hint_when_legacy_exists_and_anchor_empty(
    anchored: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """旧 CWD 库存在 + 锚定位置无库 + 未显式配置 → 打印迁移引导。"""
    _legacy_db(tmp_path)
    monkeypatch.chdir(tmp_path)

    hints = legacy_database_migration_hints(AppSettings(_env_file=None))

    assert len(hints) == 1
    assert "检测到旧版启动目录下的数据库" in hints[0]
    assert str(_legacy_db(tmp_path)) in hints[0]
    assert str(anchored / "photo_archiver.db") in hints[0]


def test_legacy_no_hint_when_anchored_db_already_exists(
    anchored: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """锚定位置已有库 → 不再提示（数据已在新默认位置）。"""
    _legacy_db(tmp_path)
    anchored.mkdir(parents=True, exist_ok=True)
    (anchored / "photo_archiver.db").write_bytes(b"new-db")
    monkeypatch.chdir(tmp_path)

    hints = legacy_database_migration_hints(AppSettings(_env_file=None))

    assert hints == []


def test_legacy_no_hint_when_database_url_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, anchored: Path
) -> None:
    """显式 DATABASE_URL → 永不提示（用户自己掌控配置）。"""
    _legacy_db(tmp_path)
    monkeypatch.chdir(tmp_path)

    explicit = AppSettings(_env_file=None, database_url="sqlite:///custom/custom.db")

    assert legacy_database_migration_hints(explicit) == []


def test_legacy_no_hint_when_no_legacy_db(
    anchored: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无旧 CWD 库 → 无提示。"""
    monkeypatch.chdir(tmp_path)

    assert legacy_database_migration_hints(AppSettings(_env_file=None)) == []


def test_no_legacy_hint_when_anchor_missing_but_no_cwd_db(
    anchored: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """陌生目录启动 + 无旧库 + 无显式配置 → 干净启动（无提示、无警告）。"""
    monkeypatch.chdir(tmp_path)

    hints = legacy_database_migration_hints(AppSettings(_env_file=None))

    assert hints == []