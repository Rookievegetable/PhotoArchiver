"""cluster_person_assignments.source 扩展 "review"（S1-F / D-2 = B）.

revision = "010_assignment_source_review"
down_revision = "009_projection_ownership"

S1-F 把审核中心的身份确认迁入 Assignment SSOT：Review 批准产生
``source='review', status='confirmed'`` 的决策行（与人工指派同等最终，S0 INV-4）。
007 的 ``source`` CHECK 只允许 ``('ordered_suggestion','manual','sample_match')``，
SQLite 无法 ALTER CHECK——按 008 的 rename/copy/drop 模式重建表。

FK 安全性：``cluster_person_assignments`` 不是任何表的 FK 父表，RENAME 不会改写
依赖方的 REFERENCES；``alembic/env.py`` 从不设置 ``PRAGMA foreign_keys``（迁移期
FK 不强制）。重建会丢失命名索引——必须按 007:71-77 的定义重建（008:108-109
已记录该陷阱）。

downgrade：先把 ``source='review'`` 行改写为 ``'manual'``（语义同属人工决策），
再按旧 CHECK 重建。降级是有损应急路径，与 008 降级回填 ``confidence=0`` 同一性质。
"""

revision = "010_assignment_source_review"
down_revision = "009_projection_ownership"
description = "cluster_person_assignments.source CHECK 扩展 'review'（S1-F 审核身份决策）"

from alembic import op  # noqa: E402  # Alembic migration template convention


def upgrade() -> None:
    # legacy_alter_table=ON：RENAME 不改写依赖方（recognition_results.assignment_id）
    # 的 REFERENCES 子句——否则外键被改写到 __010_old 表名，DROP 后指向不存在的表
    #（009 测试实测抓到）。
    op.execute("PRAGMA legacy_alter_table=ON")
    op.execute("ALTER TABLE cluster_person_assignments RENAME TO cluster_person_assignments__010_old")
    op.execute("PRAGMA legacy_alter_table=OFF")
    op.execute("""
        CREATE TABLE cluster_person_assignments (
            id TEXT PRIMARY KEY,
            cluster_id TEXT NOT NULL,
            person_id TEXT,
            status TEXT NOT NULL DEFAULT 'suggested'
                CHECK (status IN ('suggested', 'confirmed', 'rejected', 'unassigned')),
            source TEXT NOT NULL DEFAULT 'ordered_suggestion'
                CHECK (source IN ('ordered_suggestion', 'manual', 'sample_match', 'review')),
            score REAL
                CHECK (score IS NULL OR (score >= -1.0 AND score <= 1.0)),
            sort_snapshot TEXT NOT NULL DEFAULT '{}',
            error TEXT,
            created_at TEXT NOT NULL,
            confirmed_at TEXT,
            FOREIGN KEY (cluster_id) REFERENCES face_clusters(id) ON DELETE CASCADE,
            FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        INSERT INTO cluster_person_assignments
            (id, cluster_id, person_id, status, source, score, sort_snapshot,
             error, created_at, confirmed_at)
        SELECT id, cluster_id, person_id, status, source, score, sort_snapshot,
               error, created_at, confirmed_at
        FROM cluster_person_assignments__010_old
    """)
    op.execute("DROP TABLE cluster_person_assignments__010_old")
    # 重建表必丢命名索引——必须按 007:71-77 的定义重建。
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cluster_person_assignments_cluster_id "
        "ON cluster_person_assignments(cluster_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cluster_person_assignments_person_id "
        "ON cluster_person_assignments(person_id)"
    )
    # 009 引入的"最新决策"复合索引随表重建一并恢复。
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cpa_cluster_latest "
        "ON cluster_person_assignments(cluster_id, created_at DESC, id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cpa_cluster_latest")
    op.execute("DROP INDEX IF EXISTS idx_cluster_person_assignments_person_id")
    op.execute("DROP INDEX IF EXISTS idx_cluster_person_assignments_cluster_id")
    # 有损应急：review 决策在旧词表中并入 manual（同为人工来源，INV-4 语义不变）。
    op.execute(
        "UPDATE cluster_person_assignments SET source = 'manual' WHERE source = 'review'"
    )
    op.execute("ALTER TABLE cluster_person_assignments RENAME TO cluster_person_assignments__010_old")
    op.execute("""
        CREATE TABLE cluster_person_assignments (
            id TEXT PRIMARY KEY,
            cluster_id TEXT NOT NULL,
            person_id TEXT,
            status TEXT NOT NULL DEFAULT 'suggested'
                CHECK (status IN ('suggested', 'confirmed', 'rejected', 'unassigned')),
            source TEXT NOT NULL DEFAULT 'ordered_suggestion'
                CHECK (source IN ('ordered_suggestion', 'manual', 'sample_match')),
            score REAL
                CHECK (score IS NULL OR (score >= -1.0 AND score <= 1.0)),
            sort_snapshot TEXT NOT NULL DEFAULT '{}',
            error TEXT,
            created_at TEXT NOT NULL,
            confirmed_at TEXT,
            FOREIGN KEY (cluster_id) REFERENCES face_clusters(id) ON DELETE CASCADE,
            FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        INSERT INTO cluster_person_assignments
            (id, cluster_id, person_id, status, source, score, sort_snapshot,
             error, created_at, confirmed_at)
        SELECT id, cluster_id, person_id, status, source, score, sort_snapshot,
               error, created_at, confirmed_at
        FROM cluster_person_assignments__010_old
    """)
    op.execute("DROP TABLE cluster_person_assignments__010_old")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cluster_person_assignments_cluster_id "
        "ON cluster_person_assignments(cluster_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cluster_person_assignments_person_id "
        "ON cluster_person_assignments(person_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cpa_cluster_latest "
        "ON cluster_person_assignments(cluster_id, created_at DESC, id DESC)"
    )