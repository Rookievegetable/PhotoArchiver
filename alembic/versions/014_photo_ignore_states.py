"""photo ignore states — 界面优化：照片级忽略（FaceClusterRun + photo_id 作用域）.

Revision ID: 014_photo_ignore_states
Revises: 013_assignment_auto_confirm
Create Date: 2026-10-25 00:00:00

Owner 批准的界面优化基线（§3.1/§3.2）：

- 忽略对象是一张照片在**一个聚类代际**内的参与资格，作用域键为
  ``(cluster_run_id, photo_id)``；不同代际互不影响，也不跨 RecognitionRun。
- 状态持久化，跨应用重启保留，直到用户显式恢复（删除状态行）。
- 忽略照片须同步撤销该照片在作用域内的既有归属投影；撤销走既有
  ``terminate_projection``（approved → rejected，保留审计），Assignment
  决策历史一律不动。恢复不回溯投影。
- FK 级联：聚类代际删除（face_cluster_runs 级联链）或照片删除时，
  忽略状态随之清理——不残留悬空行。
"""

revision = "014_photo_ignore_states"
down_revision = "013_assignment_auto_confirm"
description = "photo ignore states scoped by cluster run + photo"

from alembic import op  # noqa: E402, F401  # Alembic migration template convention


def upgrade() -> None:
    """Create the photo_ignore_states table + 2 indexes（既有表与数据不动）."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS photo_ignore_states (
            id TEXT PRIMARY KEY,
            cluster_run_id TEXT NOT NULL,
            photo_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(cluster_run_id, photo_id),
            FOREIGN KEY(cluster_run_id) REFERENCES face_cluster_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_photo_ignore_states_run "
        "ON photo_ignore_states(cluster_run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_photo_ignore_states_photo "
        "ON photo_ignore_states(photo_id)"
    )


def downgrade() -> None:
    """Drop the table + indexes（IF EXISTS 幂等，逆序 DROP）."""
    op.execute("DROP INDEX IF EXISTS idx_photo_ignore_states_photo")
    op.execute("DROP INDEX IF EXISTS idx_photo_ignore_states_run")
    op.execute("DROP TABLE IF EXISTS photo_ignore_states")
