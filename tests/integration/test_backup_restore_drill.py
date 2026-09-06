"""N2 备份恢复演练（B7 机械部分自动化等价物）.

按启动失败弹框指引的恢复路径走一遍真实机制：

    正常启动建库 + 写入标记数据 → ``VACUUM INTO`` 快照（生产 backup_database
    路径）→ 主库写坏（垃圾字节）→ bootstrap 拒绝（CorruptedDatabaseError，
    不重建/不换库）→ **从 backups 快照复制恢复** → 再次 bootstrap 成功且
    标记数据完好。

弹框文案的"对人是否清晰可照做"仍是人工项；本用例锁定其机械正确性——
指引描述的恢复步骤在真实库上确实可行。
"""

import gc
import shutil
from pathlib import Path

import pytest

from photo_archiver.app import bootstrap_application
from photo_archiver.domain import Person
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.infrastructure.database.backup import (
    BACKUP_DIRECTORY_NAME,
    backup_database,
)
from photo_archiver.infrastructure.database.integrity import CorruptedDatabaseError

_MARKER_NAME = "恢复演练标记"
_MARKER_IDENTITY = "R0001"


def test_restore_from_backup_snapshot_recovers_library(tmp_path: Path) -> None:
    """坏库被拒 → 快照复制恢复 → bootstrap 成功且标记数据完好。"""
    db_path = tmp_path / "drill" / "data.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    settings = AppSettings(database_url=f"sqlite:///{db_path}")
    settings.ensure_runtime_directories()

    # 1) 正常启动建库并写入标记数据。
    context = bootstrap_application(settings)
    context.repositories.people.add(
        Person(name=_MARKER_NAME, identity=_MARKER_IDENTITY, department="演练部")
    )
    assert context.repositories.people.find_by_identity(_MARKER_IDENTITY) is not None

    # 2) 生产备份路径生成快照。
    backup_database(db_path)
    backups = sorted((db_path.parent / BACKUP_DIRECTORY_NAME).glob("*.db"))
    assert backups, "backup_database must create a snapshot"

    # 3) 主库写坏（垃圾字节）。前提：所有残留连接与 WAL sidecar 必须先清零
    #    ——有 -wal 在场时 SQLite 会用 wal 重放"救活"垃圾主库，损坏门形同虚设。
    #    按次连接依赖引用计数关闭，个别句柄经 gc 才释放：枚举关闭 + 断言清场。
    import sqlite3

    gc.collect()
    for obj in gc.get_objects():
        if isinstance(obj, sqlite3.Connection):
            obj.close()
    for sidecar in (tmp_path / "drill" / "data.db-wal", tmp_path / "drill" / "data.db-shm"):
        sidecar.unlink(missing_ok=True)
    assert not (tmp_path / "drill" / "data.db-wal").exists()
    db_path.write_bytes(b"not a database at all\n" * 8)

    # 4) 损坏门快速失败：不重建、不换库。
    with pytest.raises(CorruptedDatabaseError):
        bootstrap_application(settings)

    # 5) 按指引从快照复制恢复，再次启动。
    shutil.copyfile(backups[-1], db_path)
    restored_context = bootstrap_application(settings)
    restored = restored_context.repositories.people.find_by_identity(_MARKER_IDENTITY)
    assert restored is not None
    assert restored.name == _MARKER_NAME
    assert restored.department == "演练部"
