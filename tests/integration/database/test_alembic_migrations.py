"""Alembic migration integration tests（阶段 2，ADR-027）.

覆盖 ADR-027 §5 测试矩阵：
- migration up 可执行（6 基础表 + 阶段 A 2 表 + 全部显式索引创建）
- migration down 可执行（表 DROP，FK 依赖逆序）
- migration 重复执行幂等（IF NOT EXISTS / IF EXISTS 守护）
- alembic upgrade head 成功 + Schema 版本一致（alembic_version 表记录 003）
- Repository CRUD 对照回归不退化（migration 接管 DDL 后 CRUD 路径不变）

用临时 SQLite 库——每测试独立库，避污染。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

# alembic.ini 路径——与 alembic_runner.py 同锚点（5×parent: tests/integration → tests → project root）
_ALEMBIC_CFG = Path(__file__).resolve().parent.parent.parent.parent / "alembic.ini"
_ALEMBIC_SCRIPT = _ALEMBIC_CFG.resolve().parent / "alembic"

# 8 基础表（002 的 6 基础表 + 003 的导入草稿 2 表）+ 004 的 4 张 run 表
_ALL_TABLES = (
    "people",
    "folders",
    "photos",
    "recognition_results",
    "person_embeddings",
    "archive_records",
    "import_batches",
    "import_draft_rows",
    "recognition_runs",
    "recognition_run_photos",
    "recognition_run_scopes",
    "face_observations",
    "face_cluster_runs",
    "face_clusters",
    "face_cluster_members",
    "cluster_person_assignments",
    "person_face_embeddings",
    # S4-B-1：Ground Truth 标注体系（与业务链严格分离）
    "calibration_annotations",
    "calibration_ground_truth",
    "calibration_datasets",
)
# 显式命名索引（002 的 5 个 + 003 的 2 个；SQLite UNIQUE 自动索引不计入）
_ALL_INDEXES = (
    "idx_photos_folder_id",
    "idx_recognition_results_photo_id",
    "idx_recognition_results_person_id",
    "idx_archive_records_photo_id",
    "idx_archive_records_status",
    "idx_import_draft_rows_batch",
    "idx_people_roster_order",
    "idx_recognition_runs_created_at",
    "idx_recognition_run_photos_photo_id",
    "idx_face_observations_photo_id",
    "idx_face_observations_run_id",
    "idx_face_cluster_runs_recognition_run_id",
    "idx_face_clusters_cluster_run_id",
    "idx_face_clusters_run_id",
    "idx_face_cluster_members_cluster_id",
    "idx_face_cluster_members_observation_id",
    "idx_cluster_person_assignments_cluster_id",
    "idx_cluster_person_assignments_person_id",
    "idx_person_face_embeddings_person_id",
    "idx_person_face_embeddings_observation_id",
    "idx_archive_records_person_id",
    # S1 / migration 009：投影归属 + Assignment 最新决策查询。
    "idx_rr_photo_person_projection",
    "idx_rr_assignment_id",
    "idx_cpa_cluster_latest",
    # S4-B-1
    "idx_calib_ann_cluster",
    "idx_calib_ann_annotator",
    "idx_calib_gt_cluster",
    "idx_calib_gt_dataset",
    # calibration_datasets 的唯一性由复合主键 (id, version) 隐含，
    # 011 不再额外建 idx_calib_dataset_version。
)

# Stage 4：008 之后 alembic head（BLK-1 / BLK-5 schema 变更）。
_HEAD = "012_single_expert_ground_truth"


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Return a temp SQLite database file path (tmp_path is a dir, append filename)."""
    return tmp_path / "test.db"


def _make_alembic_config(tmp_db: Path) -> Config:
    """Build an Alembic Config wired to the temp SQLite database."""
    cfg = Config(str(_ALEMBIC_CFG))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_db.as_posix()}")
    cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT))
    return cfg


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    """Return user tables (exclude sqlite_* / alembic_version)."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [r[0] for r in rows]


def _list_indexes(conn: sqlite3.Connection) -> list[str]:
    """Return all index names (incl sqlite_autoindex_*)."""
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    return [r[0] for r in rows]


def _alembic_version(conn: sqlite3.Connection) -> str | None:
    """Return the current revision from alembic_version table, None if absent."""
    tables = _list_tables(conn)
    if "alembic_version" not in tables:
        return None
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return row[0] if row else None


# ── migration up 可执行 ────────────────────────────────────────────────────


def test_migration_upgrade_creates_all_tables(tmp_db: Path) -> None:
    """upgrade head 创建全部 8 表（002 的 6 基础表 + 003 的导入草稿 2 表）."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        tables = _list_tables(conn)
        for table in _ALL_TABLES:
            assert table in tables, f"Migration upgrade should create table '{table}', got: {tables}"
        assert "alembic_version" in tables, "alembic_version table should exist after upgrade"


def test_migration_upgrade_creates_all_indexes(tmp_db: Path) -> None:
    """upgrade head 创建全部显式索引（002 的 5 个 + 003 的 2 个）."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        indexes = _list_indexes(conn)
        for idx in _ALL_INDEXES:
            assert idx in indexes, f"Migration upgrade should create index '{idx}', got: {indexes}"


def test_migration_upgrade_stamps_head_revision(tmp_db: Path) -> None:
    """upgrade head 后 alembic_version 表记录 008。"""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        assert _alembic_version(conn) == _HEAD


# ── migration down 可执行 ──────────────────────────────────────────────────


def test_migration_downgrade_drops_all_six_tables(tmp_db: Path) -> None:
    """002 downgrade DROP 全部 6 表（FK 依赖逆序），回退到 001 空 stamp 状态."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "001_initial_v4")  # 回退到 001（002 down 执行）

    with sqlite3.connect(str(tmp_db)) as conn:
        tables = _list_tables(conn)
        for table in _ALL_TABLES:
            assert table not in tables, (
                f"Migration downgrade should DROP table '{table}', got: {tables}"
            )
        # 001 是空 stamp——downgrade 到 001 后 alembic_version 应记录 001
        assert _alembic_version(conn) == "001_initial_v4"


def test_migration_downgrade_idempotent(tmp_db: Path) -> None:
    """downgrade 幂等守护——DROP TABLE IF EXISTS 容重复执行不报错."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "001_initial_v4")

    # 重复 downgrade 不应报错（即使表已 DROP）
    # 注：alembic downgrade 到 base 会再 down 001，但 001 downgrade 是 no-op pass
    command.downgrade(cfg, "base")  # base = 001 down → 无前版本，001 downgrade pass


# ── migration 幂等守护 ─────────────────────────────────────────────────────


def test_migration_upgrade_idempotent(tmp_db: Path) -> None:
    """upgrade 幂等守护——CREATE TABLE IF NOT EXISTS 容重复执行不报错."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")
    # 第二次 upgrade—— alembic 检测已在 head 不再执行 003，但 stamp 不报错
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        assert _alembic_version(conn) == _HEAD
        # 表仍存在不重复创建
        tables = _list_tables(conn)
        # 按 _ALL_TABLES 断言而非硬编码数量：每次新增迁移都会让硬编码失效，
        # 而这里要验证的是"幂等 upgrade 不改变表集合"，不是表的数量。
        assert set(_ALL_TABLES) <= set(tables)
        assert "alembic_version" in tables


# ── Schema 版本一致 ─────────────────────────────────────────────────────────


def test_schema_version_consistent_after_upgrade(tmp_db: Path) -> None:
    """upgrade head 后 Schema 版本一致——alembic_version=head + 全部表与索引。"""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        assert _alembic_version(conn) == _HEAD
        tables = _list_tables(conn)
        assert set(_ALL_TABLES).issubset(set(tables))
        indexes = _list_indexes(conn)
        assert set(_ALL_INDEXES).issubset(set(indexes))


# ── Repository CRUD 对照回归 ────────────────────────────────────────────────


def test_repository_crud_works_after_migration(tmp_db: Path) -> None:
    """Repository CRUD 对照回归——migration 接管 DDL 后 CRUD 路径不退化.

    用 SQLitePhotoRepository 验：save photo → get → list → 全路径不报错。
    """
    from photo_archiver.domain import Photo, PhotoPath
    from photo_archiver.domain.repositories import PhotoRepository
    from photo_archiver.infrastructure import SQLiteConnectionProvider, SQLitePhotoRepository

    # 走 initialize_schema() 路径——ADR-027 后此方法调 Alembic 触发 migration
    provider = SQLiteConnectionProvider(tmp_db)
    provider.initialize_schema()

    repo: PhotoRepository = SQLitePhotoRepository(provider)  # type: ignore[arg-type, assignment]
    # add photo（SQLitePhotoRepository API 是 add 非 save）
    photo = Photo(path=PhotoPath("tmp/test.jpg"), id=None)
    repo.add(photo)

    # list photos（验 add 真落库）
    photos = repo.list_all()
    assert len(photos) == 1, f"list_all should return 1 photo after add, got {len(photos)}"
    saved_id = photos[0].id
    assert saved_id is not None, "add should assign id"

    # find_by_id（SQLitePhotoRepository API 是 find_by_id 非 get_by_id）
    fetched = repo.find_by_id(saved_id)  # type: ignore[arg-type]
    assert fetched is not None, "find_by_id should return saved photo"
    assert fetched.id == saved_id


def test_initialize_schema_uses_alembic_not_raw_sql(tmp_db: Path) -> None:
    """initialize_schema() 不再持 CREATE TABLE raw SQL——仅留 mkdir + PRAGMA stamp + 调 Alembic.

    ADR-027 裁决点 1=A 守护：DDL 全迁 migration，initialize_schema() 移除重复路径。
    """
    from photo_archiver.infrastructure import SQLiteConnectionProvider

    provider = SQLiteConnectionProvider(tmp_db)
    # initialize_schema() 应通过 Alembic migration 创建表——不持 raw SQL DDL
    # 验：调用后表存在（migration 执行了），且 alembic_version 表记录 head
    provider.initialize_schema()

    with sqlite3.connect(str(tmp_db)) as conn:
        tables = _list_tables(conn)
        assert "alembic_version" in tables, (
            "initialize_schema() should trigger Alembic migration (alembic_version table exists)"
        )
        assert _alembic_version(conn) == _HEAD
        # 全部业务表全在（migration 真接管 DDL）
        for table in _ALL_TABLES:
            assert table in tables, f"initialize_schema() via Alembic should create table '{table}'"


# ── 008：BLK-1 身份列 / BLK-5 可空 confidence ────────────────────────────────


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_008_adds_archive_person_id_and_nullable_confidence(tmp_db: Path) -> None:
    """008 为 archive_records 增稳定身份列，并放宽 recognition_results.confidence。"""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        assert "person_id" in _columns(conn, "archive_records")
        assert "person_id" in _columns(conn, "recognition_results")
        # confidence 必须可空（NOT NULL 会拒绝"无相似度证据"行）。
        notnull = {
            row[1]: row[3] for row in conn.execute("PRAGMA table_info(recognition_results)")
        }
        assert notnull["confidence"] == 0
        assert "idx_archive_records_person_id" in _list_indexes(conn)


def test_008_backfills_archive_person_id_by_unique_name(tmp_db: Path) -> None:
    """008 升级存量数据：姓名唯一命中时回填 person_id；重名保持 NULL。

    重名回填会把 A 的归档记到 B 头上，故必须留空并回退姓名匹配。
    """
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "007_assignments_and_person_samples")

    now = datetime.now().isoformat()
    unique_id, duplicated_name = str(uuid4()), "同名人员"
    with sqlite3.connect(str(tmp_db)) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO people (id, name, created_at) VALUES (?,?,?)",
                     (unique_id, "唯一人员", now))
        conn.execute("INSERT INTO people (id, name, created_at) VALUES (?,?,?)",
                     (str(uuid4()), duplicated_name, now))
        conn.execute("INSERT INTO people (id, name, created_at) VALUES (?,?,?)",
                     (str(uuid4()), duplicated_name, now))
        photo_unique, photo_dup = str(uuid4()), str(uuid4())
        for pid in (photo_unique, photo_dup):
            conn.execute(
                "INSERT INTO photos (id, raw_path, path_base, original_name, created_at)"
                " VALUES (?,?,'absolute','x.jpg',?)",
                (pid, f"/tmp/{pid}.jpg", now),
            )
        for pid, name in ((photo_unique, "唯一人员"), (photo_dup, duplicated_name)):
            conn.execute(
                "INSERT INTO archive_records (id, photo_id, target_archive_root,"
                " target_person_name, target_event_or_date, target_original_name,"
                " status, archived_at) VALUES (?,?,?,?,?,?,'archived',?)",
                (str(uuid4()), pid, "/a", name, "2024-05-01", "x.jpg", now),
            )
        conn.commit()

    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        rows = dict(conn.execute(
            "SELECT photo_id, person_id FROM archive_records",
        ).fetchall())
        assert rows[photo_unique] == unique_id, "唯一姓名应回填身份"
        assert rows[photo_dup] is None, "重名行必须留空（不猜身份）"


# ── S1 / migration 009：projection ownership ────────────────────────────────


def _schema_snapshot(conn: sqlite3.Connection) -> tuple:
    """Full schema fingerprint: SQL text, columns, FKs, indexes, integrity."""
    tables = sorted(
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name NOT LIKE 'sqlite_%'"
        )
    )
    objects = sorted(
        (r[0], r[1], (r[2] or "").strip())
        for r in conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL"
        )
    )
    columns = {
        table: [
            (r[1], r[2], r[3], r[5])
            for r in conn.execute(f'PRAGMA table_info("{table}")')
        ]
        for table in tables
    }
    foreign_keys = {
        table: [tuple(r) for r in conn.execute(f'PRAGMA foreign_key_list("{table}")')]
        for table in tables
    }
    indexes = sorted(
        (r[0], r[1], r[2])
        for r in conn.execute(
            "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index'"
        )
    )
    return (objects, columns, foreign_keys, indexes,
            conn.execute("PRAGMA integrity_check").fetchone()[0],
            conn.execute("PRAGMA foreign_key_check").fetchall())


def test_009_adds_assignment_id_and_support_indexes(tmp_db: Path) -> None:
    """009 为recognition_results 增assignment_id，并建三条查询索引。"""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(recognition_results)")}
        assert "assignment_id" in columns
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )}
        assert {"idx_rr_photo_person_projection", "idx_rr_assignment_id",
                "idx_cpa_cluster_latest"} <= indexes
        fks = {r[2] for r in conn.execute("PRAGMA foreign_key_list(recognition_results)")}
        assert "cluster_person_assignments" in fks


def test_009_leaves_existing_rows_unowned(tmp_db: Path) -> None:
    """009 不回填历史 approved 行——迁移前没有支撑信息，回填等于猜身份。"""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "008_archive_identity_and_confidence")
    now = "2026-01-01 00:00:00"
    with sqlite3.connect(str(tmp_db)) as conn:
        conn.execute("INSERT INTO people (id,name,created_at) VALUES (?,?,?)",
                     (str(uuid4()), "张三", now))
        conn.execute(
            "INSERT INTO photos (id, raw_path, path_base, original_name, created_at)"
            " VALUES (?,?,'absolute','x.jpg',?)", (str(uuid4()), "/tmp/x.jpg", now))
        photo_id = conn.execute("SELECT id FROM photos").fetchone()[0]
        conn.execute(
            "INSERT INTO recognition_results (id, photo_id, status, confidence, created_at)"
            " VALUES (?,?, 'approved', NULL, ?)", (str(uuid4()), photo_id, now))
        conn.commit()

    command.upgrade(cfg, "head")
    with sqlite3.connect(str(tmp_db)) as conn:
        rows = conn.execute(
            "SELECT assignment_id FROM recognition_results WHERE status='approved'"
        ).fetchall()
        assert rows and all(row[0] is None for row in rows), "存量 approved 必须保持无主（legacy）"


def test_009_upgrade_downgrade_upgrade_round_trip(tmp_db: Path) -> None:
    """upgrade → downgrade → upgrade 往返：schema 与关键数据完全一致。"""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "009_projection_ownership")

    now = "2026-01-01 00:00:00"
    with sqlite3.connect(str(tmp_db)) as conn:
        conn.execute("INSERT INTO people (id,name,created_at) VALUES (?,?,?)",
                     (str(uuid4()), "张三", now))
        conn.execute(
            "INSERT INTO photos (id, raw_path, path_base, original_name, created_at)"
            " VALUES (?,?,'absolute','x.jpg',?)", (str(uuid4()), "/tmp/x.jpg", now))
        photo_id = conn.execute("SELECT id FROM photos").fetchone()[0]
        conn.execute(
            "INSERT INTO recognition_results"
            " (id, photo_id, person_id, status, confidence, created_at, assignment_id)"
            " VALUES (?,?,?, 'rejected', NULL, ?, NULL)",
            (str(uuid4()), photo_id, None, now))
        conn.commit()

    def data_fingerprint() -> tuple:
        with sqlite3.connect(str(tmp_db)) as conn:
            return (
                sorted(conn.execute(
                    "SELECT id, photo_id, person_id, status, confidence, created_at"
                    " FROM recognition_results"
                ).fetchall()),
                sorted(conn.execute("SELECT id, name FROM people").fetchall()),
            )

    with sqlite3.connect(str(tmp_db)) as conn:
        upgraded_schema = _schema_snapshot(conn)
    upgraded_data = data_fingerprint()

    command.downgrade(cfg, "008_archive_identity_and_confidence")
    with sqlite3.connect(str(tmp_db)) as conn:
        downgraded_schema = _schema_snapshot(conn)
        columns = {r[1] for r in conn.execute("PRAGMA table_info(recognition_results)")}
        assert "assignment_id" not in columns
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        assert "idx_rr_assignment_id" not in indexes
    downgraded_data = data_fingerprint()

    command.upgrade(cfg, "009_projection_ownership")
    with sqlite3.connect(str(tmp_db)) as conn:
        reupgraded_schema = _schema_snapshot(conn)
    reupgraded_data = data_fingerprint()

    assert upgraded_schema == reupgraded_schema, "upgrade→downgrade→upgrade 的schema 必须一致"
    assert upgraded_data == reupgraded_data, "往返不得丢失或改变业务数据"
    assert upgraded_data == downgraded_data, "downgrade 不得删除业务行"
    assert upgraded_schema != downgraded_schema, "downgrade 必须真正回退 schema"
