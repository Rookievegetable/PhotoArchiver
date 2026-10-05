"""Ground Truth 人工标注体系（S4-B-1）—— 与业务 Assignment 严格分离。

这三张表**不参与**任何业务链：不被 ArchivePlanner/ProjectionReconciler/
Review/Pairing 读取，也不写入 ``cluster_person_assignments`` /
``recognition_results`` / ``person_face_embeddings``。它们只服务于离线阈值
校准（S4-B-2）。

设计要点（对应 S4-B-1 验收标准）：

* **Ground Truth ≠ Business Assignment**。业务链的"人工点了确认"**不等于**
  独立验证真值——本表的标注由独立规程产生，与业务决策流无关。
* **append-only**。标注只追加不覆盖：``calibration_annotations`` 每行是一次
  独立标注或一次仲裁，历史永久保留。
* **显式来源**。``calibration_ground_truth`` 记录最终真值**由哪些 annotation
  支撑**（``source_annotation_ids``），杜绝"最后一次标注即真值"。
* **双人独立 + 仲裁**。冻结数据集只接受「两次独立标注一致」或「经仲裁」的簇；
  单独一条标注永远不能进入数据集。
* **不可判定是一等公民**。``undecidable`` 不被当作负样本，S4-B-2 必须把它
  排除在分母之外——故需要显式标签位而非推断。

刻意**不做**的事：不给业务表加字段、不改 009/010、不引入 threshold/margin、
不实现任何自动确认路径。
"""

revision = "011_calibration_annotations"
down_revision = "010_assignment_source_review"
description = "Ground Truth 人工标注 / 仲裁 / 冻结数据集（S4-B-1，独立于业务 Assignment）"

from alembic import op  # noqa: E402  # Alembic migration template convention

def upgrade() -> None:
    """Create the three calibration tables.

    命名与业务表完全区隔（``calibration_`` 前缀），使"业务链误读标注表"
    成为可被 grep 检出的违规而非静默耦合。
    """
    op.execute("""
        CREATE TABLE IF NOT EXISTS calibration_annotations (
            id TEXT PRIMARY KEY,
            cluster_id TEXT NOT NULL,
            annotator_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'independent'
                CHECK (role IN ('independent', 'adjudication')),
            verdict TEXT NOT NULL
                CHECK (verdict IN ('person', 'out_of_roster', 'undecidable')),
            person_id TEXT,
            difficulty_reason TEXT,
            protocol_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (cluster_id) REFERENCES face_clusters(id) ON DELETE CASCADE,
            FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE SET NULL,
            CHECK ((verdict = 'person' AND person_id IS NOT NULL)
                OR (verdict <> 'person' AND person_id IS NULL)),
            CHECK (difficulty_reason IS NULL OR verdict = 'undecidable')
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_calib_ann_cluster "
        "ON calibration_annotations(cluster_id, role, annotator_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_calib_ann_annotator "
        "ON calibration_annotations(annotator_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS calibration_ground_truth (
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
            -- 难例分类必须贯通 Annotation → GroundTruth → Dataset（S4-B-1 B-1）：
            -- undecidable 必须给出原因，且只有 undecidable 允许带原因。
            CHECK (difficulty_reason IS NULL OR verdict = 'undecidable'),
            CHECK (verdict <> 'undecidable' OR difficulty_reason IS NOT NULL)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_calib_gt_cluster "
        "ON calibration_ground_truth(cluster_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_calib_gt_dataset "
        "ON calibration_ground_truth(dataset_id, dataset_version)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS calibration_datasets (
            -- S4-B-1 B-2：冻结粒度是 (id, version)，不是 id 单列。
            -- CP2.4 要求"新版本是新行，不修改旧行"，单列 PK 会让同一数据集只能有
            -- 一个版本并静默覆盖。复合主键允许 (X,v1) 与 (X,v2) 共存，同时拒绝
            -- (X,v1) 重复。
            id TEXT NOT NULL,
            version TEXT NOT NULL,
            protocol_version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'frozen'
                CHECK (status IN ('frozen')),
            cluster_count INTEGER NOT NULL DEFAULT 0,
            usable_count INTEGER NOT NULL DEFAULT 0,
            excluded_count INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (id, version)
        )
    """)


def downgrade() -> None:
    """Drop the calibration tables (independent of business data)."""
    op.execute("DROP INDEX IF EXISTS idx_calib_gt_dataset")
    op.execute("DROP INDEX IF EXISTS idx_calib_gt_cluster")
    op.execute("DROP INDEX IF EXISTS idx_calib_ann_annotator")
    op.execute("DROP INDEX IF EXISTS idx_calib_ann_cluster")
    op.execute("DROP TABLE IF EXISTS calibration_datasets")
    op.execute("DROP TABLE IF EXISTS calibration_ground_truth")
    op.execute("DROP TABLE IF EXISTS calibration_annotations")