"""cluster_person_assignments 状态/来源词表扩展 auto_confirmed（S4 冷启动位置自动确认）.

revision = "013_assignment_auto_confirm"
down_revision = "012_single_expert_ground_truth"

Owner 裁决（2026-10-10，C-1 任务书 §2）：

- ``status`` CHECK 扩展 ``'auto_confirmed'``：S4 冷启动位置规则自动确认的
  专用态（机器产生，D1=A：不进入投影支撑集，不直接驱动归档）。
- ``source`` CHECK 扩展 ``'ordered_auto_confirm'``：位置自动确认的专用来源
  （机器来源，score 恒 NULL——BD-4：位置配对不得伪造相似度证据）。
- 组合约束（auto_confirmed ⇒ ordered_auto_confirm ∧ score IS NULL；自动来源
  行不得 confirmed）由**领域实体守卫**承载（``cluster_assignment.py`` 构造期
  校验 + ``auto_confirm()``/``confirm()`` 守卫）——本迁移只扩展词表，与 010
  同口径，不加跨列 CHECK。

SQLite 无法 ALTER CHECK——沿用 010 的 rename/copy/drop 表重建模式：

- ``PRAGMA legacy_alter_table=ON``：RENAME 不改写依赖方（
  ``recognition_results.assignment_id`` 的 REFERENCES）——否则外键被改写到
  ``__013_old`` 表名，DROP 后指向不存在的表（009 测试实测抓到，010:28-30 记录）。
- ``alembic/env.py`` 从不设置 ``PRAGMA foreign_keys``（迁移期 FK 不强制）。
- 重建会丢失命名索引——必须按 007:71-77 / 009:71-74 的定义重建三个索引。

**downgrade 是有损应急路径（owner 已批准）**：``auto_confirmed → suggested``、
``ordered_auto_confirm → ordered_suggestion``。该映射**丢失**"位置自动确认"
状态与专用来源的区分——降级后无法从数据分辨哪些行曾是自动确认（历史可追溯性
在 S4 词表内不可恢复）。其余状态与来源按原值保留。
"""

revision = "013_assignment_auto_confirm"
down_revision = "012_single_expert_ground_truth"
description = "cluster_person_assignments 状态/来源 CHECK 扩展（S4 冷启动位置自动确认）"

from alembic import op  # noqa: E402  # Alembic migration template convention


def upgrade() -> None:
    """Rebuild the table with extended status/source CHECK vocabularies.

    数据逐行原样复制（全部列、全部原始值，零改写零丢失）；三个命名索引按
    007/009 定义重建。
    """
    # legacy_alter_table=ON：RENAME 不改写依赖方（recognition_results.assignment_id）
    # 的 REFERENCES 子句——否则外键被改写到 __013_old 表名，DROP 后指向不存在的表
    #（010 实测陷阱，见其 upgrade 注释）。
    op.execute("PRAGMA legacy_alter_table=ON")
    op.execute("ALTER TABLE cluster_person_assignments RENAME TO cluster_person_assignments__013_old")
    op.execute("PRAGMA legacy_alter_table=OFF")
    op.execute("""
        CREATE TABLE cluster_person_assignments (
            id TEXT PRIMARY KEY,
            cluster_id TEXT NOT NULL,
            person_id TEXT,
            status TEXT NOT NULL DEFAULT 'suggested'
                CHECK (status IN ('suggested', 'confirmed', 'rejected', 'unassigned',
                                  'auto_confirmed')),
            source TEXT NOT NULL DEFAULT 'ordered_suggestion'
                CHECK (source IN ('ordered_suggestion', 'manual', 'sample_match', 'review',
                                  'ordered_auto_confirm')),
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
        FROM cluster_person_assignments__013_old
    """)
    op.execute("DROP TABLE cluster_person_assignments__013_old")
    # 重建表必丢命名索引——按 007:71-77 与 009:71-74 的定义重建。
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


def downgrade() -> None:
    """有损应急降级（owner 已批准的映射）。

    ``auto_confirmed → suggested``、``ordered_auto_confirm → ordered_suggestion``。
    **该映射丢失自动确认状态与专用来源的区分**（见模块 docstring）——降级后的库
    无法从数据分辨哪些行曾是位置自动确认。其余状态与来源按原值保留。
    """
    op.execute("DROP INDEX IF EXISTS idx_cpa_cluster_latest")
    op.execute("DROP INDEX IF EXISTS idx_cluster_person_assignments_person_id")
    op.execute("DROP INDEX IF EXISTS idx_cluster_person_assignments_cluster_id")
    # 有损映射（owner 批准）：先在原表上改写，再按旧 CHECK 重建。
    op.execute(
        "UPDATE cluster_person_assignments SET status = 'suggested' "
        "WHERE status = 'auto_confirmed'"
    )
    op.execute(
        "UPDATE cluster_person_assignments SET source = 'ordered_suggestion' "
        "WHERE source = 'ordered_auto_confirm'"
    )
    op.execute("PRAGMA legacy_alter_table=ON")
    op.execute("ALTER TABLE cluster_person_assignments RENAME TO cluster_person_assignments__013_old")
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
        FROM cluster_person_assignments__013_old
    """)
    op.execute("DROP TABLE cluster_person_assignments__013_old")
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
