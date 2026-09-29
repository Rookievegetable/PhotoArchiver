"""AUD-016 / AUD-018 命令契约与数据模型契约测试（Stage 13C-B）.

覆盖：
- AUD-016：服务层冲突策略边界（合法三值 + 非法值/空串/大小写/None 语义）、
  执行器 fail-closed 守卫（未知策略 → 单项 FAILED，不再静默等同覆盖）、
  application 与 settings 两侧合法值集合的一致性（防漂移）。
- AUD-018-B：``RecognitionResult`` 构造期状态类型校验（域枚举是唯一状态机——
  ``recognition_results`` 表无 DB 层 CHECK，见 ADR-052）。

三策略的既有行为（skip/overwrite/rename）由既有套件保证，本文件只补契约面。
"""

from uuid import uuid4

import pytest

from photo_archiver.application.commands.archive import ArchivePhotosCommand
from photo_archiver.application.services.archive_photos_service import (
    VALID_ARCHIVE_CONFLICT_STRATEGIES as APP_VALID_STRATEGIES,
)
from photo_archiver.application.services.archive_executor import ArchiveExecutor
from photo_archiver.domain import (
    ArchiveStatus,
    MatchStatus,
    RecognitionResult,
    ValidationError,
)
from photo_archiver.infrastructure.config.settings import (
    VALID_ARCHIVE_CONFLICT_STRATEGIES as SETTINGS_VALID_STRATEGIES,
)


class _RecordingArchiveRecordRepository:
    """Minimal in-memory recorder for executor contract tests."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, record) -> None:  # noqa: ANN001
        self.added.append(record)


class _NoopFileStore:
    """Records the strategy-driven calls; never touches a real filesystem."""

    def path_exists(self, path) -> bool:  # noqa: ANN001
        return bool(getattr(self, "_exists", False))

    def ensure_parent_directory(self, target) -> None:  # noqa: ANN001
        pass

    def verify_target_containment(self, archive_root, target):  # noqa: ANN001
        return None

    def copy_atomically(self, source, target) -> None:  # noqa: ANN001
        self.copied = getattr(self, "copied", [])
        self.copied.append((str(source), str(target)))

    def find_available_sibling(self, target, conflict_suffix):  # noqa: ANN001
        return target.with_name(f"{target.stem}.{conflict_suffix}-1{target.suffix}")


def _plan_item(tmp_path):  # noqa: ANN001, ANN202
    from photo_archiver.application.dtos.archive import ArchivePlan, ArchivePlanItem
    from photo_archiver.domain.value_objects import ArchivePath

    source = tmp_path / "src.jpg"
    source.write_bytes(b"payload")
    target = ArchivePath(
        archive_root=str(tmp_path / "archive"),
        person_name="Alice",
        event_or_date="2026-01-01",
        original_name="dst.jpg",
    )
    plan_item = ArchivePlanItem(
        photo_id=uuid4(),
        source_path=source,
        target_path=target,
        person_id=uuid4(),
        person_name="Alice",
    )
    return ArchivePlan(items=(plan_item,))


# ── AUD-016: conflict strategy contract ────────────────────────────────────


def test_legal_strategy_set_is_the_documented_three():
    assert set(APP_VALID_STRATEGIES) == {"skip", "overwrite", "rename"}


def test_settings_and_application_legal_sets_stay_in_sync():
    """两侧常量分属不同层（application 不依赖 infrastructure），用测试钉死防漂移。"""
    assert set(SETTINGS_VALID_STRATEGIES) == set(APP_VALID_STRATEGIES)


def test_command_accepts_none_as_use_default_signal():
    """``None`` 是类型契约内的"未指定"信号，不是非法值。"""
    assert ArchivePhotosCommand(
        archive_root="unused", conflict_strategy=None,
    ).conflict_strategy is None


@pytest.mark.parametrize("illegal", ["merge", "", "  ", "SKIP-MIXED", "skip overwrite"])
def test_illegal_strategy_rejected_at_service_boundary(illegal: str):
    """服务层 _resolve_conflict_strategy 是权威校验点（既有实现，AUD-016 事实纠正）。"""
    from photo_archiver.application.services.archive_photos_service import (
        ArchivePhotosService,
    )

    service = ArchivePhotosService(planner=None, executor=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        service._resolve_conflict_strategy(illegal)  # noqa: SLF001 - contract under test


def test_service_normalizes_case_and_padding():
    from photo_archiver.application.services.archive_photos_service import (
        ArchivePhotosService,
    )

    service = ArchivePhotosService(planner=None, executor=None)  # type: ignore[arg-type]
    assert service._resolve_conflict_strategy("  OVERWRITE ") == "overwrite"  # noqa: SLF001


def test_executor_fails_closed_on_unknown_strategy_instead_of_silent_copy(tmp_path):
    """AUD-016 防御纵深：未知策略 → 单项 FAILED，而非落入"直接复制"（等同覆盖）。"""
    store = _NoopFileStore()
    store._exists = True  # 目标已存在——旧行为会静默覆盖
    executor = ArchiveExecutor(_RecordingArchiveRecordRepository(), store)  # type: ignore[arg-type]
    result = executor.execute(_plan_item(tmp_path), conflict_strategy="merge")

    assert result.failed_count == 1
    assert not hasattr(store, "copied")
    outcome = result.outcomes[0]
    assert outcome.status is ArchiveStatus.FAILED
    assert "unsupported conflict strategy" in (outcome.error or "")
    assert executor._archive_record_repository.added[-1].status is ArchiveStatus.FAILED  # noqa: SLF001


# ── AUD-018-B: recognition result status is domain-enum only ────────────────


def test_recognition_result_rejects_non_enum_status():
    """构造期类型校验：dataclass 不强制类型，缺此校验非法状态可直达 DB。"""
    with pytest.raises(ValidationError, match="MatchStatus"):
        RecognitionResult(photo_id=uuid4(), confidence=None, status="approved")  # type: ignore[arg-type]


def test_recognition_result_accepts_enum_statuses():
    for status in MatchStatus:
        assert RecognitionResult(photo_id=uuid4(), confidence=None, status=status).status is status
