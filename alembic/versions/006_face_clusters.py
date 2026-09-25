"""face clusters — 人物聚类（阶段 D 第一阶段）.

Revision ID: 006_face_clusters
Revises: 005_recognition_run_error_count
Create Date: 2026-09-25 00:00:00

owner 批准方案（§D-1）+ 裁决（2026-09-25）落地的三张表：

- ``face_cluster_runs``：一次聚类执行的可追溯容器（镜像 Stage C 的
  recognition run 生命周期）。同一 recognition run 可重复聚类，每次执行
  新行；``parameters`` 存执行开始时的不可变参数快照（JSON：算法版本、
  cluster_sim_threshold/consistency_threshold/low_quality_threshold、
  scope_filter）。``algorithm_version`` 独立成列便于跨 run 过滤。
- ``face_clusters``：同一人物的人脸组（不等于 Person，自动认定属
  Stage E）。``run_id`` 直连 recognition run（方案 §D-1 列）+
  ``cluster_run_id`` 代际容器；``ordinal``/``sort_key``/``first_captured_at``
  是方案 §D-3 的稳定排序字段；status 六态按方案 §3.2，本阶段只写
  ``pending``。
- ``face_cluster_members``：Cluster ↔ Observation 可追溯归属；
  ``UNIQUE(cluster_id, observation_id)`` 杜绝同簇重复归属。

既有表及数据全部保留——005 → 006 不迁移任何既有数据。FK 级联：
recognition run 删除 → cluster runs/clusters/members 逐级级联；
observation 删除 → 其成员关系级联（聚类结果随观测消亡，可重新聚类）。
"""

revision = "006_face_clusters"
down_revision = "005_recognition_run_error_count"
description = "face cluster runs, clusters and memberships — stage D"

from alembic import op  # noqa: E402, F401  # Alembic migration template convention


def upgrade() -> None:
    """Create the 3 stage-D tables + 4 indexes（既有表与数据不动）."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS face_cluster_runs (
            id TEXT PRIMARY KEY,
            recognition_run_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'created'
                CHECK (status IN ('created', 'running', 'completed', 'failed', 'cancelled')),
            algorithm_version TEXT NOT NULL,
            parameters TEXT NOT NULL DEFAULT '{}',
            cluster_count INTEGER NOT NULL DEFAULT 0 CHECK (cluster_count >= 0),
            member_count INTEGER NOT NULL DEFAULT 0 CHECK (member_count >= 0),
            excluded_count INTEGER NOT NULL DEFAULT 0 CHECK (excluded_count >= 0),
            error TEXT,
            created_at TEXT NOT NULL,
            finished_at TEXT,
            FOREIGN KEY(recognition_run_id) REFERENCES recognition_runs(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS face_clusters (
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
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS face_cluster_members (
            id TEXT PRIMARY KEY,
            cluster_id TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'auto' CHECK (source IN ('auto', 'manual')),
            confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
            created_at TEXT NOT NULL,
            UNIQUE(cluster_id, observation_id),
            FOREIGN KEY(cluster_id) REFERENCES face_clusters(id) ON DELETE CASCADE,
            FOREIGN KEY(observation_id) REFERENCES face_observations(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_face_cluster_runs_recognition_run_id "
        "ON face_cluster_runs(recognition_run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_face_clusters_cluster_run_id "
        "ON face_clusters(cluster_run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_face_clusters_run_id ON face_clusters(run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_face_cluster_members_cluster_id "
        "ON face_cluster_members(cluster_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_face_cluster_members_observation_id "
        "ON face_cluster_members(observation_id)"
    )


def downgrade() -> None:
    """Drop the 3 stage-D tables + 5 indexes（子表先 DROP；IF EXISTS 幂等）."""
    op.execute("DROP INDEX IF EXISTS idx_face_cluster_members_observation_id")
    op.execute("DROP INDEX IF EXISTS idx_face_cluster_members_cluster_id")
    op.execute("DROP INDEX IF EXISTS idx_face_clusters_run_id")
    op.execute("DROP INDEX IF EXISTS idx_face_clusters_cluster_run_id")
    op.execute("DROP INDEX IF EXISTS idx_face_cluster_runs_recognition_run_id")
    op.execute("DROP TABLE IF EXISTS face_cluster_members")
    op.execute("DROP TABLE IF EXISTS face_clusters")
    op.execute("DROP TABLE IF EXISTS face_cluster_runs")
