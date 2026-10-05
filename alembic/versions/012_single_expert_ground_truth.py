"""calibration_ground_truth 收敛到单专家协议（S4-B-2 D-2 = Single Human Expert）.

revision = "012_single_expert_ground_truth"
down_revision = "011_calibration_annotations"

Owner 裁决 ``S4B2-D2-SINGLE-EXPERT-PROTOCOL-APPROVED``：每簇一条专家标注
直接构成真值 —— ``resolution`` 词表从 ``('agreed','adjudicated')`` 收敛为
``('expert')``，``annotator_count == 1 == len(source_annotation_ids)``；
双标共识与仲裁已废止，``adjudicated_by`` 列随旧语义一并移除。

SQLite 无法 ALTER CHECK —— 按 008/010 的 rename/copy/drop 模式重建表。
FK 安全性：``calibration_ground_truth`` 不是任何表的 FK 父表，RENAME 不会
改写依赖方的 REFERENCES（``alembic/env.py`` 迁移期不设 ``PRAGMA foreign_keys``）。
重建会丢失命名索引——必须按 011 的定义重建（idx_calib_gt_cluster /
idx_calib_gt_dataset，008:108-109 已记录该陷阱）。

数据策略（有损，显式记录）：旧词表行与 'expert' 不可映射——诚实性优先，
upgrade 清空本表而非把旧词表行改写成 'expert'（伪造来源）。生产库该表为空；
任何含旧词表行的评估库在升级前应另行归档导出。downgrade 同理清空（'expert'
行无法映射回 ('agreed','adjudicated')）。

downgrade：按 011 原样重建（含 ``adjudicated_by`` 列与旧 CHECK），供迁移
回归测试往返；为有损应急路径。
"""

revision = "012_single_expert_ground_truth"
down_revision = "011_calibration_annotations"
description = "calibration_ground_truth resolution 收敛 'expert'，移除 adjudicated_by（S4-B-2 单专家协议）"

from alembic import op  # noqa: E402  # Alembic migration template convention


def upgrade() -> None:
    # legacy_alter_table=ON：RENAME 不改写依赖方 REFERENCES（本表无依赖方，
    # 沿用 010 同款防御模式）。
    op.execute("PRAGMA legacy_alter_table=ON")
    op.execute("ALTER TABLE calibration_ground_truth RENAME TO calibration_ground_truth__012_old")
    op.execute("PRAGMA legacy_alter_table=OFF")
    op.execute("""
        CREATE TABLE calibration_ground_truth (
            id TEXT PRIMARY KEY,
            cluster_id TEXT NOT NULL,
            verdict TEXT NOT NULL
                CHECK (verdict IN ('person', 'out_of_roster', 'undecidable')),
            person_id TEXT,
            difficulty_reason TEXT,
            resolution TEXT NOT NULL
                CHECK (resolution IN ('expert')),
            source_annotation_ids TEXT NOT NULL,
            annotator_count INTEGER NOT NULL
                CHECK (annotator_count = 1),
            dataset_id TEXT,
            dataset_version TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (cluster_id) REFERENCES face_clusters(id) ON DELETE CASCADE,
            FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE SET NULL,
            CHECK ((verdict = 'person' AND person_id IS NOT NULL)
                OR (verdict <> 'person' AND person_id IS NULL)),
            -- 难例分类必须贯通 Annotation → GroundTruth → Dataset（S4-B-1 B-1）：
            -- undecidable 必须给出原因，且只有 undecidable 允许带原因。
            CHECK (difficulty_reason IS NULL OR verdict = 'undecidable'),
            CHECK (verdict <> 'undecidable' OR difficulty_reason IS NOT NULL)
        )
    """)
    # 旧词表行不可诚实映射为 'expert' —— 清空而非伪造来源（见模块 docstring）。
    op.execute("DROP TABLE calibration_ground_truth__012_old")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_calib_gt_cluster "
        "ON calibration_ground_truth(cluster_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_calib_gt_dataset "
        "ON calibration_ground_truth(dataset_id, dataset_version)"
    )


def downgrade() -> None:
    op.execute("PRAGMA legacy_alter_table=ON")
    op.execute("ALTER TABLE calibration_ground_truth RENAME TO calibration_ground_truth__012_new")
    op.execute("PRAGMA legacy_alter_table=OFF")
    op.execute("""
        CREATE TABLE calibration_ground_truth (
            id TEXT PRIMARY KEY,
            cluster_id TEXT NOT NULL,
            verdict TEXT NOT NULL
                CHECK (verdict IN ('person', 'out_of_roster', 'undecidable')),
            person_id TEXT,
            difficulty_reason TEXT,
            resolution TEXT NOT NULL
                CHECK (resolution IN ('agreed', 'adjudicated')),
            source_annotation_ids TEXT NOT NULL,
            annotator_count INTEGER NOT NULL,
            adjudicated_by TEXT,
            dataset_id TEXT,
            dataset_version TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (cluster_id) REFERENCES face_clusters(id) ON DELETE CASCADE,
            FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE SET NULL,
            CHECK ((verdict = 'person' AND person_id IS NOT NULL)
                OR (verdict <> 'person' AND person_id IS NULL)),
            CHECK (difficulty_reason IS NULL OR verdict = 'undecidable'),
            CHECK (verdict <> 'undecidable' OR difficulty_reason IS NOT NULL)
        )
    """)
    # 'expert' 行无法映射回废止词表 —— 降级清空（有损应急路径，见模块 docstring）。
    op.execute("DROP TABLE calibration_ground_truth__012_new")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_calib_gt_cluster "
        "ON calibration_ground_truth(cluster_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_calib_gt_dataset "
        "ON calibration_ground_truth(dataset_id, dataset_version)"
    )
