"""cluster person assignments and person face samples — stage E.

Revision ID: 007_assignments_and_person_samples
Revises: 006_face_clusters
Create Date: 2026-09-25 00:00:00

owner 批准执行计划 §E-1（原编号 006，因阶段 D 先占 006 顺延为 007）：

- ``cluster_person_assignments``：Cluster → Person 的可追溯身份决策。
  status 四态（suggested/confirmed/rejected/unassigned）+ source 三源
  （ordered_suggestion/manual/sample_match）区分自动建议与人工决策；
  ``score`` 记录样本匹配余弦证据（ordered 建议为 NULL）；``sort_snapshot``
  在确认时保存当时的组排序快照（§5.3：以后补入更早照片不回写已确认映射）。
  同一 cluster 的决策历史以多行表达（当前有效行 = suggested/confirmed）。
- ``person_face_embeddings``：确认映射时从组成员沉淀的人员多样本库
  （D4：后续 1:N 匹配 = 多样本最大余弦）。UNIQUE(person_id,
  observation_id) 杜绝重复沉淀；``enabled`` 为 F 阶段校准预留的启用开关。

既有表及数据全部保留——006 → 007 不迁移任何既有数据。FK 级联：
cluster 删除 → assignments 级联；observation/person 删除 → samples 级联。
"""

revision = "007_assignments_and_person_samples"
down_revision = "006_face_clusters"
description = "cluster person assignments and person face samples — stage E"

from alembic import op  # noqa: E402, F401  # Alembic migration template convention


def upgrade() -> None:
    """Create the 2 stage-E tables + 4 indexes（既有表与数据不动）."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cluster_person_assignments (
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
            FOREIGN KEY(cluster_id) REFERENCES face_clusters(id) ON DELETE CASCADE,
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS person_face_embeddings (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            embedding TEXT NOT NULL,
            quality_score REAL
                CHECK (quality_score IS NULL OR (quality_score >= 0.0 AND quality_score <= 1.0)),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            UNIQUE(person_id, observation_id),
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE,
            FOREIGN KEY(observation_id) REFERENCES face_observations(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cluster_person_assignments_cluster_id "
        "ON cluster_person_assignments(cluster_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cluster_person_assignments_person_id "
        "ON cluster_person_assignments(person_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_person_face_embeddings_person_id "
        "ON person_face_embeddings(person_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_person_face_embeddings_observation_id "
        "ON person_face_embeddings(observation_id)"
    )


def downgrade() -> None:
    """Drop the 2 stage-E tables + 4 indexes（子表先 DROP；IF EXISTS 幂等）."""
    op.execute("DROP INDEX IF EXISTS idx_person_face_embeddings_observation_id")
    op.execute("DROP INDEX IF EXISTS idx_person_face_embeddings_person_id")
    op.execute("DROP INDEX IF EXISTS idx_cluster_person_assignments_person_id")
    op.execute("DROP INDEX IF EXISTS idx_cluster_person_assignments_cluster_id")
    op.execute("DROP TABLE IF EXISTS person_face_embeddings")
    op.execute("DROP TABLE IF EXISTS cluster_person_assignments")
