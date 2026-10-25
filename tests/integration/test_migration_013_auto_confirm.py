"""S4 Migration 013 — cluster_person_assignments 词表扩展的迁移完整性测试.

在隔离临时数据库中证明（C-1C.C，不触碰生产库）：

- upgrade（010 → 013 表重建）逐行零丢失、零字段改写；
- 新词表 ``auto_confirmed`` / ``ordered_auto_confirm`` 可通过 CHECK，
  词表外值仍被数据库拒绝；
- ``recognition_results.assignment_id`` 外键在表重建后仍指向重建表且
  ON DELETE SET NULL 行为不变（010 记录过的 RENAME 外键改写陷阱的回归防线）；
- 三个命名索引在 upgrade / downgrade 后均按 007/009 定义重建；
- downgrade 按 owner 批准的**有损**映射执行（auto_confirmed → suggested、
  ordered_auto_confirm → ordered_suggestion），并显式断言该映射丢失
  自动确认的区分——不声称可无损恢复。
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

_ALEMBIC_CFG = Path(__file__).resolve().parents[2] / "alembic.ini"
_PRE_REVISION = "012_single_expert_ground_truth"
# 界面优化新增 014/015 迁移后迁移头前移；本套件断言的是"升级到当前头
# 且数据保全"，不是冻结版本号。
_HEAD_REVISION = "015_run_photo_outcome"

_UUID_PERSON = "11111111-1111-1111-1111-111111111111"
_UUID_FOLDER = "77777777-7777-7777-7777-777777777777"
_UUID_PHOTO = "44444444-4444-4444-4444-444444444444"
_UUID_RUN = "88888888-8888-8888-8888-888888888888"
_UUID_CLUSTER_RUN = "99999999-9999-9999-9999-999999999999"
_UUID_CLUSTER = "aaaaaaa1-0000-0000-0000-000000000001"
_UUID_CLUSTER_2 = "aaaaaaa2-0000-0000-0000-000000000002"
_UUID_PROJECTION = "55555555-5555-5555-5555-555555555555"

# 既有词表全覆盖 + 证据变体：4 状态 × 代表来源、score 三态、error 非空。
_SEED_ASSIGNMENTS = [
    # (id, cluster_id, person_id, status, source, score, error)
    ("bbbbbbb1-0000-0000-0000-000000000001", _UUID_CLUSTER, _UUID_PERSON,
     "suggested", "ordered_suggestion", None, None),
    ("bbbbbbb2-0000-0000-0000-000000000002", _UUID_CLUSTER, _UUID_PERSON,
     "suggested", "sample_match", 0.42, None),
    ("bbbbbbb3-0000-0000-0000-000000000003", _UUID_CLUSTER, _UUID_PERSON,
     "confirmed", "manual", None, None),
    ("bbbbbbb4-0000-0000-0000-000000000004", _UUID_CLUSTER_2, _UUID_PERSON,
     "confirmed", "review", None, "seed-note"),
    ("bbbbbbb5-0000-0000-0000-000000000005", _UUID_CLUSTER_2, _UUID_PERSON,
     "rejected", "sample_match", -0.31, None),
    ("bbbbbbb6-0000-0000-0000-000000000006", _UUID_CLUSTER_2, None,
     "unassigned", "ordered_suggestion", None, None),
]


def _alembic_cfg(db: Path) -> Config:
    cfg = Config(str(_ALEMBIC_CFG))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    cfg.set_main_option("script_location", str(_ALEMBIC_CFG.resolve().parent / "alembic"))
    return cfg


@pytest.fixture
def pre_db(tmp_path: Path) -> Path:
    """Build a 012-revision database with representative assignment data."""
    db = tmp_path / "pre013.sqlite3"
    command.upgrade(_alembic_cfg(db), _PRE_REVISION)

    conn = sqlite3.connect(db)
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO people (id, name, created_at) VALUES (?, ?, ?)",
        (_UUID_PERSON, "种子人员", now),
    )
    conn.execute(
        "INSERT INTO folders (id, raw_path, path_base, display_name,"
        " total_photos, scanned_photos, created_at)"
        " VALUES (?, ?, 'absolute', ?, 0, 0, ?)",
        (_UUID_FOLDER, str(tmp_path), "seed-folder", now),
    )
    conn.execute(
        "INSERT INTO photos (id, raw_path, path_base, folder_id, original_name,"
        " created_at) VALUES (?, ?, 'absolute', ?, ?, ?)",
        (_UUID_PHOTO, str(tmp_path / "photo.jpg"), _UUID_FOLDER, "photo.jpg", now),
    )
    conn.execute(
        "INSERT INTO recognition_runs (id, status, created_at) VALUES (?, 'completed', ?)",
        (_UUID_RUN, now),
    )
    conn.execute(
        "INSERT INTO face_cluster_runs (id, recognition_run_id, status,"
        " algorithm_version, created_at) VALUES (?, ?, 'completed', 'test-v1', ?)",
        (_UUID_CLUSTER_RUN, _UUID_RUN, now),
    )
    for cluster_id in (_UUID_CLUSTER, _UUID_CLUSTER_2):
        conn.execute(
            "INSERT INTO face_clusters (id, cluster_run_id, run_id, ordinal,"
            " member_count, sort_key, status, created_at)"
            " VALUES (?, ?, ?, 0, 1, 'k|p|000000', 'pending', ?)",
            (cluster_id, _UUID_CLUSTER_RUN, _UUID_RUN, now),
        )
    for row in _SEED_ASSIGNMENTS:
        assignment_id, cluster_id, person_id, status, source, score, error = row
        conn.execute(
            "INSERT INTO cluster_person_assignments (id, cluster_id, person_id,"
            " status, source, score, sort_snapshot, error, created_at, confirmed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (assignment_id, cluster_id, person_id, status, source, score,
             json.dumps({"sort_key": "k"}, ensure_ascii=False), error, now,
             now if status == "confirmed" else None),
        )
    # 009 外键的现存消费者：approved 投影行指向 confirmed 指派（bbbbbbb3）。
    conn.execute(
        "INSERT INTO recognition_results (id, photo_id, person_id, status,"
        " confidence, created_at, assignment_id)"
        " VALUES (?, ?, ?, 'approved', NULL, ?, ?)",
        (_UUID_PROJECTION, _UUID_PHOTO, _UUID_PERSON, now,
         "bbbbbbb3-0000-0000-0000-000000000003"),
    )
    conn.commit()
    conn.close()
    return db


def _rows(db: Path) -> list[dict]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute(
        "SELECT * FROM cluster_person_assignments ORDER BY id").fetchall()]
    conn.close()
    return rows


def _alembic_version(db: Path) -> str:
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    conn.close()
    return row[0]


def _table_indexes(db: Path) -> set[str]:
    conn = sqlite3.connect(db)
    names = {
        row[1] for row in conn.execute(
            'PRAGMA index_list("cluster_person_assignments")').fetchall()
    }
    conn.close()
    return names


_EXPECTED_INDEXES = {
    "idx_cluster_person_assignments_cluster_id",
    "idx_cluster_person_assignments_person_id",
    "idx_cpa_cluster_latest",
}


def test_upgrade_preserves_every_assignment_row(pre_db: Path) -> None:
    before = _rows(pre_db)
    assert len(before) == len(_SEED_ASSIGNMENTS)
    assert _alembic_version(pre_db) == _PRE_REVISION

    command.upgrade(_alembic_cfg(pre_db), "head")

    assert _alembic_version(pre_db) == _HEAD_REVISION
    after = _rows(pre_db)
    # 逐行逐列零丢失、零改写（表重建的唯一合法变化是 CHECK 词表）。
    assert after == before
    conn = sqlite3.connect(pre_db)
    assert [list(r) for r in conn.execute("PRAGMA foreign_key_check").fetchall()] == []
    conn.close()


def test_new_vocabulary_accepted_and_out_of_vocabulary_rejected(pre_db: Path) -> None:
    command.upgrade(_alembic_cfg(pre_db), "head")
    now = datetime.now().isoformat()
    conn = sqlite3.connect(pre_db)

    conn.execute(
        "INSERT INTO cluster_person_assignments (id, cluster_id, person_id,"
        " status, source, score, sort_snapshot, created_at)"
        " VALUES ('bbbbbbb9-0000-0000-0000-000000000009', ?, ?,"
        " 'auto_confirmed', 'ordered_auto_confirm', NULL, '{}', ?)",
        (_UUID_CLUSTER, _UUID_PERSON, now),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO cluster_person_assignments (id, cluster_id, person_id,"
            " status, source, sort_snapshot, created_at)"
            " VALUES ('bbbbbbba-0000-0000-0000-00000000000a', ?, ?,"
            " 'bogus', 'ordered_suggestion', '{}', ?)",
            (_UUID_CLUSTER, _UUID_PERSON, now),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO cluster_person_assignments (id, cluster_id, person_id,"
            " status, source, sort_snapshot, created_at)"
            " VALUES ('bbbbbbbb-0000-0000-0000-00000000000b', ?, ?,"
            " 'suggested', 'positional', '{}', ?)",
            (_UUID_CLUSTER, _UUID_PERSON, now),
        )
    conn.close()


def test_projection_fk_survives_table_rebuild(pre_db: Path) -> None:
    """009 外键在 rename/copy/drop 重建后必须指向重建表且行为不变。"""
    command.upgrade(_alembic_cfg(pre_db), "head")
    conn = sqlite3.connect(pre_db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    row = dict(conn.execute(
        "SELECT assignment_id, status FROM recognition_results WHERE id = ?",
        (_UUID_PROJECTION,),
    ).fetchone())
    assert row["assignment_id"] == "bbbbbbb3-0000-0000-0000-000000000003"

    # ON DELETE SET NULL：删除被引用指派 → 投影行 assignment_id 置 NULL。
    conn.execute(
        "DELETE FROM cluster_person_assignments WHERE id = ?",
        ("bbbbbbb3-0000-0000-0000-000000000003",),
    )
    conn.commit()
    row = dict(conn.execute(
        "SELECT assignment_id FROM recognition_results WHERE id = ?",
        (_UUID_PROJECTION,),
    ).fetchone())
    assert row["assignment_id"] is None
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_assignment_fk_cascade_intact(pre_db: Path) -> None:
    """007 外键（cluster/person CASCADE）在重建后行为不变。"""
    command.upgrade(_alembic_cfg(pre_db), "head")
    conn = sqlite3.connect(pre_db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM face_clusters WHERE id = ?", (_UUID_CLUSTER,))
    conn.commit()
    remaining = conn.execute(
        "SELECT COUNT(*) FROM cluster_person_assignments WHERE cluster_id = ?",
        (_UUID_CLUSTER,),
    ).fetchone()[0]
    conn.close()
    assert remaining == 0


def test_indexes_rebuilt_after_upgrade(pre_db: Path) -> None:
    command.upgrade(_alembic_cfg(pre_db), "head")
    assert _EXPECTED_INDEXES <= _table_indexes(pre_db)


def test_downgrade_applies_approved_lossy_mapping(pre_db: Path) -> None:
    command.upgrade(_alembic_cfg(pre_db), "head")
    conn = sqlite3.connect(pre_db)
    now = datetime.now().isoformat()
    # 升级后写入两条 auto 行（一条保持 auto_confirmed，一条人工拒绝后终态）。
    conn.execute(
        "INSERT INTO cluster_person_assignments (id, cluster_id, person_id,"
        " status, source, score, sort_snapshot, created_at)"
        " VALUES ('bbbbbbbc-0000-0000-0000-00000000000c', ?, ?,"
        " 'auto_confirmed', 'ordered_auto_confirm', NULL, '{}', ?)",
        (_UUID_CLUSTER, _UUID_PERSON, now),
    )
    conn.execute(
        "INSERT INTO cluster_person_assignments (id, cluster_id, person_id,"
        " status, source, score, sort_snapshot, created_at)"
        " VALUES ('bbbbbbbd-0000-0000-0000-00000000000d', ?, ?,"
        " 'rejected', 'ordered_auto_confirm', NULL, '{}', ?)",
        (_UUID_CLUSTER_2, _UUID_PERSON, now),
    )
    conn.commit()
    conn.close()

    command.downgrade(_alembic_cfg(pre_db), _PRE_REVISION)

    assert _alembic_version(pre_db) == _PRE_REVISION
    rows = {row["id"]: row for row in _rows(pre_db)}
    # 有损映射（owner 批准）：状态与专用来源都被改写——**这是断言丢失本身**。
    auto_row = rows["bbbbbbbc-0000-0000-0000-00000000000c"]
    assert (auto_row["status"], auto_row["source"]) == ("suggested", "ordered_suggestion")
    rejected_auto = rows["bbbbbbbd-0000-0000-0000-00000000000d"]
    # rejected 状态保留；source 仍按批准映射改写——自动来源区分不可恢复。
    assert (rejected_auto["status"], rejected_auto["source"]) == (
        "rejected", "ordered_suggestion")
    # 其余旧词表行原值保留。
    assert (rows["bbbbbbb3-0000-0000-0000-000000000003"]["status"],
            rows["bbbbbbb3-0000-0000-0000-000000000003"]["source"]) == (
        "confirmed", "manual")
    assert _EXPECTED_INDEXES <= _table_indexes(pre_db)
    conn = sqlite3.connect(pre_db)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_downgrade_rejects_new_vocabulary(pre_db: Path) -> None:
    """降级后旧 CHECK 生效：新词表值不再可写。"""
    command.upgrade(_alembic_cfg(pre_db), "head")
    command.downgrade(_alembic_cfg(pre_db), _PRE_REVISION)
    conn = sqlite3.connect(pre_db)
    now = datetime.now().isoformat()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO cluster_person_assignments (id, cluster_id, person_id,"
            " status, source, sort_snapshot, created_at)"
            " VALUES ('bbbbbbbe-0000-0000-0000-00000000000e', ?, ?,"
            " 'auto_confirmed', 'ordered_auto_confirm', '{}', ?)",
            (_UUID_CLUSTER, _UUID_PERSON, now),
        )
    conn.close()


def test_upgrade_after_downgrade_roundtrips(pre_db: Path) -> None:
    """upgrade → downgrade → upgrade：降级映射后的行再次升级时零丢失。"""
    command.upgrade(_alembic_cfg(pre_db), "head")
    command.downgrade(_alembic_cfg(pre_db), _PRE_REVISION)
    after_down = _rows(pre_db)
    command.upgrade(_alembic_cfg(pre_db), "head")
    assert _rows(pre_db) == after_down
    assert _alembic_version(pre_db) == _HEAD_REVISION
