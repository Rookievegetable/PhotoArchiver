"""recognition_run_photos.photo_outcome — 界面优化：照片级处理结果状态.

Revision ID: 015_run_photo_outcome
Revises: 014_photo_ignore_states
Create Date: 2026-10-25 00:00:00

Owner 批准的界面优化基线（§6）：

- ``recognition_run_photos`` 是 run 启动时的**处理输入快照**；本迁移为其
  增加照片级处理结果列 ``photo_outcome``，至少区分：已处理有脸（faces）/
  已处理 0 脸（no_face）/ 不可读取（unreadable）/ 处理出错（error）/
  尚未处理（not_processed）。
- **历史 run 不伪造回填**：列以 NULL 增加——旧 run 的照片状态保持未知
  （展示为"未知（历史 run）"），不得展示为"0 张人脸"。
- 新 run 在快照写入时即登记 ``not_processed``，处理分支逐照片更新为
  实际结果；取消/失败 run 的未处理照片保持 ``not_processed``。
- "照片是否属于当前 run"仍由本表行存在性判断，不与处理结果混淆。
"""

revision = "015_run_photo_outcome"
down_revision = "014_photo_ignore_states"
description = "per-photo processing outcome on recognition_run_photos"

from alembic import op  # noqa: E402, F401  # Alembic migration template convention


def upgrade() -> None:
    """Add the nullable outcome column（历史行保持 NULL = 未知，不回填）."""
    op.execute(
        """
        ALTER TABLE recognition_run_photos ADD COLUMN photo_outcome TEXT
            CHECK (photo_outcome IS NULL OR photo_outcome IN (
                'not_processed', 'faces', 'no_face', 'unreadable', 'error'
            ))
        """
    )


def downgrade() -> None:
    """Drop the column（项目基线 SQLite ≥ 3.35 支持 DROP COLUMN）."""
    op.execute("ALTER TABLE recognition_run_photos DROP COLUMN photo_outcome")
