"""Historical people backfill service — Stage F（执行计划 Stage F 第 1 项）.

owner 批准执行计划 Stage F："历史人员补建导入批次（source_batch_id 回填 +
roster_order 按既有创建顺序）——迁移或一次性脚本 + 失败清单。"

语义（规格 + Stage A 预留：Person 文档明确 "None for legacy people until
stage F backfills it"）：

- **输入范围**：仅 ``source_batch_id IS NULL`` 的历史人员（Stage A 之前
  入库、或人员页手工新增的存量人员）。
- **回填动作**：创建一个标记为 ``source_type="backfill"`` 的历史导入批次
  （status=confirmed），将全部存量人员链接到该批次；**已有 roster_order
  的人员不覆盖顺序**，无顺序人员按创建时间（created_at, id）接在现有名单
  最大序号之后。
- **幂等**：无存量人员时为 no-op（不创建批次）；重复执行不产生重复归属
  或重复顺序（COALESCE 保序）。
- **不覆盖人工决策**：已有 source_batch_id / roster_order 一概不动。
- **可追溯**：批次行 + 人员行（source_batch_id）+ 失败清单（逐人更新
  失败原因）；批次与人员更新包在同一 UnitOfWork 内原子提交。
- **不触碰 Stage D/E 数据**：聚类、指派、样本、兼容层零改动。

历史数据（存量人员）与 Stage E 新生成数据（确认映射）由此天然区分：
回填批次是唯一的 ``source_type="backfill"`` 批次。
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from loguru import logger

from photo_archiver.domain import ImportBatch
from photo_archiver.domain.repositories.import_batch_repository import (
    ImportBatchRepository,
)
from photo_archiver.domain.repositories.person_repository import PersonRepository

BACKFILL_SOURCE_TYPE = "backfill"
BACKFILL_BATCH_LABEL = "历史人员回填"


@dataclass(frozen=True, slots=True)
class BackfillHistoricalPeopleCommand:
    """Request one historical-people backfill run."""

    batch_label: str = BACKFILL_BATCH_LABEL


@dataclass(slots=True)
class BackfillHistoricalPeopleResult:
    """Outcome of one backfill run（含逐人失败清单）。"""

    batch_id: UUID | None
    backfilled_count: int = 0
    skipped_already_linked: int = 0
    failures: tuple[str, ...] = field(default_factory=tuple)


class BackfillHistoricalPeopleService:
    """Link legacy people to a synthetic historical import batch."""

    def __init__(
        self,
        person_repository: PersonRepository,
        import_batch_repository: ImportBatchRepository,
        unit_of_work=None,
    ) -> None:
        self._person_repository = person_repository
        self._import_batch_repository = import_batch_repository
        self._unit_of_work = unit_of_work

    def execute(
        self, command: BackfillHistoricalPeopleCommand | None = None,
    ) -> BackfillHistoricalPeopleResult:
        """Run the idempotent backfill; returns counts + failure list."""
        command = command or BackfillHistoricalPeopleCommand()
        people = self._person_repository.list_all()
        legacy = [
            person for person in people if person.source_batch_id is None
        ]
        skipped = len(people) - len(legacy)
        if not legacy:
            logger.info(
                "BackfillHistoricalPeopleService: no legacy people — no-op",
            )
            return BackfillHistoricalPeopleResult(
                batch_id=None, skipped_already_linked=skipped,
            )

        # roster_order 只补无序者：接在现有名单最大序号之后，按创建顺序。
        max_order = self._person_repository.max_roster_order() or 0
        ordered_legacy = sorted(
            legacy,
            key=lambda person: (person.created_at or person.id, str(person.id)),
        )
        entries: list[tuple[UUID, int | None]] = []
        next_order = max_order + 1
        for person in ordered_legacy:
            if person.id is None:  # pragma: no cover - 实体恒生成 id
                continue
            entries.append((
                person.id,
                None if person.roster_order is not None else next_order,
            ))
            if person.roster_order is None:
                next_order += 1

        batch = ImportBatch(
            file_name=command.batch_label,
            file_hash=f"backfill:{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            source_type=BACKFILL_SOURCE_TYPE,
            status="confirmed",
        )
        failures: list[str] = []
        backfilled = 0

        def _run_batch() -> None:
            nonlocal backfilled
            self._import_batch_repository.add_batch(batch)
            assert batch.id is not None
            for person_id, roster_order in entries:
                updated = self._person_repository.apply_historical_backfill(
                    person_id, batch.id, roster_order,
                )
                if updated == 1:
                    backfilled += 1
                else:
                    failures.append(
                        f"人员 {person_id} 回填失败（行不存在或并发删除）"
                    )

        if self._unit_of_work is not None:
            with self._unit_of_work:
                _run_batch()
        else:
            _run_batch()

        logger.info(
            "BackfillHistoricalPeopleService: batch {} backfilled {} people "
            "({} failures, {} already linked)",
            batch.id, backfilled, len(failures), skipped,
        )
        return BackfillHistoricalPeopleResult(
            batch_id=batch.id,
            backfilled_count=backfilled,
            skipped_already_linked=skipped,
            failures=tuple(failures),
        )
