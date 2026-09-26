"""Old-database upgrade integrity verifier — Stage F Wave 3 检查点 2.

对**目标数据库的副本**执行 旧版本 → HEAD 升级并输出前后统计 diff
（people/photos/recognition_results/archive_records/import_batches 计数、
people 关键字段、FK 检查、新表空初始化），再叠加历史人员回填交互验证。
**绝不修改源数据库**——先物理复制到临时目录再升级。

Usage:

    python tools/verify_upgrade_integrity.py --source "%LOCALAPPDATA%\\PhotoArchiver\\photo_archiver.db"
    python tools/verify_upgrade_integrity.py --source path/to/db --json out.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys_path = str(REPO_ROOT / "src")
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

_BASE_TABLES = (
    "people", "photos", "recognition_results", "archive_records",
    "import_batches", "import_draft_rows", "person_embeddings",
)
_STAGE_DE_TABLES = (
    "recognition_runs", "recognition_run_photos", "recognition_run_scopes",
    "face_observations", "face_cluster_runs", "face_clusters",
    "face_cluster_members", "cluster_person_assignments",
    "person_face_embeddings",
)
_EXPECTED_HEAD = "007_assignments_and_person_samples"


def _snapshot(db_path: Path) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    snap: dict = {"tables": {}, "alembic_version": None}
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'",
        )
    }
    for table in (*_BASE_TABLES, *_STAGE_DE_TABLES):
        snap["tables"][table] = (
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if table in tables else None
        )
    try:
        version = conn.execute(
            "SELECT version_num FROM alembic_version",
        ).fetchone()
        snap["alembic_version"] = version[0] if version else None
    except sqlite3.OperationalError:
        snap["alembic_version"] = None  # alembic_version 表不存在（升级前可能）
    snap["people_sample"] = [
        dict(row) for row in conn.execute(
            "SELECT id, name, created_at, roster_order, source_batch_id"
            " FROM people ORDER BY created_at LIMIT 20",
        )
    ]
    snap["fk_violations"] = [
        list(row.values()) for row in conn.execute("PRAGMA foreign_key_check")
    ]
    conn.close()
    return snap


def _upgrade(db_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(cfg, "head")


def _run_backfill(db_path: Path) -> dict:
    from photo_archiver.app.repositories import build_sqlite_repositories
    from photo_archiver.application.services.backfill_historical_people_service import (
        BackfillHistoricalPeopleCommand,
        BackfillHistoricalPeopleService,
    )
    from photo_archiver.infrastructure.database.sqlite_unit_of_work import (
        SQLiteUnitOfWork,
    )

    repositories = build_sqlite_repositories(db_path)
    service = BackfillHistoricalPeopleService(
        repositories.people, repositories.import_batches,
        unit_of_work=SQLiteUnitOfWork(repositories._connection_provider),
    )
    first = service.execute(BackfillHistoricalPeopleCommand())
    second = service.execute(BackfillHistoricalPeopleCommand())
    return {
        "first": {
            "batch_id": str(first.batch_id) if first.batch_id else None,
            "backfilled": first.backfilled_count,
            "already_linked": first.skipped_already_linked,
            "failures": list(first.failures),
        },
        "second_noop": second.backfilled_count == 0 and second.batch_id is None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage F Wave 3 old-DB upgrade integrity verifier (copy-first).",
    )
    parser.add_argument("--source", required=True, help="source DB path (read-only)")
    parser.add_argument("--json", default=None, help="evidence JSON output path")
    parser.add_argument("--skip-backfill", action="store_true")
    args = parser.parse_args()

    import os

    source = Path(os.path.expandvars(args.source))
    if not source.exists():
        print(f"source database not found: {source}")
        return 1
    workdir = Path(tempfile.mkdtemp(prefix="stage_f_upgrade_"))
    copy_path = workdir / "upgrade_copy.sqlite3"
    shutil.copyfile(source, copy_path)
    print(f"[upgrade] source copied to {copy_path} (source untouched)")

    before = _snapshot(copy_path)
    print(f"[upgrade] before: version={before['alembic_version']} "
          f"tables={ {k: v for k, v in before['tables'].items() if v} }")
    _upgrade(copy_path)
    after = _snapshot(copy_path)
    print(f"[upgrade] after: version={after['alembic_version']}")

    diff: dict = {"tables": {}, "people_rows_changed": False}
    for table in (*_BASE_TABLES, *_STAGE_DE_TABLES):
        b, a = before["tables"][table], after["tables"][table]
        if b != a:
            diff["tables"][table] = {"before": b, "after": a, "expected": (
                "新表空初始化（0→0 不变）" if table in _STAGE_DE_TABLES
                else "非预期变化！"
            )}
    diff["people_rows_changed"] = (
        before["people_sample"] != after["people_sample"]
    )
    print(f"[upgrade] base-table count diff: {diff['tables'] or 'none'}")
    print(f"[upgrade] people key-field diff: {diff['people_rows_changed']}")
    print(f"[upgrade] FK violations: before={before['fk_violations']} "
          f"after={after['fk_violations']}")

    ok = (
        after["alembic_version"] == _EXPECTED_HEAD
        and not after["fk_violations"]
        and all(after["tables"][t] == (before["tables"][t] or 0)
                for t in _BASE_TABLES)
        and all(after["tables"][t] == 0 for t in _STAGE_DE_TABLES)
        and not diff["people_rows_changed"]
    )

    backfill = None
    if not args.skip_backfill:
        backfill = _run_backfill(copy_path)
        print(f"[upgrade] backfill: {json.dumps(backfill, ensure_ascii=False)}")

    evidence = {
        "source": str(source),
        "copy": str(copy_path),
        "before": {"alembic_version": before["alembic_version"],
                   "tables": before["tables"]},
        "after": {"alembic_version": after["alembic_version"],
                  "tables": after["tables"]},
        "diff": diff,
        "backfill": backfill,
        "integrity_ok": ok and (backfill is None or backfill["second_noop"]),
    }
    print(f"[upgrade] integrity_ok: {evidence['integrity_ok']}")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(f"[upgrade] evidence JSON written to {args.json}")
    shutil.rmtree(workdir, ignore_errors=True)
    return 0 if evidence["integrity_ok"] else 1


if __name__ == "__main__":
    __import__("sys").exit(main())
