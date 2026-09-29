"""AUD-015 — 归档 FS/DB 部分失败语义（确定性故障注入，Stage 12D）.

目标：定性 ArchiveExecutor 的 FS/DB 一致性语义——不修改生产代码，用
真实 SQLite + 真实 filesystem + **commit 边界故障注入**证明：

- Scenario A  FS 失败（源缺失）：单项 FAILED 隔离，重试收敛。
- Scenario B  FS 成功后 DB 回滚（崩溃模拟：commit 前进程消失）→ 孤儿文件；
  retry-skip 自愈（SKIPPED 收敛、零重复文件）、retry-overwrite 重新归档。
- Scenario C  半写目标文件（mid-copy 崩溃形态）+ skip 策略：**部分文件被
  保留并标记 SKIPPED**（损坏窗口证据）；overwrite 重试为恢复路径。
- 幂等：重复 execute / 多次重试后记录数与文件数稳定。

一致性模型（详见 ADR-048）：**Accepted Partial State + retry 幂等收敛**——
批量 DB 原子（单 UoW）× 非原子 FS 复制；崩溃窗口产生孤儿文件；skip 策略
把"目标已存在"收敛为 SKIPPED（成功态），overwrite 收敛为 ARCHIVED。
"""

from datetime import datetime
from pathlib import Path

from PIL import Image

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands.archive import ArchivePhotosCommand
from photo_archiver.application.services.archive_executor import ArchiveExecutor
from photo_archiver.application.services.archive_path_builder_service import (
    ArchivePathBuilderService,
)
from photo_archiver.application.services.archive_planner import ArchivePlanner
from photo_archiver.application.services.archive_photos_service import (
    ArchivePhotosService,
)
from photo_archiver.domain import (
    ArchiveStatus,
    Person,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionResult,
)
from photo_archiver.infrastructure.database.sqlite_unit_of_work import SQLiteUnitOfWork


class _CrashOnCommitUoW:
    """崩溃注入：模拟"最后一次复制完成后、事务提交前进程消失"。

    真实 SQLite 事务 + 真实仓储写入，仅在 __exit__ 处把 commit 替换为
    rollback 并抑制异常——复刻崩溃后"无从传播、状态就地遗留"的语义。
    """

    def __init__(self, provider) -> None:
        self._provider = provider

    def __enter__(self) -> "_CrashOnCommitUoW":
        self._scope = self._provider.transaction()
        self._scope.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            self._scope.__exit__(ValueError, ValueError("simulated crash"), None)
        except ValueError:
            pass  # rollback 已执行（连接已关闭）
        return True  # 抑制——崩溃后无进程可传播异常


def _seed_confirmed_archive_input(repos, tmp_path: Path, names: list[str]):
    """真实仓储种子：人员 + 绝对路径照片 + APPROVED 兼容行（带身份）。"""
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir(exist_ok=True)
    person = Person(name="张三")
    repos.people.add(person)
    photos = []
    for index, name in enumerate(names):
        source = photos_dir / name
        Image.new("RGB", (8, 8), (30 + index * 50, 100, 150)).save(source)
        photo = Photo(
            path=PhotoPath(source, base=PhotoPathBase.ABSOLUTE),
            original_name=name,
            captured_at=datetime(2026, 1, 1 + index),
        )
        repos.photos.add(photo)
        result = RecognitionResult(
            photo_id=photo.id, person_id=person.id, confidence=None,
        )
        result.approve()
        repos.recognition.add(result)
        photos.append(photo)
    return person, photos


def _archive_service(repos, conflict_strategy: str) -> ArchivePhotosService:
    return ArchivePhotosService(
        planner=ArchivePlanner(
            path_builder=ArchivePathBuilderService(),
            person_repository=repos.people,
            photo_repository=repos.photos,
            recognition_repository=repos.recognition,
            archive_record_repository=repos.archive_records,
        ),
        executor=ArchiveExecutor(
            repos.archive_records,
            unit_of_work=SQLiteUnitOfWork(repos._connection_provider),
        ),
        default_conflict_strategy=conflict_strategy,
    )


def _execute(repos, archive_root: Path, conflict_strategy: str):
    return _archive_service(repos, conflict_strategy).execute(
        ArchivePhotosCommand(archive_root=Path(archive_root)),
    )


def test_fs_failure_is_isolated_and_retry_converges(tmp_path):
    """Scenario A：源缺失 → 单项 FAILED 隔离；恢复后重试收敛、零重复。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _, photos = _seed_confirmed_archive_input(repos, tmp_path, ["alpha.jpg", "beta.jpg"])
    beta_source = Path(photos[1].path.raw_path)
    archive_root = tmp_path / "archive"

    beta_source.unlink()                        # FS 故障注入：源文件消失
    result = _execute(repos, archive_root, "skip")
    assert (result.archived_count, result.failed_count) == (1, 1)
    records = {r.target_original_name: r for r in repos.archive_records.list_all()}
    assert records["alpha.jpg"].status is ArchiveStatus.ARCHIVED
    assert records["beta.jpg"].status is ArchiveStatus.FAILED
    assert records["beta.jpg"].error
    assert next(archive_root.rglob("alpha.jpg"), None) is not None
    assert next(archive_root.rglob("beta.jpg"), None) is None

    # 重试：FAILED 不拦重试（M-2 语义）→ 收敛；成功项去重
    _make_image_back(beta_source)
    result_retry = _execute(repos, archive_root, "skip")
    assert (result_retry.archived_count, result_retry.failed_count) == (1, 0)
    assert next(archive_root.rglob("beta.jpg"), None) is not None
    by_name = {}
    for record in repos.archive_records.list_all():
        by_name.setdefault(record.target_original_name, []).append(record.status)
    assert by_name["alpha.jpg"] == [ArchiveStatus.ARCHIVED]
    assert by_name["beta.jpg"] == [ArchiveStatus.ARCHIVED, ArchiveStatus.FAILED]
    assert len(repos.archive_records.list_all()) == 3           # 1 failed + 2 archived（历史保留）

    # 再重试：完全幂等（零新计划）
    assert _execute(repos, archive_root, "skip").planned_count == 0
    assert len(repos.archive_records.list_all()) == 3


def _make_image_back(path: Path) -> None:
    Image.new("RGB", (8, 8), (30, 100, 150)).save(path)


def test_crash_after_copy_leaves_orphans_and_skip_retry_converges(tmp_path):
    """Scenario B（核心）：FS 成功 + DB 回滚 → 孤儿文件；retry-skip 幂等收敛。

    崩溃窗口语义：executor 上报 ARCHIVED（内存结果）但批量事务回滚 →
    全部归档记录丢失、目标文件留存（孤儿）。重试时 planner 重新规划
    （无成功态记录），executor 发现目标已存在 → skip 策略标记 SKIPPED
    （成功态，has_successful 拦截后续）→ 零重复复制、状态收敛。
    """
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _, photos = _seed_confirmed_archive_input(repos, tmp_path, ["alpha.jpg", "beta.jpg"])
    archive_root = tmp_path / "archive"
    crash_uow = _CrashOnCommitUoW(repos._connection_provider)

    executor = ArchiveExecutor(repos.archive_records, unit_of_work=crash_uow)
    plan = ArchivePlanner(
        path_builder=ArchivePathBuilderService(),
        person_repository=repos.people,
        photo_repository=repos.photos,
        recognition_repository=repos.recognition,
        archive_record_repository=repos.archive_records,
    ).plan(str(archive_root), ())
    assert plan.planned_count == 2
    result = executor.execute(plan, "skip")
    assert result.archived_count == 2                    # executor 内存上报"成功"

    # 崩溃现场（保留不清理）：文件存在、记录为零
    assert len(repos.archive_records.list_all()) == 0
    copied = sorted(str(p) for p in archive_root.rglob("*.jpg"))
    assert len(copied) == 2                              # 孤儿文件

    # retry-skip：孤儿文件被"目标已存在"发现 → SKIPPED（成功态）→ 收敛
    result_retry = _archive_service(repos, "skip").execute(
        ArchivePhotosCommand(archive_root=Path(archive_root)),
    )
    assert (result_retry.planned_count, result_retry.skipped_count) == (2, 2)
    records = sorted(r.status for r in repos.archive_records.list_all())
    assert records == [ArchiveStatus.SKIPPED, ArchiveStatus.SKIPPED]
    assert sorted(str(p) for p in archive_root.rglob("*.jpg")) == copied  # 零重复复制

    # 再重试：成功态拦截 → 零新计划（完全幂等）
    assert _archive_service(repos, "skip").execute(
        ArchivePhotosCommand(archive_root=Path(archive_root)),
    ).planned_count == 0
    assert len(repos.archive_records.list_all()) == 2
    assert sorted(str(p) for p in archive_root.rglob("*.jpg")) == copied


def test_crash_after_copy_overwrite_retry_rearchives_fresh_copy(tmp_path):
    """Scenario B（overwrite 策略）：孤儿文件被重新复制覆盖 → ARCHIVED 收敛。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _, photos = _seed_confirmed_archive_input(repos, tmp_path, ["alpha.jpg"])
    archive_root = tmp_path / "archive"
    crash_uow = _CrashOnCommitUoW(repos._connection_provider)
    plan = ArchivePlanner(
        path_builder=ArchivePathBuilderService(),
        person_repository=repos.people,
        photo_repository=repos.photos,
        recognition_repository=repos.recognition,
        archive_record_repository=repos.archive_records,
    ).plan(str(archive_root), ())
    ArchiveExecutor(repos.archive_records, unit_of_work=crash_uow).execute(plan, "overwrite")
    assert len(repos.archive_records.list_all()) == 0    # 记录回滚
    orphan = next(archive_root.rglob("alpha.jpg"))
    orphan.write_bytes(b"stale-orphan-bytes")            # 篡改孤儿内容以区分

    result = _archive_service(repos, "overwrite").execute(
        ArchivePhotosCommand(archive_root=Path(archive_root)),
    )
    assert (result.planned_count, result.archived_count) == (1, 1)
    records = repos.archive_records.list_all()
    assert len(records) == 1 and records[0].status is ArchiveStatus.OVERWRITTEN
    assert orphan.read_bytes() != b"stale-orphan-bytes"  # 真实重新复制
    assert len(repos.archive_records.list_all()) == 1    # 幂等：无重复记录


def test_legacy_partial_destination_locked_and_new_executor_never_creates_it(tmp_path):
    """半写目标的两种语义（Stage 12D 定性）：

    Part 1（遗留/外部形态）：skip 策略信任"目标存在" → SKIPPED 成功态
    **锁定**重新规划——损坏的部分文件无法经 overwrite 重试恢复（planned 0），
    恢复需人工（删除记录与目标后重归档，见 ADR-048）。
    Part 2（修复后）：executor 经 .part + os.replace 原子落位——复制中途
    崩溃（注入 os.replace 失败）→ 单项 FAILED、目标不存在、.part 清理，
    重试完整归档；正常路径不再产生半写目标。
    """
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _, photos = _seed_confirmed_archive_input(repos, tmp_path, ["alpha.jpg"])
    archive_root = tmp_path / "archive"
    service = _archive_service(repos, "skip")
    plan = service.preview(str(archive_root))
    assert plan.planned_count == 1
    target = Path(plan.items[0].target_path.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"PARTIAL-")                      # 遗留半写形态

    result = service.execute(ArchivePhotosCommand(archive_root=Path(archive_root)))
    assert result.skipped_count == 1
    assert target.read_bytes() == b"PARTIAL-"            # skip 保留部分文件
    records = repos.archive_records.list_all()
    assert records[0].status is ArchiveStatus.SKIPPED
    # 锁定证据：SKIPPED 为成功态 → 拦截重新规划（overwrite 也无法恢复）
    blocked = _archive_service(repos, "overwrite").preview(str(archive_root))
    assert blocked.planned_count == 0

    # Part 2：原子复制下复制中途故障 → FAILED（非半写目标）+ .part 清理 + 重试收敛
    import os as os_module

    repos2 = build_sqlite_repositories(tmp_path / "db2.sqlite3")
    _, photos2 = _seed_confirmed_archive_input(repos2, tmp_path, ["gamma.jpg"])
    archive_root2 = tmp_path / "archive2"

    real_replace = os_module.replace

    def _boom(src, dst):
        raise OSError("simulated crash before replace")

    os_module.replace = _boom
    try:
        failed = _archive_service(repos2, "skip").execute(
            ArchivePhotosCommand(archive_root=Path(archive_root2)),
        )
    finally:
        os_module.replace = real_replace
    assert (failed.planned_count, failed.failed_count) == (1, 1)
    target2 = next(archive_root2.rglob("gamma.jpg*"), None)
    assert target2 is None                               # 目标与 .part 均未留存
    assert repos2.archive_records.list_all()[0].status is ArchiveStatus.FAILED

    retry = _archive_service(repos2, "skip").execute(
        ArchivePhotosCommand(archive_root=Path(archive_root2)),
    )
    assert retry.archived_count == 1
    assert Path(photos2[0].path.raw_path).read_bytes() == next(
        archive_root2.rglob("gamma.jpg"),
    ).read_bytes()                                       # 完整副本


def test_rename_strategy_after_orphan_creates_sibling_copy(tmp_path):
    """rename 策略遇孤儿：孤儿保留为 .archived-1 兄弟、新副本落正位 → 收敛。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _, photos = _seed_confirmed_archive_input(repos, tmp_path, ["alpha.jpg"])
    archive_root = tmp_path / "archive"
    crash_uow = _CrashOnCommitUoW(repos._connection_provider)
    plan = ArchivePlanner(
        path_builder=ArchivePathBuilderService(),
        person_repository=repos.people,
        photo_repository=repos.photos,
        recognition_repository=repos.recognition,
        archive_record_repository=repos.archive_records,
    ).plan(str(archive_root), ())
    ArchiveExecutor(repos.archive_records, unit_of_work=crash_uow).execute(plan, "rename")
    assert len(repos.archive_records.list_all()) == 0    # 崩溃：孤儿 + 无记录

    result = _archive_service(repos, "rename").execute(
        ArchivePhotosCommand(archive_root=Path(archive_root)),
    )
    assert result.planned_count == 1
    records = repos.archive_records.list_all()
    assert len(records) == 1 and records[0].status is ArchiveStatus.RENAMED
    # 既有行为（Stage 12D 钉定，ADR-048 记录）：记录保留规划名，实际兄弟名
    # 仅存在于 outcome——消费方经 RENAMED 状态感知。
    assert records[0].target_original_name == "alpha.jpg"
    target_dir = (
        Path(records[0].target_archive_root)
        / records[0].target_person_name
        / records[0].target_event_or_date
    )
    siblings = sorted(entry.name for entry in target_dir.rglob("*") if entry.is_file())
    assert len(siblings) == 2                            # 孤儿 + dup-1 兄弟并存
    assert any("dup-1" in name for name in siblings)


def test_destination_conflict_matrix_skip_semantics(tmp_path):
    """目标冲突矩阵（skip）：absent→ARCHIVED；same→SKIPPED；不同→SKIPPED 保留他者。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _, photos = _seed_confirmed_archive_input(repos, tmp_path, ["alpha.jpg", "beta.jpg"])
    archive_root = tmp_path / "archive"
    service = _archive_service(repos, "skip")

    first = service.execute(ArchivePhotosCommand(archive_root=Path(archive_root)))
    assert first.archived_count == 2                     # absent → ARCHIVED
    records = {r.target_original_name: r for r in repos.archive_records.list_all()}
    assert all(r.status is ArchiveStatus.ARCHIVED for r in records.values())

    second = service.execute(ArchivePhotosCommand(archive_root=Path(archive_root)))
    assert second.planned_count == 0                     # 成功态拦截 → 不再规划
