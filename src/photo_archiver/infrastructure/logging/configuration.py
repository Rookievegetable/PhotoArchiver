"""Loguru configuration for PhotoArchiver."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

DEFAULT_LOG_DIRECTORY = Path("logs")
DEFAULT_LOG_FILE_NAME = "photo_archiver.log"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_ENVIRONMENT = "development"
LOG_FILE_ROTATION = "10 MB"
LOG_FILE_RETENTION = "30 days"
LOG_MESSAGE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level:<8} | "
    "{name}:{function}:{line} - {message}"
)
SUPPORTED_LOG_LEVELS = frozenset(
    {
        "TRACE",
        "DEBUG",
        "INFO",
        "SUCCESS",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }
)


def normalize_log_level(level: str) -> str:
    """Normalize and validate a Loguru log level name.

    Args:
        level: Raw log level string, case-insensitive.

    Returns:
        Uppercase log level accepted by Loguru.

    Raises:
        ValueError: If the level is not supported.
    """
    normalized = level.strip().upper()
    if normalized not in SUPPORTED_LOG_LEVELS:
        supported = ", ".join(sorted(SUPPORTED_LOG_LEVELS))
        raise ValueError(
            f"Unsupported log level {level!r}. Supported levels: {supported}"
        )
    return normalized


@dataclass(frozen=True)
class LoggingConfig:
    """Configuration values used to initialize application logging.

    Args:
        log_directory: Directory where log files are written.
        file_name: Name of the application log file.
        level: Minimum log level for console and file sinks.
    """

    log_directory: Path = DEFAULT_LOG_DIRECTORY
    file_name: str = DEFAULT_LOG_FILE_NAME
    level: str = DEFAULT_LOG_LEVEL

    def __post_init__(self) -> None:
        if not isinstance(self.log_directory, Path):
            object.__setattr__(self, "log_directory", Path(self.log_directory))
        object.__setattr__(self, "level", normalize_log_level(self.level))

    @property
    def log_file(self) -> Path:
        """Return the full path to the application log file."""
        return self.log_directory / self.file_name


def logging_config_from_env() -> LoggingConfig:
    """Build logging configuration from environment variables.

    Reads ``LOG_LEVEL`` and ``LOG_DIRECTORY`` when present. This helper
    bridges Step 1 logging with Step 2 configuration without hard-coding
    environment access in ``main.py``.

    Returns:
        Logging configuration derived from the current process environment.
    """
    log_directory = Path(os.environ.get("LOG_DIRECTORY", DEFAULT_LOG_DIRECTORY))
    log_level = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL)
    return LoggingConfig(log_directory=log_directory, level=log_level)


def configure_logging(config: LoggingConfig | None = None) -> None:
    """Configure Loguru sinks for console and file logging.

    Args:
        config: Optional logging configuration. Defaults are used when omitted.
    """
    resolved_config = config or LoggingConfig()
    resolved_config.log_directory.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stderr,
        level=resolved_config.level,
        format=LOG_MESSAGE_FORMAT,
    )
    logger.add(
        resolved_config.log_file,
        level=resolved_config.level,
        format=LOG_MESSAGE_FORMAT,
        rotation=LOG_FILE_ROTATION,
        retention=LOG_FILE_RETENTION,
        encoding="utf-8",
    )
    logger.info("Logging configured at {}", resolved_config.log_file)


def log_application_startup(*, name: str, version: str, environment: str) -> None:
    """Record a structured application startup message.

    Args:
        name: Application display name.
        version: Application version string.
        environment: Runtime environment label, such as ``development``.
    """
    logger.info("Starting {} v{} ({})", name, version, environment)
