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

    def execute(self, exporter, output_path, scope, criteria=None):
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
