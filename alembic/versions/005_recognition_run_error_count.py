"""add detection error count to recognition runs.

Revision ID: 005_recognition_run_error_count
Revises: 004_recognition_runs_and_observations
"""
revision = "005_recognition_run_error_count"
down_revision = "004_recognition_runs_and_observations"
description = "track per-photo detector errors in recognition run statistics"

from alembic import op  # noqa: E402, F401


def upgrade() -> None:
    """Add a non-negative detector error counter with a safe default."""
    op.execute(
        "ALTER TABLE recognition_runs "
        "ADD COLUMN error_count INTEGER NOT NULL DEFAULT 0 "
        "CHECK (error_count >= 0)"
    )


def downgrade() -> None:
    """Remove the detector error counter."""
    op.execute("ALTER TABLE recognition_runs DROP COLUMN error_count")
