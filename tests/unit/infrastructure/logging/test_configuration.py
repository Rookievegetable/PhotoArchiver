"""Unit tests for Loguru logging configuration."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from loguru import logger

from photo_archiver.infrastructure.logging.configuration import (
    LOG_FILE_RETENTION,
    LOG_FILE_ROTATION,
    LOG_MESSAGE_FORMAT,
    LoggingConfig,
    configure_logging,
    log_application_startup,
    logging_config_from_env,
    normalize_log_level,
)


@pytest.fixture(autouse=True)
def reset_logger_handlers() -> None:
    """Ensure tests do not leak custom Loguru handlers."""
    yield
    logger.remove()


def test_normalize_log_level_accepts_case_insensitive_values() -> None:
    assert normalize_log_level("debug") == "DEBUG"
    assert normalize_log_level(" INFO ") == "INFO"


def test_normalize_log_level_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="Unsupported log level"):
        normalize_log_level("VERBOSE")


def test_logging_config_from_env_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_DIRECTORY", raising=False)

    config = logging_config_from_env()

    assert config.level == "INFO"
    assert config.log_directory == Path("logs")


def test_logging_config_from_env_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_DIRECTORY", str(tmp_path))

    config = logging_config_from_env()

    assert config.level == "DEBUG"
    assert config.log_directory == tmp_path


def test_configure_logging_creates_log_file_and_writes_messages(tmp_path: Path) -> None:
    config = LoggingConfig(
        log_directory=tmp_path,
        file_name="test.log",
        level="DEBUG",
    )

    configure_logging(config)
    logger.debug("debug message")

    log_content = config.log_file.read_text(encoding="utf-8")

    assert config.log_file.exists()
    assert "debug message" in log_content
    assert "DEBUG" in log_content


def test_configure_logging_applies_rotation_and_retention(tmp_path: Path) -> None:
    config = LoggingConfig(log_directory=tmp_path, file_name="rotation.log")

    with patch("photo_archiver.infrastructure.logging.configuration.logger.add") as mock_add:
        configure_logging(config)

    file_sink_call = mock_add.call_args_list[1]
    assert file_sink_call.args[0] == config.log_file
    assert file_sink_call.kwargs["rotation"] == LOG_FILE_ROTATION
    assert file_sink_call.kwargs["retention"] == LOG_FILE_RETENTION
    assert file_sink_call.kwargs["format"] == LOG_MESSAGE_FORMAT


def test_configure_logging_can_be_called_multiple_times(tmp_path: Path) -> None:
    first_config = LoggingConfig(log_directory=tmp_path / "first", file_name="first.log")
    second_config = LoggingConfig(log_directory=tmp_path / "second", file_name="second.log")

    configure_logging(first_config)
    logger.info("first run")
    configure_logging(second_config)
    logger.info("second run")

    assert first_config.log_file.exists()
    assert second_config.log_file.exists()
    assert "first run" in first_config.log_file.read_text(encoding="utf-8")
    assert "second run" in second_config.log_file.read_text(encoding="utf-8")


def test_logging_from_worker_thread_does_not_raise(tmp_path: Path) -> None:
    config = LoggingConfig(log_directory=tmp_path, file_name="thread.log", level="INFO")
    configure_logging(config)

    errors: list[BaseException] = []

    def worker() -> None:
        try:
            logger.info("worker thread message")
        except BaseException as error:  # noqa: BLE001 - test harness captures any failure
            errors.append(error)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert not errors
    assert "worker thread message" in config.log_file.read_text(encoding="utf-8")


def test_log_application_startup_writes_message(tmp_path: Path) -> None:
    config = LoggingConfig(log_directory=tmp_path, file_name="startup.log", level="INFO")
    configure_logging(config)

    log_application_startup(name="PhotoArchiver", version="0.1.0", environment="development")

    log_content = config.log_file.read_text(encoding="utf-8")
    assert "Starting PhotoArchiver v0.1.0 (development)" in log_content
