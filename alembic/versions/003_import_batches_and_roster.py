"""import drafts and stable roster order — people-import redesign stage A.

Revision ID: 003_import_batches_and_roster
Revises: 002_split_create_ddl
Create Date: 2026-09-20 00:00:00

owner 业务方案《人员名单导入与人脸分组匹配开发方案》阶段 A（docs/development/
people-import-face-clustering-development-plan.md §3.1/§7）：

- ``import_batches``：一次导入的可追溯容器（draft/confirmed/cancelled）。
- ``import_draft_rows``：确认前的可编辑草稿行（原始值、解析字段、告警、动作、顺序）。
- ``people`` 扩列：``roster_order``（用户确认的名单顺序）、``source_batch_id``
  （人员来源追踪，可空 FK）。

幂等守护与既有约定一致（IF NOT EXISTS / 逆序 DROP）。
"""

revision = "003_import_batches_and_roster"
down_revision = "002_split_create_ddl"
description = "import batches, draft rows and stable roster order — stage A"

from alembic import op  # noqa: E402, F401  # Alembic migration template convention


def upgrade() -> None:
    """Create import draft tables and extend people with roster columns."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS import_batches (
            id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            source_type TEXT NOT NULL,
            encoding TEXT,
            delimiter TEXT,
            has_header INTEGER NOT NULL DEFAULT 1,
            sheet_name TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL,
            confirmed_at TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS import_draft_rows (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            source_row INTEGER NOT NULL,
            raw_values TEXT NOT NULL,
            parsed_name TEXT,
            parsed_identity TEXT,
            parsed_department TEXT,
            parsed_note TEXT,
            parsed_group TEXT,
            warnings TEXT NOT NULL DEFAULT '[]',
            action TEXT NOT NULL DEFAULT 'create',
            merge_target_id TEXT,
            order_index INTEGER NOT NULL,
            FOREIGN KEY(batch_id) REFERENCES import_batches(id) ON DELETE CASCADE,
            FOREIGN KEY(merge_target_id) REFERENCES people(id) ON DELETE SET NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_import_draft_rows_batch ON import_draft_rows(batch_id)")
    op.execute("ALTER TABLE people ADD COLUMN roster_order INTEGER")
    op.execute("ALTER TABLE people ADD COLUMN source_batch_id TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_people_roster_order ON people(roster_order)")


def downgrade() -> None:
    """Drop import draft tables and remove the people roster columns."""
    op.execute("DROP INDEX IF EXISTS idx_people_roster_order")
    op.execute("DROP TABLE IF EXISTS import_draft_rows")
    op.execute("DROP TABLE IF EXISTS import_batches")
    # SQLite 3.35+ 支持 DROP COLUMN；为兼容旧库文件采用 12 步重建方式过于
    # 冗长——项目基线（Python 3.11 自带 SQLite ≥ 3.37）支持 DROP COLUMN。
    op.execute("ALTER TABLE people DROP COLUMN roster_order")
    op.execute("ALTER TABLE people DROP COLUMN source_batch_id")
