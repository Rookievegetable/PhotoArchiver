"""Alembic environment configuration for PhotoArchiver.

Uses raw SQLite connection (not SQLAlchemy ORM) for migrations, matching the
project's existing data-access pattern. Each migration script executes plain SQL
through Alembic's ``op.execute()``.

The runtime database path is injected by :func:`run_migrations` when called
from ``alembic_runner.py`` during bootstrap; the ``alembic.ini`` placeholder
URL is only used for ``alembic revision --autogenerate`` (which is not
supported for raw-SQL migrations — revisions are hand-written).
"""

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic Config object, which provides access to the .ini file values.
config = context.config

# Set up Python logging from the ini file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The target metadata is None because we use raw SQL, not ORM declarative models.
target_metadata = None

# Runtime database path — overridden by set_database_path() before run_migrations().
_database_path: Path | None = None


def set_database_path(path: Path) -> None:
    """Inject the runtime SQLite database path before running migrations."""
    global _database_path
    _database_path = path


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB connection).

    Used for generating migration SQL scripts for review.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the runtime database connection."""
    if _database_path is not None:
        # Override the ini file URL with the resolved runtime path.
        url = f"sqlite:///{_database_path.as_posix()}"
        config.set_main_option("sqlalchemy.url", url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
