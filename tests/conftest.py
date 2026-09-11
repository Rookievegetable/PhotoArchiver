"""Shared pytest fixtures (Phase F F-5 / 体检 T-1：收敛真实 SQLite 装配重复).

约十二个测试模块各自重复 ``AppSettings(database_url=...) →
ensure_runtime_directories() → bootstrap_application(settings)`` 装配。本
conftest 将该装配收敛为一个工厂 fixture，测试文化不变——仍是文件级真实
SQLite（零 ``:memory:``），每个测试独立 tmp_path 库文件。
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from photo_archiver.app import ApplicationContext, bootstrap_application
from photo_archiver.infrastructure.config import AppSettings


@pytest.fixture
def make_sqlite_context(tmp_path: Path) -> Callable[..., ApplicationContext]:
    """Factory fixture: bootstrap a real app context over a real tmp SQLite file.

    The returned callable accepts a ``db_name`` (default
    ``photo_archiver_test.db``; distinct names isolate multiple contexts inside
    one test) plus any further ``AppSettings`` keyword overrides.
    """

    def _make(db_name: str = "photo_archiver_test.db", **settings_kwargs) -> ApplicationContext:
        settings = AppSettings(
            database_url=f"sqlite:///{tmp_path / db_name}", **settings_kwargs
        )
        settings.ensure_runtime_directories()
        return bootstrap_application(settings)

    return _make
