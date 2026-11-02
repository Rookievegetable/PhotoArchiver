"""Manual per-photo attribution from the photo library（追加轮 29，Owner）.

照片库选择**只有单个人脸的未匹配照片**，输入指定人员名并选择批次（新建
或并入已导入批次）→ 照片归到对应人名下：

- 批次解析：已导入批次按 id 取用；新建批次以 ``confirmed`` 态直建（其唯
  一成员由用户显式指定，无 draft 生命周期）。
- 人员解析：批次内同名人员**复用**（归到对应人名下）；否则新建并挂靠
  该批次（``source_batch_id``）。
- 归属链：照片若无识别结果行则合成 PENDING 行（``confidence=None``＝无
  相似度证据的人工指派语义），随后走 :meth:`ReviewRecognitionService.approve`
  的身份决策唯一链（S1-F：Assignment(source='review', confirmed) → 投影）
  ——照片变为「已匹配·待审核名单上消失」，归档面按 approved 消费。

单事务边界：合成行落库与身份批准分两次提交（身份决策服务自带事务，
SQLite 不支持嵌套）——批准失败的残留 PENDING 行如实披露（审核中心可见
可拒绝）。单脸校验按**归属运行**口径（照片被重复扫描时旧运行观测不计）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from photo_archiver.domain.entities.import_batch import (
    BATCH_STATUS_CONFIRMED,
    ImportBatch,
)
from photo_archiver.domain.entities.person import Person
from photo_archiver.domain.entities.recognition import (
    MatchStatus,
    RecognitionResult,
)
from photo_archiver.domain.exceptions import ValidationError

if TYPE_CHECKING:
    from uuid import UUID


@dataclass(frozen=True, slots=True)
class ManualAttributionCommand:
    """指定人员归档命令（追加轮 29）.

    ``existing_batch_id`` 与 ``new_batch_name`` 二选一（同时给出＝校验错误）。
    """

    photo_ids: tuple[UUID, ...]
    person_name: str
    existing_batch_id: UUID | None = None
    new_batch_name: str | None = None


@dataclass(frozen=True, slots=True)
class PhotoAttributionOutcome:
    """单张照片的归档结果（诚实逐项）。"""

    photo_id: UUID
    ok: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ManualAttributionResult:
    """指定人员归档结果汇总。"""

    assigned: int
    outcomes: tuple[PhotoAttributionOutcome, ...]
    person_id: UUID | None
    person_name: str
    batch_id: UUID | None
    batch_name: str


class ManualAttributionService:
    """Attribute single-face unmatched photos to a named person in a batch."""

    def __init__(
        self,
        photo_repository,
        observation_repository,
        recognition_repository,
        review_service,
        person_repository,
        import_batch_repository,
        run_repository=None,
    ) -> None:
        """Initialize with its ports.

        Args:
            photo_repository: 照片存在性校验。
            observation_repository: 单脸校验的观测读取。
            recognition_repository: 识别结果读取与合成 PENDING 行落库。
            review_service: 身份批准唯一链（S1-F 决策服务经其触达）。
            person_repository: 人员解析（批次内同名复用/新建）。
            import_batch_repository: 批次解析（已导入取用/新建直建 confirmed）。
            run_repository: 单脸校验的归属运行判定（未注入时回退全部观测计数）。
        """
        self._photos = photo_repository
        self._observations = observation_repository
        self._recognition = recognition_repository
        self._review = review_service
        self._people = person_repository
        self._batches = import_batch_repository
        self._runs = run_repository

    # ── 校验 ──────────────────────────────────────────────────────────

    def _owning_face_counts(self, photo_ids) -> dict:
        """photo_id → 归属运行（拥有其观测的最新运行）的人脸数.

        追加轮 31：走免反序列化聚合读口（不加载 512 维嵌入）——照片墙选
        区变化可挂此校验；runs 按 created_at 降序，首见即归属（与特征数
        据集的 latest-wins 同口径），重复扫描照片的旧运行观测不计。
        """
        counts: dict = {}
        for run_id, photo_id, count in (
            self._observations.count_faces_by_run_and_photo(tuple(photo_ids))
        ):
            counts.setdefault(photo_id, {})[run_id] = count
        owner: dict = {}
        if self._runs is not None:
            for run in self._runs.list_runs():
                if run.id is None:  # pragma: no cover - 实体恒生成 id
                    continue
                for photo_id, per_run in counts.items():
                    if photo_id in owner:
                        continue
                    if run.id in per_run:
                        owner[photo_id] = per_run[run.id]
        for photo_id, per_run in counts.items():
            if photo_id not in owner:
                # 未注入 run 仓储时回退合计（测试路径；重复扫描按保守拒绝）。
                owner[photo_id] = sum(per_run.values())
        for photo_id in photo_ids:
            owner.setdefault(photo_id, 0)
        return owner

    def _validate_photo(self, photo_id, owner_map: dict) -> str:
        """返回空串＝可归档；否则返回拒绝原因（预演与执行同口径）."""
        if self._photos.find_by_id(photo_id) is None:
            return "照片不存在（可能已被删除）"
        face_count = owner_map.get(photo_id, 0)
        if not face_count:
            return "照片没有人脸观测（无法指定人员）"
        if face_count > 1:
            return (
                f"照片包含 {face_count} 张人脸——只支持单人脸照片的指定归档"
            )
        first = self._recognition.list_first_by_photo_ids([photo_id]).get(photo_id)
        if first is not None:
            if first.person_id is not None:
                return "照片已有人员归属"
            if first.status is MatchStatus.APPROVED:
                return "照片已通过审核"
            if first.status is MatchStatus.REJECTED:
                return "照片已被拒绝（拒绝态不可指定归档）"
        return ""

    def preview(self, photo_ids) -> dict:
        """逐张校验（无副作用）——返回 ``{photo_id: 拒绝原因或""}``."""
        owner_map = self._owning_face_counts(photo_ids)
        return {
            photo_id: self._validate_photo(photo_id, owner_map)
            for photo_id in photo_ids
        }

    def list_batch_person_names(self, batch_id) -> tuple[str, ...]:
        """批次内人员姓名（追加轮 30：并入已导入批次时的关联搜索数据源）.

        按名单顺序（``roster_order``，缺省排后）——与人员页/建议顺序同口径。
        """
        people = [
            person for person in self._people.list_all()
            if person.source_batch_id is not None
            and person.source_batch_id == batch_id
        ]
        people.sort(key=lambda person: (
            person.roster_order is None,
            person.roster_order if person.roster_order is not None else 0,
            person.name,
        ))
        return tuple(person.name for person in people)

    # ── 执行 ──────────────────────────────────────────────────────────

    def _resolve_batch(self, command: ManualAttributionCommand) -> ImportBatch:
        if command.existing_batch_id is not None:
            batch = self._batches.get_batch(command.existing_batch_id)
            if batch is None:
                raise ValidationError("所选批次不存在（可能已被删除）")
            return batch
        assert command.new_batch_name  # execute 入口已校验
        batch = ImportBatch(
            file_name=command.new_batch_name.strip(),
            file_hash=f"manual:{uuid4()}",
            source_type="manual",
            status=BATCH_STATUS_CONFIRMED,
        )
        self._batches.add_batch(batch)
        return batch

    def _resolve_person(self, person_name: str, batch: ImportBatch) -> Person:
        """批次内同名人员复用（归到对应人名下）；否则新建并挂靠批次。"""
        wanted = person_name.strip()
        for person in self._people.list_all():
            if (
                person.name == wanted
                and person.source_batch_id is not None
                and batch.id is not None
                and person.source_batch_id == batch.id
            ):
                return person
        person = Person(name=wanted, source_batch_id=batch.id)
        self._people.add(person)
        return person

    def _attribute_one(self, photo_id, person, owner_map: dict) -> PhotoAttributionOutcome:
        reason = self._validate_photo(photo_id, owner_map)
        if reason:
            return PhotoAttributionOutcome(photo_id=photo_id, ok=False, reason=reason)
        result = self._recognition.list_first_by_photo_ids([photo_id]).get(photo_id)
        if result is None:
            # 合成 PENDING 行（confidence=None＝人工指派、无相似度证据）——
            # 身份批准链复用 pending 行为投影（D-3）。
            result = RecognitionResult(
                photo_id=photo_id, person_id=None, confidence=None,
            )
            self._recognition.add(result)
        outcome = self._review.approve(result.id, person_id=person.id)
        if outcome is None:
            return PhotoAttributionOutcome(
                photo_id=photo_id, ok=False, reason="识别结果已被终审（状态冲突）",
            )
        return PhotoAttributionOutcome(photo_id=photo_id, ok=True)

    def execute(self, command: ManualAttributionCommand) -> ManualAttributionResult:
        """逐张归档（允许部分成功；每张独立提交，失败不中断整批）."""
        person_name = command.person_name.strip()
        if not person_name:
            raise ValidationError("人员姓名不能为空")
        if (command.existing_batch_id is None) == (command.new_batch_name is None):
            raise ValidationError(
                "必须且只能选择一种批次方式：新建批次或并入已导入批次",
            )
        if command.new_batch_name is not None and not command.new_batch_name.strip():
            raise ValidationError("新建批次名称不能为空")

        batch = self._resolve_batch(command)
        person = self._resolve_person(person_name, batch)
        assert person.id is not None

        owner_map = self._owning_face_counts(command.photo_ids)
        outcomes = []
        assigned = 0
        for photo_id in command.photo_ids:
            try:
                outcome = self._attribute_one(photo_id, person, owner_map)
            except Exception as exc:  # noqa: BLE001 - 逐项披露，不中断整批
                logger.warning(
                    "Manual attribution failed for photo {}: {}", photo_id, exc,
                )
                outcome = PhotoAttributionOutcome(
                    photo_id=photo_id, ok=False, reason=str(exc),
                )
            outcomes.append(outcome)
            if outcome.ok:
                assigned += 1
        result = ManualAttributionResult(
            assigned=assigned,
            outcomes=tuple(outcomes),
            person_id=person.id,
            person_name=person.name,
            batch_id=batch.id,
            batch_name=batch.file_name,
        )
        logger.info(
            "AUDIT manual-attribution actor=local-user batch={} person={} "
            "assigned={}/{}",
            batch.file_name, person.name, assigned, len(command.photo_ids),
        )
        return result
