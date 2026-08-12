"""split create DDL from initialize_schema — ADR-027 phase 2.

Revision ID: 002_split_create_ddl
Revises: 001_initial_v4
Create Date: 2026-08-12 00:00:00

ADR-027（Accepted 2026-08-12，前置门拍板，定稿草案
``docs/development/phase2-adr-draft.md``）：

- 裁决点 1=A：migration 全接管 6 表 + 6 索引 DDL（people / folders / photos /
  recognition_results / person_embeddings / archive_records），迁自
  ``sqlite_connection.py:109-206`` 的 ``initialize_schema()`` raw SQL。
- 裁决点 2=B：新建本 002 持 DDL，``001_initial_v4`` 保留空 stamp 形态
  （避免改造 upgrade/downgrade 的首次 migration 无前版本可回难题）。
- 幂等守护：``CREATE TABLE IF NOT EXISTS`` + ``CREATE INDEX IF NOT EXISTS`` +
  ``DROP TABLE IF EXISTS`` + ``DROP INDEX IF EXISTS``——migration 在已由
  ``initialize_schema()`` 创建的库上重复执行不报错。
- FK 依赖逆序 DROP：archive_records → recognition_results → person_embeddings →
  photos → folders → people（子表先 DROP 避引用错）。
"""

revision = "002_split_create_ddl"
down_revision = "001_initial_v4"
description = "split create DDL from initialize_schema — ADR-027 phase 2"

from alembic import op  # noqa: E402, F401  # Alembic migration template convention


def upgrade() -> None:
    """Create 6 tables + 6 indexes (迁自 initialize_schema raw SQL).

    在已由 ``initialize_schema()`` ``CREATE TABLE IF NOT EXISTS`` 的库上幂等——
    IF NOT EXISTS 守护重复执行不报错。新库由 ``initialize_schema()`` 调
    ``run_alembic_migrations()`` 触发本 migration 真正创建表。
    """
    # ── 6 表 DDL（与 initialize_schema() 原始 raw SQL 一致，不改表结构） ────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            identity TEXT UNIQUE,
            department TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS folders (
            id TEXT PRIMARY KEY,
            raw_path TEXT NOT NULL,
            path_base TEXT NOT NULL,
            display_name TEXT,
            total_photos INTEGER NOT NULL,
            scanned_photos INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(raw_path, path_base)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS photos (
            id TEXT PRIMARY KEY,
            raw_path TEXT NOT NULL,
            path_base TEXT NOT NULL,
            folder_id TEXT,
            original_name TEXT,
            created_at TEXT NOT NULL,
            captured_at TEXT,
            metadata_width INTEGER,
            metadata_height INTEGER,
            metadata_file_size_bytes INTEGER,
            metadata_modified_at TEXT,
            metadata_content_hash TEXT,
            UNIQUE(raw_path, path_base),
            FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS recognition_results (
            id TEXT PRIMARY KEY,
            photo_id TEXT NOT NULL,
            person_id TEXT,
            status TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE,
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS person_embeddings (
            person_id TEXT PRIMARY KEY,
            embedding BLOB NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS archive_records (
            id TEXT PRIMARY KEY,
            photo_id TEXT NOT NULL,
            target_archive_root TEXT NOT NULL,
            target_person_name TEXT NOT NULL,
            target_event_or_date TEXT NOT NULL,
            target_original_name TEXT NOT NULL,
            status TEXT NOT NULL,
            archived_at TEXT,
            error TEXT,
            FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
        )
        """
    )

    # ── 6 索引（与 initialize_schema() 原始 raw SQL 一致） ──────────────────
    op.execute("CREATE INDEX IF NOT EXISTS idx_photos_folder_id ON photos(folder_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_recognition_results_photo_id "
        "ON recognition_results(photo_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_recognition_results_person_id "
        "ON recognition_results(person_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_archive_records_photo_id "
        "ON archive_records(photo_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_archive_records_status "
        "ON archive_records(status)"
    )


def downgrade() -> None:
    """DROP 6 表（FK 依赖逆序：子表先 DROP 避引用错）.

    回滚到 ``001_initial_v4`` 空 stamp 状态——表全 DROP，alembic_version
    回退至 001。幂等守护：``DROP TABLE IF EXISTS`` 容重复执行。
    """
    # 子表先 DROP（FK 依赖逆序）：archive_records → recognition_results →
    # person_embeddings → photos → folders → people
    op.execute("DROP TABLE IF EXISTS archive_records")
    op.execute("DROP TABLE IF EXISTS recognition_results")
    op.execute("DROP TABLE IF EXISTS person_embeddings")
    op.execute("DROP TABLE IF EXISTS photos")
    op.execute("DROP TABLE IF EXISTS folders")
    op.execute("DROP TABLE IF EXISTS people")
