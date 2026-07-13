"""Tests for the top-level application entrypoint."""

from pathlib import Path
from types import SimpleNamespace

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