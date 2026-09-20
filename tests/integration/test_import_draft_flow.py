"""Stage A integration tests: import draft parse → preview edits → confirm.

Real SQLite + real FileRosterTableReader + real Parse/Confirm services over
the owner-plan stage-A flows: encoding ladder, delimiter detection, group
titles, multi-name splits, duplicate classes, atomic confirm with stable
roster order, and the 003 migration roundtrip.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from photo_archiver.application.commands.import_draft import (
    ConfirmImportCommand,
    ParseImportDraftCommand,
)
from photo_archiver.application.services import (
    ConfirmImportService,
    ParseImportDraftService,
)
from photo_archiver.domain.entities import BATCH_STATUS_CONFIRMED
from photo_archiver.infrastructure.database.sqlite_person_repository import (
    SQLitePersonRepository,
)
from photo_archiver.infrastructure.importers import FileRosterTableReader

_ALEMBIC_CFG = Path(__file__).resolve().parent.parent.parent / "alembic.ini"


def _services(db_path: Path) -> tuple[ParseImportDraftService, ConfirmImportService, SQLitePersonRepository]:
    """Wire real parse/confirm services over a real SQLite file."""
    from photo_archiver.app.repositories import build_sqlite_repositories

    repositories = build_sqlite_repositories(db_path)
    parse = ParseImportDraftService(
        FileRosterTableReader(), repositories.import_batches, repositories.people,
    )
    confirm = ConfirmImportService(
        repositories.import_batches, repositories.people,
    )
    return parse, confirm, repositories.people


# ── Reader: encoding ladder / delimiter detection ────────────────────────────


def test_reader_decodes_gb18030_csv(tmp_path: Path) -> None:
    """GBK/GB18030-encoded CSV must decode (D2 ladder) with comma delimiter."""
    content = "姓名,工号\n张三,E001\n李四,E002\n"
    path = tmp_path / "roster_gb.csv"
    path.write_bytes(content.encode("gb18030"))
    table = FileRosterTableReader().read_raw(path)
    assert table.encoding == "auto"
    assert table.delimiter == ","
    assert [row[0] for row in table.rows] == ["张三", "李四"]


def test_reader_decodes_utf16_tsv(tmp_path: Path) -> None:
    """UTF-16 + tab delimiter must decode via the BOM-aware ladder."""
    content = "姓名\t工号\nAlice\tA001\n"
    path = tmp_path / "roster_utf16.csv"
    path.write_bytes(content.encode("utf-16"))
    table = FileRosterTableReader().read_raw(path)
    assert table.delimiter == "\t"
    assert table.rows[0][0] == "Alice"


_XLS_FIXTURE = Path(__file__).resolve().parent / "resources" / "roster.xls"


def test_reader_reads_xls(tmp_path: Path) -> None:
    """D1: legacy .xls rosters parse via xlrd (owner-approved dependency).

    Uses the committed binary fixture (written once with xlwt) so the read
    path is exercised on every machine without a writer dependency.
    """
    pytest.importorskip("xlrd")
    assert _XLS_FIXTURE.exists(), "committed .xls fixture missing"
    table = FileRosterTableReader().read_raw(_XLS_FIXTURE)
    assert table.source_type == "xls"
    assert table.header == ["姓名", "工号", "部门"]
    assert [row[0] for row in table.rows] == ["王小明", "李小红"]


# ── Parse → draft rows: warnings and actions ────────────────────────────────


def _write_csv(path: Path, content: str, encoding: str = "utf-8") -> Path:
    path.write_bytes(content.encode(encoding))
    return path


def test_parse_flags_group_title_and_multi_name(tmp_path: Path) -> None:
    """“2组”行默认跳过；顿号串联姓名生成拆分建议而不静默拆分。"""
    path = _write_csv(tmp_path / "roster.csv", "姓名,工号\n1曹徽文、2曹紫夏、3贾偌涵,\n2组\n张三,E001\n")
    parse, _, _ = _services(tmp_path / "a.db")
    draft = parse.execute(ParseImportDraftCommand(path))

    actions = {(row.parsed_name, row.action) for row in draft.rows}
    assert ("2组", "skip") in actions  # 组标题告警 + 默认跳过
    multi = next(row for row in draft.rows if any(w[0] == "multi_name" for w in row.warnings))
    assert "曹徽文" in multi.parsed_name
    assert multi.action == "create"  # 拆分是用户动作，不静默
    assert draft.multi_name_row_ids == (multi.id,)


def test_split_draft_row_creates_one_row_per_name(tmp_path: Path) -> None:
    """拆分动作把一行拆为多人，顺序重排且其余告警保留。"""
    path = _write_csv(tmp_path / "roster.csv", "姓名\n1曹徽文、2曹紫夏、3贾偌涵\n张三\n")
    parse, _, _ = _services(tmp_path / "a.db")
    draft = parse.execute(ParseImportDraftCommand(path))
    multi = next(row for row in draft.rows if any(w[0] == "multi_name" for w in row.warnings))

    split = parse.split_draft_row(draft.batch.id, multi.id)

    names = [row.parsed_name for row in split.rows]
    assert names == ["1曹徽文", "2曹紫夏", "3贾偌涵", "张三"]
    assert all(row.action == "create" for row in split.rows[:3])
    assert not any(w[0] == "multi_name" for row in split.rows[:3] for w in row.warnings)


def test_parse_marks_db_identity_duplicate_as_merge(tmp_path: Path) -> None:
    """与库内已有工号重复 → 强冲突告警 + 默认合并到已有人员。"""
    parse, confirm, people = _services(tmp_path / "a.db")
    first = _write_csv(tmp_path / "first.csv", "姓名,工号\n张三,E001\n")
    draft = parse.execute(ParseImportDraftCommand(first))
    confirm.execute(ConfirmImportCommand(draft.batch.id))

    second = _write_csv(tmp_path / "second.csv", "姓名,工号\n张三,E001\n李四,E002\n")
    draft2 = parse.execute(ParseImportDraftCommand(second))
    row = next(r for r in draft2.rows if r.parsed_identity == "E001")
    assert any(w[0] == "identity_duplicate_db" for w in row.warnings)
    assert row.action == "merge_existing"

    result = confirm.execute(ConfirmImportCommand(draft2.batch.id))
    assert result.imported_count == 1  # 只有李四是新建
    assert result.merged_count == 1
    assert len(people.list_all()) == 2  # 张三未重复创建


# ── Confirm: atomic write with stable roster order ──────────────────────────


def test_confirm_writes_people_with_roster_order(tmp_path: Path) -> None:
    """确认后人员按草稿顺序获得 roster_order，且来源批次可回溯。"""
    path = _write_csv(tmp_path / "roster.csv", "姓名,工号,部门\n张三,E001,工程部\n李四,E002,\n2组\n")
    parse, confirm, people = _services(tmp_path / "a.db")
    draft = parse.execute(ParseImportDraftCommand(path))

    result = confirm.execute(ConfirmImportCommand(draft.batch.id))

    assert result.imported_count == 2
    assert result.skipped_count == 1  # “2组”默认跳过
    all_people = people.list_all()
    assert [p.name for p in all_people] == ["张三", "李四"]  # roster 顺序
    assert all(p.roster_order is not None for p in all_people)
    assert all(p.source_batch_id is not None for p in all_people)
    batch = parse._import_batches.get_batch(draft.batch.id)  # noqa: SLF001  (test readback)
    assert batch is not None and batch.status == BATCH_STATUS_CONFIRMED


def test_cancel_keeps_draft_and_registry_untouched(tmp_path: Path) -> None:
    """取消（不确认）不写正式人员，草稿仍可回看。"""
    path = _write_csv(tmp_path / "roster.csv", "姓名,工号\n张三,E001\n")
    parse, confirm, people = _services(tmp_path / "a.db")
    draft = parse.execute(ParseImportDraftCommand(path))

    # 模拟取消：不调 confirm。
    assert people.list_all() == []
    reread = parse._import_batches.list_draft_rows(draft.batch.id)  # noqa: SLF001
    assert len(reread) == 1


def test_confirm_is_atomic_on_row_error(tmp_path: Path) -> None:
    """行级错误不回滚整批（其余行生效），错误带行号进入结果。"""
    path = _write_csv(tmp_path / "roster.csv", "姓名,工号\n,E001\n张三,E002\n")
    parse, confirm, people = _services(tmp_path / "a.db")
    draft = parse.execute(ParseImportDraftCommand(path))  # 空名行默认 skip，不触发错误
    # 把空名行改为 create，制造确认期实体校验错误
    for row in draft.rows:
        if not row.parsed_name:
            row.action = "create"
    parse.save_draft_rows(draft.batch.id, draft.rows)

    result = confirm.execute(ConfirmImportCommand(draft.batch.id))

    assert result.imported_count == 1  # 张三成功
    assert result.errors and "row" in result.errors[0]
    assert [p.name for p in people.list_all()] == ["张三"]


# ── Migration 003 roundtrip ─────────────────────────────────────────────────


def test_migration_003_roundtrip(tmp_path: Path) -> None:
    """003 upgrade 建草稿表并扩列 people；downgrade 干净回退。"""
    from alembic import command
    from alembic.config import Config

    db = tmp_path / "mig.db"
    cfg = Config(str(_ALEMBIC_CFG))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    cfg.set_main_option("script_location", str(_ALEMBIC_CFG.resolve().parent / "alembic"))

    command.upgrade(cfg, "head")
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )}
    people_cols = {r[1] for r in conn.execute("PRAGMA table_info(people)")}
    conn.close()
    assert {"import_batches", "import_draft_rows"} <= tables
    assert {"roster_order", "source_batch_id"} <= people_cols

    command.downgrade(cfg, "002_split_create_ddl")
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )}
    people_cols = {r[1] for r in conn.execute("PRAGMA table_info(people)")}
    conn.close()
    assert "import_batches" not in tables and "import_draft_rows" not in tables
    assert "roster_order" not in people_cols
