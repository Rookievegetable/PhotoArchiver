"""Logging infrastructure for PhotoArchiver."""

from photo_archiver.infrastructure.logging.configuration import (
    DEFAULT_ENVIRONMENT,
    DEFAULT_LOG_DIRECTORY,
    DEFAULT_LOG_FILE_NAME,
    DEFAULT_LOG_LEVEL,
    LOG_FILE_RETENTION,
    LOG_FILE_ROTATION,
    LOG_MESSAGE_FORMAT,
    LoggingConfig,
    configure_logging,
    log_application_startup,
    logging_config_from_env,
    normalize_log_level,
)

__all__ = [
    "DEFAULT_ENVIRONMENT",
    "DEFAULT_LOG_DIRECTORY",
    "DEFAULT_LOG_FILE_NAME",
    "DEFAULT_LOG_LEVEL",
    "LOG_FILE_RETENTION",
    "LOG_FILE_ROTATION",
    "LOG_MESSAGE_FORMAT",
    "LoggingConfig",
    "configure_logging",
    "log_application_startup",
    "logging_config_from_env",
    "normalize_log_level",
]
