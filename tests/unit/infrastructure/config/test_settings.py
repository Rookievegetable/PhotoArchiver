"""Unit tests for application settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from photo_archiver.infrastructure.config import AppSettings


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent local ``.env`` files from affecting settings tests."""
    monkeypatch.setenv("APP_NAME", "PhotoArchiver")
    monkeypatch.setenv("APP_VERSION", "0.1.0")
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("LOG_DIRECTORY", "logs")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///data/photo_archiver.db")
    monkeypatch.setenv("MODEL_PATH", "models")
    monkeypatch.setenv("MAX_WORKERS", "4")
    monkeypatch.delenv("PHOTO_ROOT", raising=False)
    monkeypatch.delenv("OUTPUT_ROOT", raising=False)


def test_app_settings_use_defaults(isolated_env: None) -> None:
    settings = AppSettings(_env_file=None)

    assert settings.app_name == "PhotoArchiver"
    assert settings.app_version == "0.1.0"
    assert settings.env == "development"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.log_directory == Path("logs")
    assert settings.database_url == "sqlite:///data/photo_archiver.db"
    assert settings.model_path == Path("models")
    assert settings.photo_root is None
    assert settings.output_root is None
    assert settings.max_workers == 4


def test_app_settings_read_environment_overrides(
    isolated_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    monkeypatch.setenv("APP_NAME", "TestArchiver")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("LOG_DIRECTORY", str(tmp_path / "logs"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "models"))
    monkeypatch.setenv("PHOTO_ROOT", str(tmp_path / "photos"))
    monkeypatch.setenv("OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("MAX_WORKERS", "8")

    settings = AppSettings(_env_file=None)

    assert settings.app_name == "TestArchiver"
    assert settings.log_level == "WARNING"
    assert settings.log_directory == tmp_path / "logs"
    assert settings.database_path == tmp_path / "app.db"
    assert settings.model_path == tmp_path / "models"
    assert settings.photo_root == tmp_path / "photos"
    assert settings.output_root == output_root
    assert settings.max_workers == 8


def test_debug_promotes_log_level_when_log_level_unset(
    isolated_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = AppSettings(_env_file=None)

    assert settings.debug is True
    assert settings.effective_log_level == "DEBUG"


def test_explicit_log_level_takes_precedence_over_debug(
    isolated_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")

    settings = AppSettings(_env_file=None)

    assert settings.effective_log_level == "ERROR"


def test_invalid_log_level_raises_validation_error(isolated_env: None) -> None:
    with pytest.raises(ValidationError, match="Unsupported log level"):
        AppSettings(_env_file=None, log_level="VERBOSE")


def test_invalid_database_url_raises_validation_error(isolated_env: None) -> None:
    with pytest.raises(ValidationError, match="sqlite:/// scheme"):
        AppSettings(_env_file=None, database_url="postgresql://localhost/db")


def test_empty_database_path_raises_validation_error(isolated_env: None) -> None:
    with pytest.raises(ValidationError, match="database file path"):
        AppSettings(_env_file=None, database_url="sqlite:///")


def test_invalid_max_workers_raises_validation_error(isolated_env: None) -> None:
    with pytest.raises(ValidationError, match="MAX_WORKERS must be between"):
        AppSettings(_env_file=None, max_workers=0)


def test_to_logging_config_uses_effective_log_level(
    isolated_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setenv("LOG_DIRECTORY", str(tmp_path / "logs"))

    settings = AppSettings(_env_file=None)
    logging_config = settings.to_logging_config()

    assert logging_config.log_directory == tmp_path / "logs"
    assert logging_config.level == "DEBUG"


def test_ensure_runtime_directories_creates_expected_paths(
    isolated_env: None,
    tmp_path: Path,
) -> None:
    settings = AppSettings(
        _env_file=None,
        log_directory=tmp_path / "logs",
        database_url=f"sqlite:///{tmp_path / 'data' / 'app.db'}",
        model_path=tmp_path / "models",
        output_root=tmp_path / "exports",
    )

    settings.ensure_runtime_directories()

    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "data").is_dir()
    # model_path is intentionally NOT created by ensure_runtime_directories
    # (P2-b): InsightFaceLoader / download_models.py own it.
    assert not (tmp_path / "models").exists()
    assert (tmp_path / "exports").is_dir()
