"""Alembic migration template for PhotoArchiver.

New migrations are created by copying the latest migration and adjusting
the revision / down_revision identifiers.
"""
revision: str
down_revision: str | None
description: str | None

from typing import Collection

from alembic import op
import sqlalchemy as sa
