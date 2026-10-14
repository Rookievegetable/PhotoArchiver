"""Tests for the top-level application entrypoint."""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import main as main_module
from photo_archiver.application import ScanAndRegisterPhotosCommand, ScanAndRegisterPhotosResult


class StubScanAndRegisterPhotosService:
    """Capture scan commands and return a configured result."""

    def __init__(self, result: ScanAndRegisterPhotosResult) -> None:
        self.result = result
        self.commands: list[ScanAndRegisterPhotosCommand] = []

    def execute(self, command: ScanAndRegisterPhotosCommand) -> ScanAndRegisterPhotosResult:
        self.commands.append(command)
        return self.result


def test_main_runs_scan_command(monkeypatch, capsys) -> None:
    """The scan CLI delegates to the scan-and-register service."""
    service = StubScanAndRegisterPhotosService(
        ScanAndRegisterPhotosResult(discovered_count=2, registered_count=1, skipped_count=1)
    )
    context = SimpleNamespace(
        services=SimpleNamespace(scan_and_register_photos=service),
    )
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["scan", "photos", "--no-recursive", "--name", "Family"])

    assert exit_code == 0
    assert service.commands == [
        ScanAndRegisterPhotosCommand(
            folder_path=Path("photos"),
            recursive=False,
            folder_display_name="Family",
        )
    ]
    captured = capsys.readouterr()
    assert "discovered=2" in captured.out
    assert "registered=1" in captured.out
    assert captured.err == ""


def test_main_returns_failure_when_scan_has_errors(monkeypatch, capsys) -> None:
    """The scan CLI reports item-level failures through its exit code and stderr."""
    service = StubScanAndRegisterPhotosService(
        ScanAndRegisterPhotosResult(discovered_count=1, failed_count=1, errors=("bad.jpg",))
    )
    context = SimpleNamespace(
        services=SimpleNamespace(scan_and_register_photos=service),
    )
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["scan", "photos"])

    assert exit_code == 1
    assert service.commands[0].recursive is True
    captured = capsys.readouterr()
    assert "failed=1" in captured.out
    assert "Error: bad.jpg" in captured.err


# ---- prune-missing CLI（Phase E E-5，ADR-034 D5）----


class StubPruneMissingPhotosService:
    """Capture prune preview/execute calls and return configured results."""

    def __init__(self, preview, result=None):
        self._preview = preview
        self._result = result
        self.executed_command = None

    def preview(self):
        return self._preview

    def execute(self, command):
        self.executed_command = command
        return self._result


def _prune_preview():
    """Preview with one missing registration."""
    from photo_archiver.application.dtos.deletion import MissingPhotoItem, PruneMissingPreview

    return PruneMissingPreview(
        scanned=2,
        items=(MissingPhotoItem(photo_id=uuid4(), disk_path=Path("/photos/gone.jpg")),),
        unresolvable=0,
    )


def _prune_prune_result():
    from photo_archiver.application.dtos.deletion import PruneMissingResult

    return PruneMissingResult(scanned=2, missing=1, requested=1, pruned=1, rejected=0, unresolvable=0)


def test_main_prune_missing_dry_run_lists_but_does_not_execute(monkeypatch, capsys) -> None:
    """默认 dry-run：列出失联登记，不调用 execute（不删除）。"""
    service = StubPruneMissingPhotosService(_prune_preview(), _prune_prune_result())
    context = SimpleNamespace(
        services=SimpleNamespace(prune_missing_photos=service),
    )
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["prune-missing"])

    assert exit_code == 0
    assert service.executed_command is None  # dry-run 绝不执行
    captured = capsys.readouterr()
    assert "Dry-run: nothing pruned" in captured.out
    assert "missing" in captured.out


def test_main_prune_missing_execute_removes_registrations(monkeypatch, capsys) -> None:
    """--execute：确认后执行清理，输出 pruned 计数。"""
    service = StubPruneMissingPhotosService(_prune_preview(), _prune_prune_result())
    context = SimpleNamespace(
        services=SimpleNamespace(prune_missing_photos=service),
    )
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["prune-missing", "--execute"])

    assert exit_code == 0
    assert service.executed_command is not None
    assert len(service.executed_command.photo_ids) == 1
    captured = capsys.readouterr()
    assert "Prune complete: pruned=1" in captured.out
    assert "unresolvable=0" in captured.out


def test_main_prune_missing_nothing_missing(monkeypatch, capsys) -> None:
    """无失联登记 → 提示信息且不执行。"""
    from photo_archiver.application.dtos.deletion import PruneMissingPreview

    empty = PruneMissingPreview(scanned=1, items=(), unresolvable=0)
    service = StubPruneMissingPhotosService(empty, None)
    context = SimpleNamespace(
        services=SimpleNamespace(prune_missing_photos=service),
    )
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["prune-missing", "--execute"])

    assert exit_code == 0
    assert service.executed_command is None
    captured = capsys.readouterr()
    assert "no missing registrations found" in captured.out


# ---- backfill-capture-time CLI（Phase F F-1，ADR-035）----


class StubBackfillCaptureTimeService:
    """Capture backfill commands and return a configured result."""

    def __init__(self, result):
        self.result = result
        self.commands: list = []

    def execute(self, command):
        self.commands.append(command)
        return self.result


def _capture_result(dry_run: bool):
    from photo_archiver.application.services.backfill_capture_time_service import (
        BackfillCaptureTimeResult,
    )

    return BackfillCaptureTimeResult(
        scanned=1,
        updated=0 if dry_run else 1,
        would_update=1 if dry_run else 0,
        unchanged=0,
        failed=0,
        skipped_missing=0,
    )


def test_main_backfill_capture_time_dry_run_by_default(monkeypatch, capsys) -> None:
    """默认 dry-run：只报差异计数，不写库，提示 --execute。"""
    service = StubBackfillCaptureTimeService(_capture_result(dry_run=True))
    context = SimpleNamespace(
        services=SimpleNamespace(backfill_capture_time=service),
    )
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["backfill-capture-time"])

    assert exit_code == 0
    assert service.commands[0].dry_run is True
    captured = capsys.readouterr()
    assert "would_update=1" in captured.out
    assert "Dry-run: nothing written" in captured.out


def test_main_backfill_capture_time_execute_updates(monkeypatch, capsys) -> None:
    """--execute：写入纠错，输出 updated 计数。"""
    service = StubBackfillCaptureTimeService(_capture_result(dry_run=False))
    context = SimpleNamespace(
        services=SimpleNamespace(backfill_capture_time=service),
    )
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["backfill-capture-time", "--execute"])

    assert exit_code == 0
    assert service.commands[0].dry_run is False
    captured = capsys.readouterr()
    assert "updated=1" in captured.out
    assert "Dry-run" not in captured.out

class StubImportPeopleService:
    """Capture import commands and return a configured result."""

    def __init__(self) -> None:
        from photo_archiver.application.dtos import ImportPeopleResult

        self.result = ImportPeopleResult(imported_count=2, skipped_count=1)
        self.commands: list = []

    def execute(self, command):
        self.commands.append(command)
        return self.result


class StubExportService:
    """Capture export calls and echo the output path."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def export(self, exporter, output_path, scope, criteria=None):
        self.calls.append((exporter, output_path, scope, criteria))
        return output_path


def test_main_runs_import_people_command(monkeypatch, capsys, tmp_path) -> None:
    """ADR-036 F-6: import-people delegates to the real import pipeline."""
    service = StubImportPeopleService()
    context = SimpleNamespace(services=SimpleNamespace(import_people=service))
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    source = tmp_path / "people.txt"
    exit_code = main_module.main(["import-people", str(source), "--no-header"])

    assert exit_code == 0
    command = service.commands[0]
    assert command.source_path == source
    assert command.has_header is False
    assert command.sheet_name is None
    captured = capsys.readouterr()
    assert "imported=2" in captured.out
    assert "skipped=1" in captured.out


def test_main_import_people_reports_errors_with_failure_exit(monkeypatch, capsys, tmp_path) -> None:
    from photo_archiver.application.dtos import ImportPeopleResult

    service = StubImportPeopleService()
    service.result = ImportPeopleResult(
        imported_count=0, skipped_count=0, errors=("row 3: bad data",)
    )
    context = SimpleNamespace(services=SimpleNamespace(import_people=service))
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["import-people", str(tmp_path / "people.txt")])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "row 3: bad data" in captured.err


def test_main_export_all_scope_derives_format_from_suffix(monkeypatch, capsys, tmp_path) -> None:
    """ADR-036 F-6: export ALL with format derived from the output suffix."""
    from photo_archiver.application.dtos.export import ExportScope
    from photo_archiver.infrastructure.exporters import CsvExporter

    service = StubExportService()
    context = SimpleNamespace(services=SimpleNamespace(export=service))
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    output = tmp_path / "library.csv"
    exit_code = main_module.main(["export", str(output)])

    assert exit_code == 0
    exporter, path, scope, criteria = service.calls[0]
    assert isinstance(exporter, CsvExporter)
    assert path == str(output)
    assert scope is ExportScope.ALL
    assert criteria is None
    captured = capsys.readouterr()
    assert str(output) in captured.out


def test_main_export_filtered_resolves_person_by_name(monkeypatch, capsys, tmp_path) -> None:
    """FILTERED scope builds criteria from flags; person name resolves via the repo."""
    from datetime import datetime

    from photo_archiver.application.dtos.export import ExportScope
    from photo_archiver.domain import MatchStatus, Person
    from photo_archiver.infrastructure.exporters import ExcelExporter

    alice = Person(name="Alice")
    service = StubExportService()
    people_repo = SimpleNamespace(list_all=lambda: [alice])
    context = SimpleNamespace(
        services=SimpleNamespace(export=service),
        repositories=SimpleNamespace(people=people_repo),
    )
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    output = tmp_path / "filtered.xlsx"
    exit_code = main_module.main(
        [
            "export", str(output),
            "--scope", "filtered",
            "--status", "approved",
            "--person", "Alice",
            "--captured-to", "2024-12-31",
        ]
    )

    assert exit_code == 0
    exporter, _, scope, criteria = service.calls[0]
    assert isinstance(exporter, ExcelExporter)
    assert scope is ExportScope.FILTERED
    assert criteria is not None
    assert criteria.match_status is MatchStatus.APPROVED
    assert criteria.person_id == alice.id
    assert criteria.captured_to is not None
    assert criteria.captured_to <= datetime(2024, 12, 31, 23, 59, 59)
    assert criteria.captured_to > datetime(2024, 12, 31, 0, 0, 0)


def test_main_export_filtered_without_flags_is_rejected(monkeypatch, capsys, tmp_path) -> None:
    """FILTERED without any filter flag is rejected at the CLI boundary."""
    service = StubExportService()
    context = SimpleNamespace(services=SimpleNamespace(export=service))
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(
        ["export", str(tmp_path / "out.csv"), "--scope", "filtered"]
    )

    assert exit_code == 2
    assert service.calls == []
    captured = capsys.readouterr()
    assert "scope=filtered requires" in captured.err


def test_main_export_unknown_person_fails_cleanly(monkeypatch, capsys, tmp_path) -> None:
    service = StubExportService()
    people_repo = SimpleNamespace(list_all=lambda: [])
    context = SimpleNamespace(
        services=SimpleNamespace(export=service),
        repositories=SimpleNamespace(people=people_repo),
    )
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(
        ["export", str(tmp_path / "out.csv"), "--scope", "filtered", "--person", "Nobody"]
    )

    assert exit_code == 2
    assert service.calls == []
    captured = capsys.readouterr()
    assert "person not found: 'Nobody'" in captured.err


class StubCleanupThumbnailsService:
    """Capture dry-run flags and echo a configured cleanup result."""

    def __init__(self) -> None:
        self.calls: list[bool] = []

    def execute(self, *, dry_run: bool):
        from photo_archiver.application.services.cleanup_thumbnail_cache_service import (
            ThumbnailCacheCleanupResult,
        )

        self.calls.append(dry_run)
        return ThumbnailCacheCleanupResult(removed=3, retained=9, dry_run=dry_run)


def test_main_cleanup_thumbnails_dry_run_by_default(monkeypatch, capsys) -> None:
    """ADR-036 收口（ISSUE-023）：cleanup-thumbnails 默认 dry-run。"""
    service = StubCleanupThumbnailsService()
    context = SimpleNamespace(services=SimpleNamespace(cleanup_thumbnails=service))
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["cleanup-thumbnails"])

    assert exit_code == 0
    assert service.calls == [True]
    captured = capsys.readouterr()
    assert "would_remove=3" in captured.out
    assert "Dry-run" in captured.out


def test_main_cleanup_thumbnails_execute_removes(monkeypatch, capsys) -> None:
    service = StubCleanupThumbnailsService()
    context = SimpleNamespace(services=SimpleNamespace(cleanup_thumbnails=service))
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["cleanup-thumbnails", "--execute"])

    assert exit_code == 0
    assert service.calls == [False]
    captured = capsys.readouterr()
    assert "removed=3" in captured.out
    assert "Dry-run" not in captured.out


def _make_sqlite_db(path, with_row: bool = False) -> None:
    """Create a minimal PhotoArchiver-shaped database (photos/people/folders)."""
    import sqlite3

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        for table in ("photos", "people", "folders"):
            connection.execute(f"CREATE TABLE {table} (id TEXT PRIMARY KEY)")
        if with_row:
            connection.execute("INSERT INTO people (id) VALUES ('legacy-person')")
        connection.commit()
    finally:
        connection.close()


def _patch_migrate_env(monkeypatch, tmp_path) -> None:
    """Pin the anchored-default paths and settings inside the migrate runner."""
    anchored_dir = tmp_path / "anchored"
    monkeypatch.setattr(
        main_module, "default_database_url",
        lambda: f"sqlite:///{anchored_dir / 'photo_archiver.db'}",
    )
    monkeypatch.setattr(
        main_module, "default_database_path",
        lambda: anchored_dir / "photo_archiver.db",
    )
    monkeypatch.setattr(
        main_module, "AppSettings",
        lambda: SimpleNamespace(
            database_url=f"sqlite:///{anchored_dir / 'photo_archiver.db'}"
        ),
    )


def test_main_migrate_refuses_when_database_url_is_explicit(
    monkeypatch, capsys, tmp_path
) -> None:
    """migrate only serves the anchored-default takeover scenario."""
    monkeypatch.setattr(
        main_module, "default_database_url", lambda: "sqlite:///anchored.db"
    )
    monkeypatch.setattr(
        main_module, "AppSettings",
        lambda: SimpleNamespace(database_url="sqlite:///explicit.db"),
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main_module.main(["migrate"])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "explicit" in captured.err


def test_main_migrate_reports_missing_legacy_database(monkeypatch, capsys, tmp_path) -> None:
    _patch_migrate_env(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)  # no data/photo_archiver.db here

    exit_code = main_module.main(["migrate"])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "No legacy database found" in captured.err


def test_main_migrate_dry_run_plans_without_copying(monkeypatch, capsys, tmp_path) -> None:
    _patch_migrate_env(monkeypatch, tmp_path)
    legacy = tmp_path / "data" / "photo_archiver.db"
    _make_sqlite_db(legacy, with_row=True)
    monkeypatch.chdir(tmp_path)

    exit_code = main_module.main(["migrate"])

    assert exit_code == 0
    assert not (tmp_path / "anchored" / "photo_archiver.db").exists()
    captured = capsys.readouterr()
    assert "Migration plan (dry-run)" in captured.out
    assert "nothing copied" in captured.out


def test_main_migrate_execute_copies_and_leaves_legacy_in_place(
    monkeypatch, capsys, tmp_path
) -> None:
    import sqlite3

    _patch_migrate_env(monkeypatch, tmp_path)
    legacy = tmp_path / "data" / "photo_archiver.db"
    _make_sqlite_db(legacy, with_row=True)
    monkeypatch.chdir(tmp_path)

    exit_code = main_module.main(["migrate", "--execute"])

    assert exit_code == 0
    target = tmp_path / "anchored" / "photo_archiver.db"
    assert target.exists()
    connection = sqlite3.connect(target)
    try:
        rows = connection.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    finally:
        connection.close()
    assert rows == 1  # 数据随快照迁移
    assert legacy.exists()  # copy-not-move：原库原地保留


def test_main_migrate_execute_takes_over_empty_anchored_target(
    monkeypatch, capsys, tmp_path
) -> None:
    """bootstrap 已创建的空锚定库可被安全接管（启动备份已留快照）。"""
    _patch_migrate_env(monkeypatch, tmp_path)
    legacy = tmp_path / "data" / "photo_archiver.db"
    _make_sqlite_db(legacy, with_row=True)
    monkeypatch.chdir(tmp_path)
    _make_sqlite_db(tmp_path / "anchored" / "photo_archiver.db", with_row=False)

    exit_code = main_module.main(["migrate", "--execute"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Migration complete" in captured.out


def test_main_migrate_refuses_non_empty_target(monkeypatch, capsys, tmp_path) -> None:
    _patch_migrate_env(monkeypatch, tmp_path)
    legacy = tmp_path / "data" / "photo_archiver.db"
    _make_sqlite_db(legacy, with_row=True)
    monkeypatch.chdir(tmp_path)
    _make_sqlite_db(tmp_path / "anchored" / "photo_archiver.db", with_row=True)

    exit_code = main_module.main(["migrate", "--execute"])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "already exists and holds data" in captured.err
    assert legacy.exists()  # 任何分支都不动旧库


class StubMatchServiceForCli:
    """Capture recognize commands; optionally raise ModelPackMissing."""

    def __init__(self, results, error=None, with_reporter=True) -> None:
        import contextlib

        self._results = results
        self._error = error
        self._with_reporter = with_reporter
        self._reporter = None
        self.commands: list = []
        self._ctx = contextlib

    def bind_progress_reporter(self, reporter):  # noqa: ANN001
        self._reporter = reporter
        return self._ctx.nullcontext()

    def execute(self, command):  # noqa: ANN001
        self.commands.append(command)
        if self._error is not None:
            raise self._error
        if self._with_reporter and self._reporter is not None:
            for index in range(1, len(command.photo_ids) + 1):
                self._reporter.report(index, len(command.photo_ids), "Matched photo")
        return self._results


def _match_cli_context(monkeypatch, tmp_path, *, people=1, photos=3, already_matched=0):
    """Build a CLI context with N people, M photos, K pre-matched photos."""
    from datetime import datetime

    from photo_archiver.domain import Folder, MatchStatus, Person, Photo, PhotoPath

    people_rows = [Person(name=f"Person{i}") for i in range(people)]
    folder = Folder(path=PhotoPath("photos"), total_photos=photos)
    photo_rows = []
    for index in range(photos):
        photo_rows.append(
            Photo(
                path=PhotoPath(f"photos/p{index}.jpg"),
                folder_id=folder.id,
                original_name=f"p{index}.jpg",
                captured_at=datetime(2024, 1, 1, 8, 0, 0),
            )
        )
    matched = {photo_rows[i].id: "sentinel" for i in range(already_matched)}

    def _list_by_photo_ids(photo_ids):
        """Stub：返回这些照片的全部（合成）识别记录。

        ``already_matched`` 的照片各生成一条 APPROVED 哨兵行，其余照片零行——
        与既有 ``list_first_by_photo_ids`` Stub 的语义保持一致。
        """
        results = []
        for pid in photo_ids:
            if pid in matched:
                results.append(
                    SimpleNamespace(
                        photo_id=pid, status=MatchStatus.APPROVED
                    )
                )
        return results

    repositories = SimpleNamespace(
        people=SimpleNamespace(list_all=lambda: people_rows),
        photos=SimpleNamespace(list_all=lambda: photo_rows),
        recognition=SimpleNamespace(
            list_first_by_photo_ids=lambda ids: dict(matched),
            list_by_photo_ids=_list_by_photo_ids,
        ),
    )
    return repositories, photo_rows, MatchStatus


def test_main_recognize_resumes_unmatched_photos_only(monkeypatch, capsys, tmp_path) -> None:
    from photo_archiver.application.dtos import MatchResult
    from photo_archiver.domain import FaceBox

    repositories, photo_rows, _ = _match_cli_context(
        monkeypatch, tmp_path, photos=3, already_matched=1
    )
    results = tuple(
        MatchResult(photo_id=photo.id, box=FaceBox(x1=0, y1=0, x2=10, y2=10))
        for photo in photo_rows[1:]
    )
    service = StubMatchServiceForCli(results)
    context = SimpleNamespace(services=SimpleNamespace(match_persons=service), repositories=repositories)
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["recognize"])

    assert exit_code == 0
    command = service.commands[0]
    unmatched = {photo_rows[1].id, photo_rows[2].id}
    assert set(command.photo_ids) == unmatched
    assert len(command.images) == 2
    captured = capsys.readouterr()
    assert "processed=2" in captured.out
    assert "faces_found=2" in captured.out
    assert "  [1/2]" in captured.out  # 进度行


def test_main_recognize_all_flag_reruns_every_photo(monkeypatch, capsys, tmp_path) -> None:
    from photo_archiver.application.dtos import MatchResult

    repositories, photo_rows, _ = _match_cli_context(
        monkeypatch, tmp_path, photos=3, already_matched=1
    )
    results = tuple(MatchResult(photo_id=photo.id, box=None) for photo in photo_rows)
    service = StubMatchServiceForCli(results)
    context = SimpleNamespace(services=SimpleNamespace(match_persons=service), repositories=repositories)
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["recognize", "--all"])

    assert exit_code == 0
    assert len(service.commands[0].photo_ids) == 3
    captured = capsys.readouterr()
    assert "no_face=3" in captured.out


def test_main_recognize_limit_caps_batch(monkeypatch, tmp_path) -> None:
    from photo_archiver.application.dtos import MatchResult

    repositories, photo_rows, _ = _match_cli_context(monkeypatch, tmp_path, photos=3)
    results = tuple(MatchResult(photo_id=photo.id, box=None) for photo in photo_rows)
    service = StubMatchServiceForCli(results)
    context = SimpleNamespace(services=SimpleNamespace(match_persons=service), repositories=repositories)
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["recognize", "--limit", "2"])

    assert exit_code == 0
    assert len(service.commands[0].photo_ids) == 2


# ── AUD-030：--all 的 PENDING 防重过滤（仅 --all 路径；默认续跑不变） ────────


def _match_cli_context_with_recognition_rows(
    monkeypatch, tmp_path, *, photos, rows_by_index
):
    """CLI 上下文：photos 张照片，rows_by_index 指定各照片的既有识别记录状态列表。"""
    from datetime import datetime

    from photo_archiver.domain import Folder, MatchStatus, Person, Photo, PhotoPath

    people_rows = [Person(name="Person0")]
    folder = Folder(path=PhotoPath("photos"), total_photos=photos)
    photo_rows = []
    recognition_rows = []
    for index in range(photos):
        photo_rows.append(
            Photo(
                path=PhotoPath(f"photos/p{index}.jpg"),
                folder_id=folder.id,
                original_name=f"p{index}.jpg",
                captured_at=datetime(2024, 1, 1, 8, 0, 0),
            )
        )
        for order, status in enumerate(rows_by_index.get(index, [])):
            from photo_archiver.domain import RecognitionResult

            recognition_rows.append(
                RecognitionResult(
                    photo_id=photo_rows[index].id,
                    person_id=None,
                    confidence=None,
                    status=status,
                    created_at=datetime(2024, 1, 2, 8, 0, order),
                )
            )
    repositories = SimpleNamespace(
        people=SimpleNamespace(list_all=lambda: people_rows),
        photos=SimpleNamespace(list_all=lambda: photo_rows),
        recognition=SimpleNamespace(
            list_first_by_photo_ids=lambda ids: {},
            list_by_photo_ids=lambda ids: list(recognition_rows),
        ),
    )
    return repositories, photo_rows, MatchStatus


def _cli_recognize_all(monkeypatch, repositories, photo_rows):
    from photo_archiver.application.dtos import MatchResult

    results = tuple(MatchResult(photo_id=photo.id, box=None) for photo in photo_rows)
    service = StubMatchServiceForCli(results)
    context = SimpleNamespace(
        services=SimpleNamespace(match_persons=service), repositories=repositories
    )
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)
    exit_code = main_module.main(["recognize", "--all"])
    submitted = list(service.commands[0].photo_ids) if service.commands else []
    return exit_code, submitted


def test_aud030_all_without_results_processes_photo(monkeypatch, tmp_path) -> None:
    """AUD-030 T01：无任何识别记录的照片在 --all 下仍被处理。"""
    repositories, photo_rows, _ = _match_cli_context_with_recognition_rows(
        monkeypatch, tmp_path, photos=1, rows_by_index={}
    )
    _, submitted = _cli_recognize_all(monkeypatch, repositories, photo_rows)
    assert submitted == [photo_rows[0].id]


def test_aud030_all_skips_photo_with_pending(monkeypatch, tmp_path) -> None:
    """AUD-030 T02：存在 PENDING 的照片被 --all 跳过，不再追加记录。"""
    from photo_archiver.domain import MatchStatus

    repositories, photo_rows, _ = _match_cli_context_with_recognition_rows(
        monkeypatch, tmp_path, photos=1, rows_by_index={0: [MatchStatus.PENDING]}
    )
    _, submitted = _cli_recognize_all(monkeypatch, repositories, photo_rows)
    assert submitted == []


def test_aud030_all_skips_photo_with_multiple_pending(monkeypatch, tmp_path) -> None:
    """AUD-030 T03/T06：多条历史 PENDING（含与终态混合）均触发跳过。"""
    from photo_archiver.domain import MatchStatus

    repositories, photo_rows, _ = _match_cli_context_with_recognition_rows(
        monkeypatch,
        tmp_path,
        photos=1,
        rows_by_index={0: [MatchStatus.PENDING, MatchStatus.PENDING]},
    )
    _, submitted = _cli_recognize_all(monkeypatch, repositories, photo_rows)
    assert submitted == []


def test_aud030_all_keeps_approved_rerun(monkeypatch, tmp_path) -> None:
    """AUD-030 T04：仅有 APPROVED（无 PENDING）的照片保留 --all 重跑语义。"""
    from photo_archiver.domain import MatchStatus

    repositories, photo_rows, _ = _match_cli_context_with_recognition_rows(
        monkeypatch, tmp_path, photos=1, rows_by_index={0: [MatchStatus.APPROVED]}
    )
    _, submitted = _cli_recognize_all(monkeypatch, repositories, photo_rows)
    assert submitted == [photo_rows[0].id]


def test_aud030_all_keeps_rejected_rerun(monkeypatch, tmp_path) -> None:
    """AUD-030 T05：仅有 REJECTED（无 PENDING）的照片保留 --all 重跑语义。"""
    from photo_archiver.domain import MatchStatus

    repositories, photo_rows, _ = _match_cli_context_with_recognition_rows(
        monkeypatch, tmp_path, photos=1, rows_by_index={0: [MatchStatus.REJECTED]}
    )
    _, submitted = _cli_recognize_all(monkeypatch, repositories, photo_rows)
    assert submitted == [photo_rows[0].id]


def test_aud030_all_mixed_finalized_and_pending_skips(monkeypatch, tmp_path) -> None:
    """AUD-030 T06：终态 + PENDING 混合 → 任一 PENDING 即跳过（不因首条终态放行）。"""
    from photo_archiver.domain import MatchStatus

    repositories, photo_rows, _ = _match_cli_context_with_recognition_rows(
        monkeypatch,
        tmp_path,
        photos=1,
        rows_by_index={0: [MatchStatus.APPROVED, MatchStatus.PENDING]},
    )
    _, submitted = _cli_recognize_all(monkeypatch, repositories, photo_rows)
    assert submitted == []


def test_aud030_all_limit_applies_after_pending_filter(
    monkeypatch, tmp_path
) -> None:
    """AUD-030 T08：--limit 在 PENDING 过滤之后生效，被跳过的照片不占名额。"""
    from photo_archiver.domain import MatchStatus

    repositories, photo_rows, _ = _match_cli_context_with_recognition_rows(
        monkeypatch,
        tmp_path,
        photos=4,
        rows_by_index={0: [MatchStatus.PENDING]},
    )
    _, submitted = _cli_recognize_all_limit(
        monkeypatch, repositories, photo_rows, limit=2
    )
    # 4 张照片中 p0 有 PENDING 被过滤 → 剩 p1、p2、p3 → 取前 2 张。
    assert submitted == [photo_rows[1].id, photo_rows[2].id]


def test_aud030_all_no_limit_no_extra_cap(monkeypatch, tmp_path) -> None:
    """AUD-030 单元覆盖：无 --limit 时不产生额外限额，过滤后全部提交。"""
    from photo_archiver.domain import MatchStatus

    repositories, photo_rows, _ = _match_cli_context_with_recognition_rows(
        monkeypatch, tmp_path, photos=3, rows_by_index={0: [MatchStatus.PENDING]}
    )
    _, submitted = _cli_recognize_all(monkeypatch, repositories, photo_rows)
    assert submitted == [photo_rows[1].id, photo_rows[2].id]


def test_aud030_all_default_resume_path_unchanged(monkeypatch, tmp_path) -> None:
    """AUD-030：默认续跑模式不经过 --all 过滤，既有行为不变。"""

    from photo_archiver.application.dtos import MatchResult
    from photo_archiver.domain import MatchStatus

    repositories, photo_rows, _ = _match_cli_context_with_recognition_rows(
        monkeypatch, tmp_path, photos=2, rows_by_index={0: [MatchStatus.PENDING]}
    )
    from photo_archiver.domain import FaceBox

    results = tuple(
        MatchResult(photo_id=photo.id, box=FaceBox(x1=0, y1=0, x2=8, y2=8))
        for photo in photo_rows[1:]
    )
    service = StubMatchServiceForCli(results)
    context = SimpleNamespace(
        services=SimpleNamespace(match_persons=service), repositories=repositories
    )
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["recognize"])

    # 默认模式：p0 无记录 → 处理；p1 有 PENDING——默认模式按既有语义处理全部
    # 无记录照片（p1），p0 无记录同样处理；此处断言提交集 = 无记录照片。
    assert exit_code == 0
    assert set(service.commands[0].photo_ids) == {
        photo_rows[0].id,
        photo_rows[1].id,
    }


def _cli_recognize_all_limit(monkeypatch, repositories, photo_rows, *, limit):
    from photo_archiver.application.dtos import MatchResult

    results = tuple(MatchResult(photo_id=photo.id, box=None) for photo in photo_rows)
    service = StubMatchServiceForCli(results)
    context = SimpleNamespace(
        services=SimpleNamespace(match_persons=service), repositories=repositories
    )
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)
    exit_code = main_module.main(["recognize", "--all", "--limit", str(limit)])
    submitted = list(service.commands[0].photo_ids) if service.commands else []
    return exit_code, submitted


def test_aud030_all_mixed_batch_order_stable(monkeypatch, tmp_path) -> None:
    """AUD-030 T08 补充：过滤保持注册序相对顺序（不重排）。"""
    from photo_archiver.domain import MatchStatus

    repositories, photo_rows, _ = _match_cli_context_with_recognition_rows(
        monkeypatch,
        tmp_path,
        photos=4,
        rows_by_index={1: [MatchStatus.PENDING]},
    )
    _, submitted = _cli_recognize_all(monkeypatch, repositories, photo_rows)
    assert submitted == [photo_rows[0].id, photo_rows[2].id, photo_rows[3].id]


def test_main_recognize_refuses_without_people(monkeypatch, capsys, tmp_path) -> None:
    repositories, _, _ = _match_cli_context(monkeypatch, tmp_path, people=0)
    service = StubMatchServiceForCli(())
    context = SimpleNamespace(services=SimpleNamespace(match_persons=service), repositories=repositories)
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["recognize"])

    assert exit_code == 2
    assert "no persons registered" in capsys.readouterr().err


def test_main_recognize_reports_everything_matched(monkeypatch, capsys, tmp_path) -> None:
    repositories, photo_rows, _ = _match_cli_context(
        monkeypatch, tmp_path, photos=2, already_matched=2
    )
    service = StubMatchServiceForCli(())
    context = SimpleNamespace(services=SimpleNamespace(match_persons=service), repositories=repositories)
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["recognize"])

    assert exit_code == 0
    assert service.commands == []
    assert "already has a recognition result" in capsys.readouterr().out


def test_main_recognize_surfaces_missing_model_pack(monkeypatch, capsys, tmp_path) -> None:
    repositories, _, _ = _match_cli_context(monkeypatch, tmp_path, photos=2)
    service = StubMatchServiceForCli((), error=main_module.ModelPackMissing("buffalo_l absent"))
    context = SimpleNamespace(services=SimpleNamespace(match_persons=service), repositories=repositories)
    monkeypatch.setattr(main_module, "bootstrap_application", lambda: context)

    exit_code = main_module.main(["recognize"])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "model pack is missing" in captured.err
    assert "download_models" in captured.err
