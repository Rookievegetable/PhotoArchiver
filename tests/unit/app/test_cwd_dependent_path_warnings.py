"""P0-9 (D-B5) launch-directory path warning tests.

Full path anchoring is deferred to P1; this round only makes CWD-relative
configured paths visible at startup. The pure helper is tested directly and
the real bootstrap wiring is verified through the real log file.
"""

from pathlib import Path

import pytest

from photo_archiver.app.bootstrap import bootstrap_application, cwd_dependent_path_warnings
from photo_archiver.infrastructure.config import AppSettings


def test_relative_default_paths_produce_warnings() -> None:
    """显式相对配置（数据库/日志/模型）必须警告——锚定默认值不受影响。"""
    settings = AppSettings(
        database_url="sqlite:///data/photo_archiver.db",
        log_directory=Path("logs"),  # Phase F F-2：默认已锚定，显式相对仍警告
    )

    warnings = cwd_dependent_path_warnings(settings)

    database_warnings = [w for w in warnings if "数据库路径" in w]
    assert len(database_warnings) == 1
    assert "photo_archiver.db" in database_warnings[0]
    assert "绝对路径" in database_warnings[0]
    assert any("模型目录" in w for w in warnings)
    assert any("日志目录" in w for w in warnings)


def test_anchored_defaults_produce_no_warnings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Phase F F-2：锚定默认值是绝对路径——不产生 CWD 警告（注入临时锚点）。"""
    import photo_archiver.infrastructure.config.settings as settings_module

    monkeypatch.setattr(settings_module, "APP_DATA_DIR", tmp_path / "anchor-data")
    monkeypatch.setattr(settings_module, "APP_LOG_DIR", tmp_path / "anchor-logs")

    settings = AppSettings(_env_file=None)

    assert settings.database_path == tmp_path / "anchor-data" / "photo_archiver.db"
    assert settings.database_path.is_absolute()
    assert settings.log_directory == tmp_path / "anchor-logs"
    # 锚定生效：数据库与日志目录不再产生 CWD 警告；模型目录未锚定（ADR-035
    # 只锚定 database/log）——其相对默认值警告按设计保留。
    warnings = cwd_dependent_path_warnings(settings)
    assert not any("数据库路径" in w for w in warnings)
    assert not any("日志目录" in w for w in warnings)
    assert any("模型目录" in w for w in warnings)


def test_absolute_paths_produce_no_warnings(tmp_path: Path) -> None:
    """Fully absolute configuration is the anchored end state — no warnings."""
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'anchored.db'}",
        model_path=tmp_path / "models",
        log_directory=tmp_path / "logs",
    )

    assert cwd_dependent_path_warnings(settings) == []


def test_memory_database_is_not_flagged() -> None:
    """:memory: has no file location to warn about."""
    settings = AppSettings(database_url="sqlite:///:memory:")

    warnings = cwd_dependent_path_warnings(settings)

    assert not any("数据库路径" in w for w in warnings)


def test_optional_unset_roots_are_skipped() -> None:
    """Unset optional roots (None) produce no warnings of their own."""
    settings = AppSettings(database_url="sqlite:///:memory:")

    warnings = cwd_dependent_path_warnings(settings)

    assert not any("照片根目录" in w for w in warnings)
    assert not any("归档根目录" in w for w in warnings)
    assert not any("输出目录" in w for w in warnings)


def test_bootstrap_logs_cwd_warnings_to_the_log_file(
    tmp_path: Path, monkeypatch
) -> None:
    """显式相对路径时 bootstrap 仍将 CWD 警告写入真实日志（向后兼容）。"""
    monkeypatch.chdir(tmp_path)  # keep the relative DB out of the dev tree

    bootstrap_application(AppSettings(
        _env_file=None,
        database_url="sqlite:///data/photo_archiver.db",
        log_directory=Path("logs"),
    ))

    log_text = (tmp_path / "logs" / "photo_archiver.log").read_text(encoding="utf-8")
    assert "数据库路径随启动目录变化" in log_text
    assert "模型目录随启动目录变化" in log_text
    assert "日志目录随启动目录变化" in log_text