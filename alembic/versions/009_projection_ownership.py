"""recognition_results.assignment_id — Assignment 支撑的投影归属 (S1 Phase B).

revision = "009_projection_ownership"
down_revision = "008_archive_identity_and_confidence"

S1 把 ``recognition_results`` 的 ``approved`` 行按来源分为两类（ADR-044 E-SG-6
的 ``(person, photo)`` 作用域不变）：

* **legacy 人工决策** —— ``assignment_id IS NULL``。ADR-045 D-1 的审核批准行
  属于此类：它们是人工裁决，从不经过 Assignment 表。S0 INV-4（machine 不得撤销
  manual decision）要求它们**不被 reconcile / rebuild 触碰**。
* **Assignment-derived projection** —— ``assignment_id IS NOT NULL``。由配对
  工作台确认写入，其存在性由「该 ``(photo, person)`` 是否仍有 active supporting
  Assignment」决定。

``assignment_id`` 是**当前 supporting Assignment 的引用**，不是永久 owner：一个
pair 可被多个 Assignment 支撑（同一簇跨多照片 ⇒ 1 Assignment 对应 N projection；
同一 pair 也可被不同簇/不同代际的 Assignment 同时支撑），支撑全部失效时投影才
终结。

``ON DELETE SET NULL``：删人时 ``cluster_person_assignments`` 因 FK CASCADE 被删，
投影行的 ``assignment_id`` 随之置 NULL。这类行同时 ``person_id IS NULL``（ADR-052
的 SET NULL），不参与任何身份判断，也不进入归档计划。

存量行一律不回填：迁移前不存在任何 Assignment 支撑信息，回填等于猜测身份。历史
``approved`` 行保持 ``assignment_id IS NULL``，按 legacy 语义继续有效。
"""

revision = "009_projection_ownership"
down_revision = "008_archive_identity_and_confidence"
description = "recognition_results.assignment_id — S1 Assignment 支撑的投影归属"

from alembic import op  # noqa: E402  # Alembic migration template convention
import sqlalchemy as sa  # noqa: E402  # Alembic migration template convention


def _column_names(table: str) -> set[str]:
    """Return the existing column names of ``table`` via the live connection."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the supporting-assignment reference plus the three lookup indexes."""
    if "assignment_id" not in _column_names("recognition_results"):
        # SQLite permits ADD COLUMN with REFERENCES only because the new column
        # defaults to NULL (same pattern as migration 008's archive_records.person_id).
        op.execute(
            "ALTER TABLE recognition_results ADD COLUMN assignment_id TEXT "
            "REFERENCES cluster_person_assignments(id) ON DELETE SET NULL"
        )

    # find_projection(photo_id, person_id) WHERE assignment_id IS NOT NULL —
    # the reconcile/rebuild hot path; the partial predicate also keeps legacy
    # rows out of the index entirely.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_rr_photo_person_projection "
        "ON recognition_results(photo_id, person_id) WHERE assignment_id IS NOT NULL"
    )
    # Retarget lookups and orphan detection by owning assignment.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_rr_assignment_id "
        "ON recognition_results(assignment_id)"
    )
    # S0 INV-1: latest decision per cluster. The existing
    # idx_cluster_person_assignments_cluster_id only covers cluster_id, so the
    # ORDER BY created_at DESC, id DESC would need a sort.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cpa_cluster_latest "
        "ON cluster_person_assignments(cluster_id, created_at DESC, id DESC)"
    )


def downgrade() -> None:
    """Drop the indexes first, then the column (SQLite refuses to drop an
    indexed column)."""
    op.execute("DROP INDEX IF EXISTS idx_cpa_cluster_latest")
    op.execute("DROP INDEX IF EXISTS idx_rr_assignment_id")
    op.execute("DROP INDEX IF EXISTS idx_rr_photo_person_projection")
    if "assignment_id" in _column_names("recognition_results"):
        op.execute("ALTER TABLE recognition_results DROP COLUMN assignment_id")