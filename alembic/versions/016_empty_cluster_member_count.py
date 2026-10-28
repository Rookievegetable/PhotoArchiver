"""face_clusters.member_count CHECK 放宽到 >= 0（批次级删除：空簇是合法状态）.

revision = "016_empty_cluster_member_count"
down_revision = "015_run_photo_outcome"

Owner 批准的批次级删除功能（D4/D7，2026-10-28）：按识别运行删除照片登记后，
簇成员关系随 ``face_observations`` 外键级联消失——**空簇是删除后的合法状态**，
``face_clusters.member_count`` 必须允许 0，删除服务才能把计数回写为真实值。

006 建表时的 ``CHECK (member_count >= 1)`` 表达的是"簇创建时至少有一个成员"
的**创建期**事实；照片删除打破了它——成员行可以晚于簇消失。存量库已经存在
这种失真（成员行没了、计数停在旧值），正是批次删除要修的问题。

- **库层**：SQLite 无法 ALTER CHECK——沿用 010/013 的 rename/copy/drop 表
  重建模式，数据逐行原样复制（零改写零丢失），两个命名索引按 006 定义重建。
- **实体层**：``FaceCluster.__post_init__`` 同步放宽为 ``member_count >= 0``
  （与 013 的"实体守卫 + 迁移词表"同构；否则读回 0 成员簇即 ValidationError，
  聚类结果的读取面整体炸掉）。

``downgrade`` 是应急路径：要求库内不存在 0 成员行（否则 CHECK 违反直接失败）。
"""

revision = "016_empty_cluster_member_count"
down_revision = "015_run_photo_outcome"
description = "face_clusters.member_count CHECK 放宽到 >= 0（空簇合法）"

from alembic import op  # noqa: E402  # Alembic migration template convention


def upgrade() -> None:
    """Rebuild ``face_clusters`` with ``CHECK (member_count >= 0)``."""
    # legacy_alter_table=ON：RENAME 不改写依赖方（face_cluster_members /
    # calibration_annotations / calibration_ground_truth 的 REFERENCES）——
    # 否则外键被改写到 __016_old 表名，DROP 后指向不存在的表（013 同陷阱）。
    op.execute("PRAGMA legacy_alter_table=ON")
    op.execute("ALTER TABLE face_clusters RENAME TO face_clusters__016_old")
    op.execute("PRAGMA legacy_alter_table=OFF")
    op.execute("""
        CREATE TABLE face_clusters (
            id TEXT PRIMARY KEY,
            cluster_run_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
            member_count INTEGER NOT NULL DEFAULT 0 CHECK (member_count >= 0),
            first_captured_at TEXT,
            sort_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'confirmed', 'unknown', 'ignored', 'split', 'merged')),
            created_at TEXT NOT NULL,
            FOREIGN KEY(cluster_run_id) REFERENCES face_cluster_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(run_id) REFERENCES recognition_runs(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        INSERT INTO face_clusters
            (id, cluster_run_id, run_id, ordinal, member_count,
             first_captured_at, sort_key, status, created_at)
        SELECT id, cluster_run_id, run_id, ordinal, member_count,
               first_captured_at, sort_key, status, created_at
        FROM face_clusters__016_old
    """)
    op.execute("DROP TABLE face_clusters__016_old")
    # 重建表必丢命名索引——按 006:93-95 的定义重建。
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_face_clusters_cluster_run_id "
        "ON face_clusters(cluster_run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_face_clusters_run_id ON face_clusters(run_id)"
    )


def downgrade() -> None:
    """应急降级：按 006 原始 CHECK（>= 1）重建。

    要求库内不存在 ``member_count = 0`` 的行——有则 INSERT 触发 CHECK 违反
    直接失败（先把这些簇处理掉再降级）。
    """
    op.execute("PRAGMA legacy_alter_table=ON")
    op.execute("ALTER TABLE face_clusters RENAME TO face_clusters__016_old")
    op.execute("PRAGMA legacy_alter_table=OFF")
    op.execute("""
        CREATE TABLE face_clusters (
            id TEXT PRIMARY KEY,
            cluster_run_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
            member_count INTEGER NOT NULL CHECK (member_count >= 1),
            first_captured_at TEXT,
            sort_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'confirmed', 'unknown', 'ignored', 'split', 'merged')),
            created_at TEXT NOT NULL,
            FOREIGN KEY(cluster_run_id) REFERENCES face_cluster_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(run_id) REFERENCES recognition_runs(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        INSERT INTO face_clusters
            (id, cluster_run_id, run_id, ordinal, member_count,
             first_captured_at, sort_key, status, created_at)
        SELECT id, cluster_run_id, run_id, ordinal, member_count,
               first_captured_at, sort_key, status, created_at
        FROM face_clusters__016_old
    """)
    op.execute("DROP TABLE face_clusters__016_old")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_face_clusters_cluster_run_id "
        "ON face_clusters(cluster_run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_face_clusters_run_id ON face_clusters(run_id)"
    )
