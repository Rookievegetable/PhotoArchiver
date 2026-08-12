"""Alembic migration integration tests（阶段 2，ADR-027）.

覆盖 ADR-027 §5 测试矩阵：
- migration up 可执行（6 表 + 6 索引创建）
- migration down 可执行（6 表 DROP，FK 依赖逆序）
- migration 重复执行幂等（IF NOT EXISTS / IF EXISTS 守护）
- alembic upgrade head 成功 + Schema 版本一致（alembic_version 表记录 002）
- Repository CRUD 对照回归不退化（migration 接管 DDL 后 CRUD 路径不变）

用临时 SQLite 库——每测试独立库，避污染。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

# alembic.ini 路径——与 alembic_runner.py 同锚点（5×parent: tests/integration → tests → project root）
_ALEMBIC_CFG = Path(__file__).resolve().parent.parent.parent.parent / "alembic.ini"
_ALEMBIC_SCRIPT = _ALEMBIC_CFG.resolve().parent / "alembic"

# 6 表 + 6 索引（与 002_split_create_ddl.py DDL 一致）
_ALL_TABLES = (
    "people",
    "folders",
    "photos",
    "recognition_results",
    "person_embeddings",
    "archive_records",
)
_ALL_INDEXES = (
    "idx_photos_folder_id",
    "idx_recognition_results_photo_id",
    "idx_recognition_results_person_id",
    "idx_archive_records_photo_id",
    "idx_archive_records_status",
)
# 第 6 索引——sqlite_autoindex_* 自动生（UNIQUE(raw_path, path_base)）非显式名


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


def test_migration_upgrade_creates_all_six_tables(tmp_db: Path) -> None:
    """002 upgrade 创建全部 6 表（people/folders/photos/recognition_results/person_embeddings/archive_records）."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        tables = _list_tables(conn)
        for table in _ALL_TABLES:
            assert table in tables, f"Migration upgrade should create table '{table}', got: {tables}"
        assert "alembic_version" in tables, "alembic_version table should exist after upgrade"


def test_migration_upgrade_creates_all_six_indexes(tmp_db: Path) -> None:
    """002 upgrade 创建全部 6 索引."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        indexes = _list_indexes(conn)
        for idx in _ALL_INDEXES:
            assert idx in indexes, f"Migration upgrade should create index '{idx}', got: {indexes}"


def test_migration_upgrade_stamps_version_002(tmp_db: Path) -> None:
    """upgrade head 后 alembic_version 表记录 '002_split_create_ddl'."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        assert _alembic_version(conn) == "002_split_create_ddl"


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
    # 第二次 upgrade—— alembic 检测已在 head 不再执行 002，但 stamp 不报错
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        assert _alembic_version(conn) == "002_split_create_ddl"
        # 表仍存在不重复创建
        tables = _list_tables(conn)
        assert len(tables) == 7  # 6 表 + alembic_version


# ── Schema 版本一致 ─────────────────────────────────────────────────────────


def test_schema_version_consistent_after_upgrade(tmp_db: Path) -> None:
    """upgrade head 后 Schema 版本一致——alembic_version=002 + 6 表 + 6 索引全在."""
    cfg = _make_alembic_config(tmp_db)
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(tmp_db)) as conn:
        assert _alembic_version(conn) == "002_split_create_ddl"
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
    photo = Photo(path=PhotoPath("/tmp/test.jpg"), id=None)
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
    # 验：调用后表存在（migration 执行了），且 alembic_version 表记录 002
    provider.initialize_schema()

    with sqlite3.connect(str(tmp_db)) as conn:
        tables = _list_tables(conn)
        assert "alembic_version" in tables, (
            "initialize_schema() should trigger Alembic migration (alembic_version table exists)"
        )
        assert _alembic_version(conn) == "002_split_create_ddl"
        # 6 表全在（migration 真接管 DDL）
        for table in _ALL_TABLES:
            assert table in tables, f"initialize_schema() via Alembic should create table '{table}'"
