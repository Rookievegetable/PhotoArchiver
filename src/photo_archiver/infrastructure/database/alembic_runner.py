"""Alembic runner — applies pending migrations at application startup.

Called from ``bootstrap.py`` after ``SQLiteConnectionProvider.initialize_schema()``
creates the tables.  Alembic detects the current ``PRAGMA user_version`` and
applies any pending migrations from ``alembic/versions/``.
"""

from pathlib import Path

from alembic.config import Config
from alembic import command
from loguru import logger

_ALEMBIC_CFG_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "alembic.ini"  # 5×parent: file→database→infrastructure→photo_archiver→src→project root

def run_alembic_migrations(database_path: Path) -> None:
    """Run Alembic migrations against the given SQLite database.

    Args:
        database_path: Absolute path to the SQLite database file.
    """
    alembic_cfg = Config(str(_ALEMBIC_CFG_PATH))
    # Override the placeholder URL with the runtime path.
    url = f"sqlite:///{database_path.as_posix()}"
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    # Resolve script_location relative to the ini file's parent directory.
    script_location = str(_ALEMBIC_CFG_PATH.resolve().parent / "alembic")
    alembic_cfg.set_main_option("script_location", script_location)

    logger.info("Running Alembic migrations against {}", database_path)
    try:
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations up to date (HEAD)")
    except Exception:
        logger.exception("Alembic migration failed against {}", database_path)
        raise
