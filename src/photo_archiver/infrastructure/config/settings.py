"""Application settings loaded from environment variables and ``.env``."""

from __future__ import annotations

from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from photo_archiver.infrastructure.logging.configuration import (
    DEFAULT_LOG_DIRECTORY,
    DEFAULT_LOG_LEVEL,
    LoggingConfig,
    normalize_log_level,
)

DEFAULT_APP_NAME = "PhotoArchiver"
DEFAULT_APP_VERSION = "0.1.0"
DEFAULT_ENVIRONMENT = "development"
DEFAULT_DATABASE_URL = "sqlite:///data/photo_archiver.db"
DEFAULT_MODEL_PATH = Path("resources/models")
DEFAULT_MAX_WORKERS = 4
MIN_MAX_WORKERS = 1
MAX_MAX_WORKERS = 32
SQLITE_URL_PREFIX = "sqlite:///"
DEFAULT_MATCH_THRESHOLD = 0.40
MIN_MATCH_THRESHOLD = 0.0
MAX_MATCH_THRESHOLD = 1.0
# Decompression-bomb guard (P2-002 fix): matches Pillow's built-in default so a
# hostile oversized image is refused instead of exhausting memory on decode.
DEFAULT_MAX_IMAGE_PIXELS = 89_478_485
# The guard must stay enabled: 0 / negative values are rejected so the limit
# can be tuned but never disabled via configuration.
MIN_MAX_IMAGE_PIXELS = 1
DEFAULT_ARCHIVE_CONFLICT_STRATEGY = "skip"
VALID_ARCHIVE_CONFLICT_STRATEGIES = ("skip", "overwrite", "rename")


class AppSettings(BaseSettings):
    """Central application configuration for PhotoArchiver.

    Values are loaded from environment variables and an optional project-root
    ``.env`` file. Field names map to uppercase environment keys, for example
    ``app_name`` -> ``APP_NAME``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = Field(default=DEFAULT_APP_NAME)
    app_version: str = Field(default=DEFAULT_APP_VERSION)
    env: str = Field(default=DEFAULT_ENVIRONMENT)
    debug: bool = Field(default=False)
    log_level: str = Field(default=DEFAULT_LOG_LEVEL)
    log_directory: Path = Field(default=DEFAULT_LOG_DIRECTORY)
    database_url: str = Field(default=DEFAULT_DATABASE_URL)
    model_path: Path = Field(default=DEFAULT_MODEL_PATH)
    photo_root: Path | None = Field(default=None)
    output_root: Path | None = Field(default=None)
    archive_root: Path | None = Field(default=None)
    archive_conflict_strategy: str = Field(default=DEFAULT_ARCHIVE_CONFLICT_STRATEGY)
    max_workers: int = Field(default=DEFAULT_MAX_WORKERS)
    match_threshold: float = Field(default=DEFAULT_MATCH_THRESHOLD)
    max_image_pixels: int = Field(default=DEFAULT_MAX_IMAGE_PIXELS)

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, value: object) -> str:
        """Validate configured log level names."""
        if value is None:
            return DEFAULT_LOG_LEVEL
        return normalize_log_level(str(value))

    @field_validator("log_directory", "model_path", mode="before")
    @classmethod
    def validate_required_path(cls, value: object) -> Path:
        """Convert configured path values to ``Path`` instances."""
        if isinstance(value, Path):
            return value
        if value is None or str(value).strip() == "":
            raise ValueError("Path configuration values must not be empty")
        return Path(str(value))

    @field_validator("photo_root", "output_root", "archive_root", mode="before")
    @classmethod
    def validate_optional_path(cls, value: object) -> Path | None:
        """Convert optional path values, treating blank values as unset."""
        if value is None or str(value).strip() == "":
            return None
        return Path(str(value))

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Ensure the database URL uses SQLite with a concrete target."""
        if not value.startswith(SQLITE_URL_PREFIX):
            raise ValueError(
                "DATABASE_URL must use the sqlite:/// scheme. "
                f"Received: {value!r}"
            )
        database_path = value.removeprefix(SQLITE_URL_PREFIX).strip()
        if not database_path:
            raise ValueError(
                "DATABASE_URL must include a database file path after sqlite:///"
            )
        return value

    @field_validator("max_workers")
    @classmethod
    def validate_max_workers(cls, value: int) -> int:
        """Ensure worker count stays within supported bounds."""
        if not MIN_MAX_WORKERS <= value <= MAX_MAX_WORKERS:
            raise ValueError(
                "MAX_WORKERS must be between "
                f"{MIN_MAX_WORKERS} and {MAX_MAX_WORKERS}. Received: {value}"
            )
        return value

    @field_validator("match_threshold")
    @classmethod
    def validate_match_threshold(cls, value: float) -> float:
        """Ensure the match threshold stays within the supported similarity range."""
        if not MIN_MATCH_THRESHOLD <= value <= MAX_MATCH_THRESHOLD:
            raise ValueError(
                "MATCH_THRESHOLD must be between "
                f"{MIN_MATCH_THRESHOLD} and {MAX_MATCH_THRESHOLD}. Received: {value}"
            )
        return value

    @field_validator("max_image_pixels")
    @classmethod
    def validate_max_image_pixels(cls, value: int) -> int:
        """Ensure the image pixel guard stays a finite, positive limit (P2-002)."""
        if value < MIN_MAX_IMAGE_PIXELS:
            raise ValueError(
                "MAX_IMAGE_PIXELS must be a positive pixel count. Received: "
                f"{value}. The decompression-bomb guard must never be disabled."
            )
        return value

    @field_validator("archive_conflict_strategy")
    @classmethod
    def validate_archive_conflict_strategy(cls, value: str) -> str:
        """Ensure the archive conflict strategy is one of the supported modes."""
        normalized = str(value).strip().lower()
        if normalized not in VALID_ARCHIVE_CONFLICT_STRATEGIES:
            raise ValueError(
                "ARCHIVE_CONFLICT_STRATEGY must be one of "
                f"{VALID_ARCHIVE_CONFLICT_STRATEGIES}. Received: {value}"
            )
        return normalized

    @property
    def effective_log_level(self) -> str:
        """Return the normalized runtime log level.

        When ``DEBUG`` is enabled and ``LOG_LEVEL`` was not explicitly provided,
        runtime logging defaults to ``DEBUG``.
        """
        if self.debug and "log_level" not in self.model_fields_set:
            return "DEBUG"
        return normalize_log_level(self.log_level)

    @property
    def database_path(self) -> Path:
        """Return the filesystem path encoded in ``database_url``."""
        return Path(self.database_url.removeprefix(SQLITE_URL_PREFIX))

    def to_logging_config(self) -> LoggingConfig:
        """Build logging configuration derived from application settings."""
        return LoggingConfig(
            log_directory=self.log_directory,
            level=self.effective_log_level,
        )

    def ensure_runtime_directories(self) -> None:
        """Create directories required for logging and local data storage."""
        self.log_directory.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        # model_path is intentionally NOT created here: InsightFaceLoader and
        # scripts/download_models.py own it, and creating it unconditionally
        # would hide the actual AI dependency (P2-b fix).
        if self.output_root is not None:
            self.output_root.mkdir(parents=True, exist_ok=True)
        # archive_root 不在此无条件 mkdir：归档前 ArchivePlanner /
        # ArchiveExecutor 会显式校验并创建，避免静默落盘到未配置的默认路径。
        if self.archive_root is not None:
            self.archive_root.mkdir(parents=True, exist_ok=True)
