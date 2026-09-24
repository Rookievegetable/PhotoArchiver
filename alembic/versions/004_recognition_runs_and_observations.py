"""recognition runs and face observations — face-recognition rework stage C.

Revision ID: 004_recognition_runs_and_observations
Revises: 003_import_batches_and_roster
Create Date: 2026-09-24 00:00:00

owner 任务书阶段 C（多脸检测、识别范围选择与可重跑）Commit 1 数据地基：

- ``recognition_runs``：一次识别执行的可追溯容器（created → running →
  completed/failed/cancelled）。``parameters`` 存运行开始时的不可变配置
  快照（JSON，C-SEM-3）；运行结果统计为独立列（face_count /
  unreadable_count / no_face_count / in_scope_photo_count /
  out_of_scope_photo_count），不得覆盖 parameters 写统计。
- ``recognition_run_photos``：run 创建时的照片输入快照（raw_path /
  captured_at，C-SEM-4）。
- ``recognition_run_scopes``：run 选中的人脸数范围（ordinal 保序）。
  UNIQUE 建在 ``(run_id, ordinal)`` 上而非 ``(run_id, min_count,
  max_count)``——SQLite 中 NULL 不参与 UNIQUE 等值判断，值级唯一约束
  对无上限范围（max_count IS NULL）不可靠。
- ``face_observations``：一次 run 中一张照片一张脸的检测记录。
  ``UNIQUE(run_id, photo_id, face_index)`` 从存储层杜绝同 run 重复/覆盖
  （C-SEM-1）；CHECK(photo_face_count >= 1) 落实"0 脸不建 Observation"。

既有表及数据全部保留——003 → 004 不进行任何既有数据迁移。FK 双向
``ON DELETE CASCADE``：照片删除级联删除其 run_photos / observations
（C-SEM-4 派生数据删除语义），run 删除级联删除其全部子行。幂等守护
与 002/003 约定一致（IF NOT EXISTS / IF EXISTS）。
"""

revision = "004_recognition_runs_and_observations"
down_revision = "003_import_batches_and_roster"
description = "recognition runs, run photos/scopes and face observations — stage C"

from alembic import op  # noqa: E402, F401  # Alembic migration template convention


def upgrade() -> None:
    """Create the 4 stage-C tables + 3 indexes（既有表与数据不动）."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS recognition_runs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'created'
                CHECK (status IN ('created', 'running', 'completed', 'failed', 'cancelled')),
            parameters TEXT NOT NULL DEFAULT '{}',
            face_count INTEGER NOT NULL DEFAULT 0 CHECK (face_count >= 0),
            unreadable_count INTEGER NOT NULL DEFAULT 0 CHECK (unreadable_count >= 0),
            no_face_count INTEGER NOT NULL DEFAULT 0 CHECK (no_face_count >= 0),
            in_scope_photo_count INTEGER NOT NULL DEFAULT 0 CHECK (in_scope_photo_count >= 0),
            out_of_scope_photo_count INTEGER NOT NULL DEFAULT 0 CHECK (out_of_scope_photo_count >= 0),
            error TEXT,
            created_at TEXT NOT NULL,
            finished_at TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS recognition_run_photos (
            run_id TEXT NOT NULL,
            photo_id TEXT NOT NULL,
            raw_path_snapshot TEXT NOT NULL,
            captured_at_snapshot TEXT,
            PRIMARY KEY (run_id, photo_id),
            FOREIGN KEY(run_id) REFERENCES recognition_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS recognition_run_scopes (
            run_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            min_count INTEGER NOT NULL CHECK (min_count >= 1),
            max_count INTEGER CHECK (max_count IS NULL OR max_count >= min_count),
            PRIMARY KEY (run_id, ordinal),
            FOREIGN KEY(run_id) REFERENCES recognition_runs(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS face_observations (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            photo_id TEXT NOT NULL,
            face_index INTEGER NOT NULL CHECK (face_index >= 0),
            photo_face_count INTEGER NOT NULL CHECK (photo_face_count >= 1),
            det_score REAL NOT NULL CHECK (det_score >= 0.0 AND det_score <= 1.0),
            bbox TEXT NOT NULL,
            quality_score REAL
                CHECK (quality_score IS NULL OR (quality_score >= 0.0 AND quality_score <= 1.0)),
            embedding TEXT NOT NULL,
            scope_verdict TEXT NOT NULL
                CHECK (scope_verdict IN ('in_selected_scope', 'out_of_selected_scope')),
            UNIQUE(run_id, photo_id, face_index),
            FOREIGN KEY(run_id) REFERENCES recognition_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_recognition_runs_created_at "
        "ON recognition_runs(created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_recognition_run_photos_photo_id "
        "ON recognition_run_photos(photo_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_face_observations_photo_id "
        "ON face_observations(photo_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_face_observations_run_id "
        "ON face_observations(run_id)"
    )


def downgrade() -> None:
    """Drop the 4 stage-C tables + 3 indexes（子表先 DROP；IF EXISTS 幂等）."""
    op.execute("DROP INDEX IF EXISTS idx_face_observations_run_id")
    op.execute("DROP INDEX IF EXISTS idx_face_observations_photo_id")
    op.execute("DROP INDEX IF EXISTS idx_recognition_run_photos_photo_id")
    op.execute("DROP INDEX IF EXISTS idx_recognition_runs_created_at")
    op.execute("DROP TABLE IF EXISTS face_observations")
    op.execute("DROP TABLE IF EXISTS recognition_run_scopes")
    op.execute("DROP TABLE IF EXISTS recognition_run_photos")
    op.execute("DROP TABLE IF EXISTS recognition_runs")
