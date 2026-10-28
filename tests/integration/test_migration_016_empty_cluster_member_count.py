"""Migration 016 — face_clusters.member_count CHECK 放宽到 >= 0 的迁移完整性测试.

在隔离临时数据库中证明（不触碰生产库）：

- upgrade（015 → 016 表重建）逐行零丢失、零字段改写；
- ``member_count = 0``（空簇，照片删除后的合法状态）可通过 CHECK；
- 两个命名索引按 006 定义重建；
- downgrade 是应急路径：存在 0 成员行时按旧 CHECK 重建会失败；
  清除 0 行后可降级（数据保全）。
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

_ALEMBIC_CFG = Path(__file__).resolve().parents[2] / "alembic.ini"
_PRE_REVISION = "015_run_photo_outcome"

_UUID_RUN = "88888888-8888-8888-8888-888888888888"
_UUID_CLUSTER_RUN = "99999999-9999-9999-9999-999999999999"
_UUID_CLUSTER = "aaaaaa01-0000-0000-0000-000000000001"
_UUID_CLUSTER_2 = "aaaaaa02-0000-0000-0000-000000000002"


def _alembic_cfg(db: Path) -> Config:
    cfg = Config(str(_ALEMBIC_CFG))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    cfg.set_main_option("script_location", str(_ALEMBIC_CFG.resolve().parent / "alembic"))
    return cfg


def _seed(db: Path) -> None:
    """Seed one recognition run + cluster run + two 1-member clusters."""
    conn = sqlite3.connect(db)
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO recognition_runs (id, status, parameters, created_at)"
        " VALUES (?, 'completed', '{}', ?)",
        (_UUID_RUN, now),
    )
    conn.execute(
        "INSERT INTO face_cluster_runs (id, recognition_run_id, status,"
        " algorithm_version, parameters, cluster_count, member_count,"
        " excluded_count, created_at)"
        " VALUES (?, ?, 'completed', 'v1', '{}', 2, 2, 0, ?)",
        (_UUID_CLUSTER_RUN, _UUID_RUN, now),
    )
    for cluster_id, member_count in (
        (_UUID_CLUSTER, 1),
        (_UUID_CLUSTER_2, 1),
    ):
        conn.execute(
            "INSERT INTO face_clusters (id, cluster_run_id, run_id, ordinal,"
            " member_count, sort_key, status, created_at)"
            " VALUES (?, ?, ?, 0, ?, 'k|g0|seed', 'pending', ?)",
            (cluster_id, _UUID_CLUSTER_RUN, _UUID_RUN, member_count, now),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def pre_db(tmp_path: Path) -> Path:
    """Build a 015-revision database with a representative cluster pair."""
    db = tmp_path / "pre016.sqlite3"
    command.upgrade(_alembic_cfg(db), _PRE_REVISION)
    _seed(db)
    return db


def _rows(db: Path) -> list[tuple]:
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT id, cluster_run_id, run_id, ordinal, member_count, sort_key,"
        " status, created_at FROM face_clusters ORDER BY id"
    ).fetchall()
    conn.close()
    return rows


def _rows_by_id(db: Path) -> dict[str, tuple]:
    return {row[0]: row for row in _rows(db)}


def test_upgrade_preserves_rows_and_allows_zero_members(pre_db: Path) -> None:
    """重建逐行保全；0 成员簇可写（旧 CHECK 会拒绝）。"""
    before = _rows(pre_db)
    command.upgrade(_alembic_cfg(pre_db), "head")
    assert _rows(pre_db) == before

    conn = sqlite3.connect(pre_db)
    conn.execute(
        "UPDATE face_clusters SET member_count = 0 WHERE id = ?", (_UUID_CLUSTER,),
    )
    conn.commit()
    conn.close()
    assert _rows_by_id(pre_db)[_UUID_CLUSTER][4] == 0

    # 命名索引按 006 定义重建
    conn = sqlite3.connect(pre_db)
    names = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='face_clusters'"
        ).fetchall()
    }
    conn.close()
    assert "idx_face_clusters_cluster_run_id" in names
    assert "idx_face_clusters_run_id" in names


def test_downgrade_requires_no_zero_member_rows(pre_db: Path, tmp_path: Path) -> None:
    """0 成员行存在时降级失败；干净库降级成功且数据保全。

    SQLite DDL 非事务性——CHECK 失败会留下半迁移状态（``__016_old`` 持有
    原数据），需手工恢复（与 013 同性质）。因此"失败"与"成功"两条路径用
    两个独立库验证。
    """
    command.upgrade(_alembic_cfg(pre_db), "head")

    conn = sqlite3.connect(pre_db)
    conn.execute(
        "UPDATE face_clusters SET member_count = 0 WHERE id = ?", (_UUID_CLUSTER,),
    )
    conn.commit()
    conn.close()
    with pytest.raises(Exception, match="CHECK constraint failed"):
        command.downgrade(_alembic_cfg(pre_db), _PRE_REVISION)

    # 干净库：无 0 成员行 → 降级成功，数据保全。
    clean_db = tmp_path / "clean016.sqlite3"
    command.upgrade(_alembic_cfg(clean_db), _PRE_REVISION)
    _seed(clean_db)
    command.upgrade(_alembic_cfg(clean_db), "head")
    command.downgrade(_alembic_cfg(clean_db), _PRE_REVISION)
    after = _rows_by_id(clean_db)
    assert after[_UUID_CLUSTER][4] == 1
    assert after[_UUID_CLUSTER_2][4] == 1
