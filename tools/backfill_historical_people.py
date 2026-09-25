"""Historical people backfill CLI — Stage F 一次性回填脚本.

owner 批准执行计划 Stage F："历史人员补建导入批次……迁移或一次性脚本 +
失败清单"。对目标数据库执行幂等回填：存量无来源人员 → 历史导入批次
（source_type=backfill，status=confirmed）+ 缺失 roster_order 按创建顺序
补齐。**不触碰 Stage D/E 数据；不覆盖已有 source_batch_id / roster_order。**

用法（repo 根，项目 venv）：

    python tools/backfill_historical_people.py --db "%LOCALAPPDATA%\\PhotoArchiver\\photo_archiver.db"
    python tools/backfill_historical_people.py --db path/to/db --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage F historical people backfill (idempotent).",
    )
    parser.add_argument("--db", required=True, help="target SQLite database path")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would be backfilled without writing",
    )
    args = parser.parse_args()

    from photo_archiver.app.repositories import build_sqlite_repositories
    from photo_archiver.application.services.backfill_historical_people_service import (
        BackfillHistoricalPeopleCommand,
        BackfillHistoricalPeopleService,
    )
    from photo_archiver.infrastructure.database.sqlite_unit_of_work import (
        SQLiteUnitOfWork,
    )

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"database not found: {db_path}")
        return 1
    repositories = build_sqlite_repositories(db_path)
    service = BackfillHistoricalPeopleService(
        repositories.people,
        repositories.import_batches,
        unit_of_work=SQLiteUnitOfWork(repositories._connection_provider),
    )

    if args.dry_run:
        people = repositories.people.list_all()
        legacy = [p for p in people if p.source_batch_id is None]
        print(json.dumps({
            "dry_run": True,
            "legacy_people": len(legacy),
            "already_linked": len(people) - len(legacy),
        }, ensure_ascii=False))
        return 0

    result = service.execute(BackfillHistoricalPeopleCommand())
    print(json.dumps({
        "batch_id": str(result.batch_id) if result.batch_id else None,
        "backfilled": result.backfilled_count,
        "already_linked": result.skipped_already_linked,
        "failures": list(result.failures),
    }, ensure_ascii=False, indent=2))
    return 0 if not result.failures else 1


if __name__ == "__main__":
    sys.exit(main())
