"""initial v4 schema — stamp existing database state.

Revision ID: 001_initial_v4
Revises: None (first migration)
Create Date: 2026-07-25 13:20:00
"""

revision = "001_initial_v4"
down_revision = None
description = "initial v4 schema — stamp existing database state"

from alembic import op  # noqa: E402, F401  # Alembic migration template convention: op available at module level for upgrade()/downgrade()


def upgrade() -> None:
    """Stamps the current v4 schema.

    The tables are created by ``sqlite_connection.py``'s ``initialize_schema()``
    using raw SQL.  This migration DOES NOT recreate them — it only stamps the
    version so Alembic knows the database is at v4.

    When a brand-new database is created by ``initialize_schema()`` (which sets
    ``PRAGMA user_version = 4``), Alembic's ``stamp`` detects the version and
    skips this migration.  On pre-existing databases the stamp ensures Alembic
    considers them current.
    """
    # Nothing to do — the schema is created by initialize_schema().
    # Alembic's version table (alembic_version) is managed by the env.py flow.
    pass


def downgrade() -> None:
    """Reverse the initial stamp — no-op since we didn't create any tables."""
    pass
