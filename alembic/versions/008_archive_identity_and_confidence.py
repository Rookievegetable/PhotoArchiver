"""archive record person identity + nullable recognition confidence.

Revision ID: 008_archive_identity_and_confidence
Revises: 007_assignments_and_person_samples
Create Date: 2026-09-27 00:00:00

Stage 4 冻结阻断项修复（BLK-1 + BLK-5）：

- **BLK-1（归档去重身份错误）**：``archive_records`` 原先**没有** person 身份列，
  成功态去重只能按 ``target_person_name`` 字符串匹配。两个后果：
  (1) 跨部门同名的两个独立 person 会互相抑制归档；
  (2) person 改名后新姓名查不到旧记录 -> 同一张照片被重复归档。
  本 migration 增 ``person_id``（FK → people，ON DELETE SET NULL）并**回填**
  存量行；去重语义随之改为按稳定 Person identity（详见
  ``sqlite_archive_record_repository.has_successful_for_person``）。
  回填规则：``person_id IS NULL AND target_person_name`` 唯一命中某个 people.name
  时回填；重名（多命中）保持 NULL，回退到姓名匹配——宁可沿用旧语义，
  也不猜错身份（误回填会把 A 的归档记到 B 头上）。
- **BLK-5（位置配对置信度语义）**：``recognition_results.confidence`` 原为
  ``NOT NULL``，导致"没有相似度证据"（位置配对，``assignment.score IS NULL``）
  只能被写成 ``0.0``，把"无证据"错误表达成"相似度为零"。本 migration 放宽为
  可空：``NULL`` = 该归属**无相似度证据**（人工按位置/指派确认），
  数值 = 样本匹配的真实余弦。二者语义不再混同。

既有表与数据全部保留：仅新增列（幂等守护：重复执行时先探测列是否存在）。
``downgrade`` 反向删列 + 删索引。
"""

revision = "008_archive_identity_and_confidence"
down_revision = "007_assignments_and_person_samples"
description = "archive dedup by stable person identity; nullable confidence"

from alembic import op  # noqa: E402, F401  # Alembic migration template convention
import sqlalchemy as sa  # noqa: E402  # Alembic migration template convention


def _column_names(table: str) -> set[str]:
    """Return the existing column names of ``table`` via the live connection."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    """Add person_id to archive_records (backfilled) and allow NULL confidence."""
    if "person_id" not in _column_names("archive_records"):
        # SQLite 允许 ADD COLUMN 带 REFERENCES，前提是该列默认 NULL（本列可空，
        # 存量行回填前为 NULL）——故 person_id 拥有真实的 FK 约束与
        # ON DELETE SET NULL 语义，与 recognition_results.person_id 一致。
        op.execute(
            "ALTER TABLE archive_records ADD COLUMN person_id TEXT "
            "REFERENCES people(id) ON DELETE SET NULL"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_archive_records_person_id "
            "ON archive_records(person_id)"
        )
        # 回填：仅在姓名**唯一**命中某个 people.name 时回填；重名保持 NULL。
        # 用子查询计数（不用 HAVING——UPDATE 的子查询里 HAVING 会报
        # "HAVING clause on a non-aggregate query"）。
        op.execute(
            """
            UPDATE archive_records
               SET person_id = (
                   SELECT p.id FROM people p
                    WHERE p.name = archive_records.target_person_name
                      AND (
                          SELECT COUNT(*) FROM people p2
                           WHERE p2.name = archive_records.target_person_name
                      ) = 1
               )
             WHERE person_id IS NULL
            """
        )

    if "confidence" in _column_names("recognition_results"):
        # SQLite 无法用 ALTER 放宽 NOT NULL —— 重建表（保留数据 + 索引）。
        op.execute(
            "ALTER TABLE recognition_results RENAME TO "
            "recognition_results__008_old"
        )
        op.execute(
            """
            CREATE TABLE recognition_results (
                id TEXT PRIMARY KEY,
                photo_id TEXT NOT NULL,
                person_id TEXT,
                status TEXT NOT NULL,
                confidence REAL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE,
                FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE SET NULL
            )
            """
        )
        op.execute(
            """
            INSERT INTO recognition_results (
                id, photo_id, person_id, status, confidence, created_at
            )
            SELECT id, photo_id, person_id, status, confidence, created_at
              FROM recognition_results__008_old
            """
        )
        op.execute("DROP TABLE recognition_results__008_old")
        # 重建表会丢失命名索引——必须按 002 的定义重建（表名/列名不变，
        # 仅 confidence 由 NOT NULL 放宽为可空）。
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_recognition_results_photo_id "
            "ON recognition_results(photo_id)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_recognition_results_person_id "
            "ON recognition_results(person_id)"
        )


def downgrade() -> None:
    """Restore NOT NULL confidence and drop the person_id column."""
    if "confidence" in _column_names("recognition_results"):
        # 回填 NULL confidence（BLK-5 引入的"无证据"行）为 0.0 以满足旧 NOT NULL。
        op.execute("UPDATE recognition_results SET confidence = 0 WHERE confidence IS NULL")
        op.execute(
            "ALTER TABLE recognition_results RENAME TO "
            "recognition_results__008_down"
        )
        op.execute(
            """
            CREATE TABLE recognition_results (
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
            INSERT INTO recognition_results (
                id, photo_id, person_id, status, confidence, created_at
            )
            SELECT id, photo_id, person_id, status, confidence, created_at
              FROM recognition_results__008_down
            """
        )
        op.execute("DROP TABLE recognition_results__008_down")
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_recognition_results_photo_id "
            "ON recognition_results(photo_id)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_recognition_results_person_id "
            "ON recognition_results(person_id)"
        )

    op.execute("DROP INDEX IF EXISTS idx_archive_records_person_id")
    if "person_id" in _column_names("archive_records"):
        op.execute("ALTER TABLE archive_records DROP COLUMN person_id")
