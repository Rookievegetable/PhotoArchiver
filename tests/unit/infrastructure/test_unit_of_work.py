"""Tests for SQLite UnitOfWork transaction boundaries and thread isolation."""

import threading
from pathlib import Path

import pytest

from photo_archiver.domain import Folder, PhotoPath, PhotoPathBase
from photo_archiver.infrastructure import SQLiteConnectionProvider, SQLiteUnitOfWork
from photo_archiver.infrastructure.database.sqlite_folder_repository import SQLiteFolderRepository


def _make_folder(path: str) -> Folder:
    return Folder(
        path=PhotoPath(raw_path=Path(path), base=PhotoPathBase.ABSOLUTE),
        display_name="test",
    )


@pytest.fixture()
def provider(tmp_path: Path) -> SQLiteConnectionProvider:
    """Return an initialized SQLite connection provider backed by a temp file."""
    provider = SQLiteConnectionProvider(tmp_path / "uow.db")
    provider.initialize_schema()
    return provider


def test_unit_of_work_commits_on_normal_exit(provider: SQLiteConnectionProvider) -> None:
    """Folder added within scope should be visible after commit."""
    repo = SQLiteFolderRepository(provider)
    uow = SQLiteUnitOfWork(provider)
    with uow:
        folder = _make_folder("C:/commit")
        repo.add(folder)
    assert repo.find_by_id(folder.id) is not None


def test_unit_of_work_rolls_back_on_exception(provider: SQLiteConnectionProvider) -> None:
    """Folder added within scope should not persist when scope raises."""
    repo = SQLiteFolderRepository(provider)
    uow = SQLiteUnitOfWork(provider)
    folder = _make_folder("C:/rollback")
    with pytest.raises(RuntimeError, match="simulated"):
        with uow:
            repo.add(folder)
            raise RuntimeError("simulated mid-scan failure")
    assert repo.find_by_id(folder.id) is None


def test_unit_of_work_supports_concurrent_threads(provider: SQLiteConnectionProvider) -> None:
    """Two threads should each open independent transactions without cross-talk."""
    repo = SQLiteFolderRepository(provider)
    uow = SQLiteUnitOfWork(provider)
    results: dict[str, str] = {}

    def worker(name: str, path: str) -> None:
        try:
            with uow:
                folder = _make_folder(path)
                repo.add(folder)
                results[name] = "ok"
        except Exception as exc:
            results[name] = f"fail: {exc}"

    t1 = threading.Thread(target=worker, args=("T1", "C:/t1"))
    t2 = threading.Thread(target=worker, args=("T2", "C:/t2"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results == {"T1": "ok", "T2": "ok"}
