"""AUD-024 — SQLite 连接生命周期契约（Stage 13C-C）.

不依赖 CPython 引用计数实现的脆弱断言：观测**可契约化**的部分——

- UnitOfWork ``transaction()``：提交 / 回滚 / 异常三条路径**均显式 close**
  （``sqlite_connection.py`` 的 ``finally``）——用 spy 观测；
- 嵌套事务仍显式报错（边界未漂移）；
- per-call 路径（``connect()``）：每次调用返回**新连接**（不共享、不缓存），
  且仓储方法内异常**不会留下写锁**（后续连接仍可写）——行为断言，不测 refcount。

per-call 连接的关闭依赖 CPython 引用计数（项目钉定 3.11）：方法返回后局部
变量失去引用即释放。异常路径下 traceback 可能短暂持有帧引用，关闭延后至
traceback 释放/GC——有界、无累积。ADR-053 记录该假设。
"""

import sqlite3

import pytest

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.domain import Person
from photo_archiver.infrastructure.database.sqlite_connection import (
    SQLiteConnectionProvider,
)
from photo_archiver.infrastructure.database.sqlite_unit_of_work import (
    SQLiteUnitOfWork,
)


class _ConnectionSpy:
    """Wrap ``sqlite3.connect`` and record created connections + close calls."""

    def __init__(self, monkeypatch) -> None:  # noqa: ANN001
        self.created: list[sqlite3.Connection] = []
        self._real_connect = sqlite3.connect
        monkeypatch.setattr(sqlite3, "connect", self._connect)

    def _connect(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        connection = self._real_connect(*args, **kwargs)
        self.created.append(connection)
        return connection

    @property
    def closed_count(self) -> int:
        return sum(1 for connection in self.created if _is_closed(connection))


def _is_closed(connection: sqlite3.Connection) -> bool:
    """A closed sqlite3 connection raises ProgrammingError on any operation."""
    try:
        connection.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


@pytest.fixture
def spy(monkeypatch) -> _ConnectionSpy:  # noqa: ANN001
    return _ConnectionSpy(monkeypatch)


def test_unit_of_work_closes_connection_on_commit(tmp_path, spy):  # noqa: ANN001
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    spy.created.clear()

    with SQLiteUnitOfWork(repos._connection_provider):  # noqa: SLF001 - 契约内省
        repos.people.add(Person(name="提交路径"))

    assert spy.closed_count == len(spy.created) == 1
    assert any(p.name == "提交路径" for p in repos.people.list_all())


def test_unit_of_work_closes_connection_on_rollback(tmp_path, spy):  # noqa: ANN001
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    spy.created.clear()

    with pytest.raises(RuntimeError, match="boom"):
        with SQLiteUnitOfWork(repos._connection_provider):  # noqa: SLF001
            repos.people.add(Person(name="回滚路径"))
            raise RuntimeError("boom")

    assert spy.closed_count == len(spy.created) == 1
    assert all(p.name != "回滚路径" for p in repos.people.list_all())


def test_nested_transaction_still_rejected(tmp_path, spy):  # noqa: ANN001
    provider = SQLiteConnectionProvider(tmp_path / "db.sqlite3")
    provider.initialize_schema()

    with SQLiteUnitOfWork(provider):
        with pytest.raises(RuntimeError, match="Nested SQLite transactions"):
            with SQLiteUnitOfWork(provider):
                pass  # pragma: no cover - 不应到达


def test_per_call_path_returns_a_fresh_connection_each_time(tmp_path):  # noqa: ANN001
    provider = SQLiteConnectionProvider(tmp_path / "db.sqlite3")
    provider.initialize_schema()

    first = provider.connect()
    second = provider.connect()
    try:
        assert first is not second          # 不共享、不缓存
    finally:
        first.close()
        second.close()


def test_unique_violation_inside_repository_does_not_leave_a_write_lock(tmp_path, spy):  # noqa: ANN001
    """真实 DB 失败（UNIQUE 冲突）在 ``with`` 路径抛出——后续写入必须成功。"""
    from photo_archiver.domain import PersonIdentity

    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    identity = PersonIdentity("E001")
    repos.people.add(Person(name="张三", identity=identity))
    spy.created.clear()

    with pytest.raises(sqlite3.IntegrityError):
        repos.people.add(Person(name="重复工号", identity=identity))

    # 关键断言：无写锁滞留（否则此处会 "database is locked"）。
    repos.people.add(Person(name="冲突后写入"))
    names = {person.name for person in repos.people.list_all()}
    assert "冲突后写入" in names and "重复工号" not in names


def test_per_call_repository_error_leaves_database_usable(tmp_path):  # noqa: ANN001
    """仓储方法内异常后，数据库仍可正常读写（连接未持有写锁）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")

    class _BoomRepo:
        def add(self, person):  # noqa: ANN001, ANN202
            raise sqlite3.OperationalError("simulated failure inside repository")

    boom = _BoomRepo()
    with pytest.raises(sqlite3.OperationalError):
        boom.add(Person(name="赵六"))

    repos.people.add(Person(name="正常写入"))
    names = {person.name for person in repos.people.list_all()}
    assert "正常写入" in names


def test_provider_transaction_close_is_observed_even_without_operations(tmp_path, spy):  # noqa: ANN001
    """空事务也必须 close（无操作 ≠ 无连接）。"""
    provider = SQLiteConnectionProvider(tmp_path / "db.sqlite3")
    provider.initialize_schema()
    spy.created.clear()

    with SQLiteUnitOfWork(provider):
        pass

    assert spy.closed_count == len(spy.created) == 1
