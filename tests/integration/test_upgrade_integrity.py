"""Stage F Wave 3 — old-database upgrade integrity (003 → HEAD).

Builds a representative old-schema database (alembic 003: people / photos /
recognition_results / archive_records / import_batches), snapshots every
existing row, upgrades to HEAD, and verifies zero data loss, zero
unauthorized field changes, expected empty initialization of Stage D/E
tables, FK integrity, and the historical-people backfill interaction.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command

_ALEMBIC_CFG = Path(__file__).resolve().parents[2] / "alembic.ini"
_OLD_REVISION = "003_import_batches_and_roster"
# Stage 4：008 之后 alembic head。
_HEAD_REVISION = "008_archive_identity_and_confidence"


def _load_backfill_service(db_path: Path):
    """Load the backfill service over a real SQLite DB（验证库路径注入）."""
    from photo_archiver.app.repositories import build_sqlite_repositories
    from photo_archiver.application.services.backfill_historical_people_service import (
        BackfillHistoricalPeopleService,
    )
    from photo_archiver.infrastructure.database.sqlite_unit_of_work import (
        SQLiteUnitOfWork,
    )

    repositories = build_sqlite_repositories(db_path)
    service = BackfillHistoricalPeopleService(
        repositories.people,
        repositories.import_batches,
        unit_of_work=SQLiteUnitOfWork(repositories._connection_provider),
    )
    return repositories, service


@pytest.fixture
def old_db(tmp_path: Path) -> Path:
    """Create a representative 003-era database with existing business data."""
    db = tmp_path / "old.sqlite3"
    cfg_base = Path(__file__).resolve().parents[2] / "alembic.ini"
    from alembic.config import Config

    cfg = Config(str(cfg_base))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    cfg.set_main_option("script_location", str(cfg_base.resolve().parent / "alembic"))
    command.upgrade(cfg, _OLD_REVISION)

    conn = sqlite3.connect(db)
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO people (id, name, identity, department, note, created_at,"
        " roster_order, source_batch_id) VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?)",
        ("11111111-1111-1111-1111-111111111111", "已导入人员", now, 4,
         "22222222-2222-2222-2222-222222222222"),
    )
    conn.execute(
        "INSERT INTO people (id, name, created_at) VALUES (?, ?, ?)",
        ("33333333-3333-3333-3333-333333333333", "历史遗留人员", now),
    )
    conn.execute(
        "INSERT INTO folders (id, raw_path, path_base, display_name,"
        " total_photos, scanned_photos, created_at)"
        " VALUES (?, ?, 'absolute', ?, 0, 0, ?)",
        ("77777777-7777-7777-7777-777777777777", str(tmp_path), "seed-folder", now),
    )
    conn.execute(
        "INSERT INTO photos (id, raw_path, path_base, folder_id, original_name,"
        " created_at) VALUES (?, ?, 'absolute', ?, ?, ?)",
        ("44444444-4444-4444-4444-444444444444",
         str(tmp_path / "photo.jpg"), "77777777-7777-7777-7777-777777777777",
         "photo.jpg", now),
    )
    conn.execute(
        "INSERT INTO recognition_results (id, photo_id, person_id, status,"
        " confidence, created_at) VALUES (?, ?, ?, 'approved', 0.9, ?)",
        ("55555555-5555-5555-5555-555555555555",
         "44444444-4444-4444-4444-444444444444",
         "11111111-1111-1111-1111-111111111111", now),
    )
    conn.execute(
        "INSERT INTO import_batches (id, file_name, file_hash, source_type,"
        " status, created_at) VALUES (?, ?, ?, 'xlsx', 'confirmed', ?)",
        ("22222222-2222-2222-2222-222222222222", "历史导入.xlsx", "hash-1", now),
    )
    conn.execute(
        "INSERT INTO import_draft_rows (id, batch_id, source_row, raw_values,"
        " order_index) VALUES (?, ?, 1, '{}', 0)",
        ("66666666-6666-6666-6666-666666666666",
         "22222222-2222-2222-2222-222222222222"),
    )
    conn.commit()
    conn.close()
    return db


def _snapshot(db: Path) -> dict:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    snap: dict = {}
    for table in ("people", "photos", "recognition_results", "import_batches",
                  "import_draft_rows"):
        rows = [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]
        snap[table] = rows
    snap["fk_violations"] = [
        list(row.values()) for row in conn.execute("PRAGMA foreign_key_check")
    ]
    conn.close()
    return snap


def _alembic_version(db: Path) -> str:
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    conn.close()
    return row[0]


def _upgrade_to_head(db: Path) -> None:
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_CFG))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    cfg.set_main_option("script_location", str(_ALEMBIC_CFG.resolve().parent / "alembic"))
    command.upgrade(cfg, "head")


def test_upgrade_preserves_all_existing_data(old_db: Path) -> None:
    before = _snapshot(old_db)
    assert _alembic_version(old_db) == _OLD_REVISION

    _upgrade_to_head(old_db)
    after = _snapshot(old_db)

    assert _alembic_version(old_db) == _HEAD_REVISION
    # 既有表逐行零丢失、零字段变化。
    for table in before:
        assert after[table] == before[table], f"table {table} changed during upgrade"
    # FK 完整性：无 orphan。
    assert after["fk_violations"] == []


def test_stage_d_e_tables_initialized_empty(old_db: Path) -> None:
    """旧库不存在的表为空初始化——预期行为，不属于数据丢失。"""
    _upgrade_to_head(old_db)
    conn = sqlite3.connect(old_db)
    for table in ("recognition_runs", "recognition_run_photos",
                  "recognition_run_scopes", "face_observations",
                  "face_cluster_runs", "face_clusters", "face_cluster_members",
                  "cluster_person_assignments", "person_face_embeddings"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count == 0, f"{table} should initialize empty"
    conn.close()


def test_backfill_after_upgrade_is_idempotent_and_safe(old_db: Path) -> None:
    """升级 → 历史回填：仅链接无批次人员，已有批次/顺序不覆盖；重复执行 no-op。"""
    _upgrade_to_head(old_db)
    repositories, service = _load_backfill_service(old_db)

    first = service.execute()
    assert first.backfilled_count == 1  # 仅"历史遗留人员"（已导入者跳过）
    conn = sqlite3.connect(old_db)
    conn.row_factory = sqlite3.Row
    legacy = dict(conn.execute(
        "SELECT * FROM people WHERE name = '历史遗留人员'").fetchone())
    linked = dict(conn.execute(
        "SELECT * FROM people WHERE name = '已导入人员'").fetchone())
    assert legacy["source_batch_id"] == str(first.batch_id)
    assert legacy["roster_order"] == 5  # 接在已导入人员（order 4）之后
    assert linked["source_batch_id"] == "22222222-2222-2222-2222-222222222222"
    assert linked["roster_order"] == 4  # 已有顺序不覆盖

    second = service.execute()
    assert second.backfilled_count == 0 and second.batch_id is None
    # 识别结果与既有批次零变化（回填不触 recognition_results/import_batches 旧行）。
    assert conn.execute("SELECT COUNT(*) FROM recognition_results").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] == 2
    conn.close()
