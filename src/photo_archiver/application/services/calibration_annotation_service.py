"""Ground Truth 标注服务（S4-B-1 建立，S4-B-2 D-2 改为单专家协议）。

生命周期（D-2 = Single Human Expert）::

    UNLABELED
        │  annotate(expert)       append-only
        ▼
    ANNOTATED ──► resolve_ground_truth() ──► FINAL_GROUND_TRUTH
                                                   │
                                          freeze(dataset) ▼
                                            FROZEN_EVALUATION_DATASET

四条硬规则（测试逐条钉死）：

1. **单专家即真值**：每簇恰一条专家标注直接构成 GT —— ``resolution``
   恒为 ``expert``，``annotator_count == 1 == len(source_annotation_ids)``
   由 ``CalibrationGroundTruth`` 构造期强制；双标共识（agreed）与仲裁
   （adjudicated）已随旧协议废止，不存在任何伪造第二标注的兼容路径。
2. **历史不可覆盖**：``add_annotation`` 只追加；重新标注 = 新行，旧行仍在，
   "最新行"是该簇的当前答案。
3. **盲标注**：服务不提供"给我看别人的答案"的标注者视图；
   ``annotate`` 不读取也不写入任何业务 Assignment。
4. **不污染业务链**：本服务**不注入** ``ClusterPersonAssignmentRepository`` /
   ``RecognitionRepository`` / ``PersonFaceSampleRepository``——结构上无法创建
   Business Assignment 或触发归档。

``undecidable`` 的处理：它不是"拒绝标注"，而是一个**已完成**的核验结论。
它会进入 ground truth 与数据集，但 S4-B-2 必须把它排除在精确率分母之外
（本阶段只负责如实记录该标签与其难例原因）。
"""

from datetime import datetime, timedelta
from uuid import UUID

from photo_archiver.domain.entities.calibration_annotation import (
    ANNOTATION_ROLES,
    DIFFICULTY_REASONS,
    PROTOCOL_VERSION,
    RESOLUTION_EXPERT,
    ROLE_INDEPENDENT,
    VERDICTS,
    VERDICT_PERSON,
    VERDICT_UNDECIDABLE,
    CalibrationAnnotation,
    CalibrationDataset,
    CalibrationGroundTruth,
)
from photo_archiver.domain.repositories.calibration_annotation_repository import (
    CalibrationAnnotationRepository,
)


class CalibrationAnnotationService:
    """Record expert annotations, derive ground truth, freeze datasets."""

    def __init__(self, repository: CalibrationAnnotationRepository) -> None:
        self._repository = repository
        self._last_issued_at: datetime | None = None

    @property
    def store(self) -> CalibrationAnnotationRepository:
        """Read-only audit access (tests / reporting).

        Exposed deliberately so verification code can assert the isolation
        guarantees — e.g. "annotating N clusters produced zero rows in the
        business tables" — without reaching into privates.
        """
        return self._repository

    # ── 标注 ──────────────────────────────────────────────────────────

    def annotate(
        self,
        cluster_id: UUID,
        annotator_id: str,
        verdict: str,
        person_id: UUID | None = None,
        difficulty_reason: str | None = None,
        protocol_version: str = PROTOCOL_VERSION,
    ) -> CalibrationAnnotation:
        """Append one **independent** annotation.

        同一标注者重复标注同一簇 → 追加新行（历史保留），不覆盖；最新行是该
        标注者的当前答案（供盲标注 UI 渲染）。

        ``created_at`` 被强制**单调递增**：`datetime.now()` 的微秒精度在快速
        连写时可能相同，此时"最新"会退化为 UUID 序而随机。保证单调后，"取最新
        一行"与"写入序最后"严格一致——这是"历史保留、最新为准"能成立的
        结构性前提。
        """
        annotation = CalibrationAnnotation(
            cluster_id=cluster_id,
            annotator_id=annotator_id,
            verdict=verdict,
            person_id=person_id,
            difficulty_reason=difficulty_reason,
            role=ROLE_INDEPENDENT,
            protocol_version=protocol_version,
            created_at=self._next_timestamp(),
        )
        self._repository.add_annotation(annotation)
        return annotation

    def latest_own_annotation(
        self, cluster_id: UUID, annotator_id: str,
    ) -> CalibrationAnnotation | None:
        """The annotator's own latest row — the only view an annotator UI may use."""
        return self._repository.find_latest_own_annotation(cluster_id, annotator_id)

    def _next_timestamp(self) -> datetime:
        """Strictly increasing creation timestamp (append-order == latest-order)."""
        now = datetime.now()
        if self._last_issued_at is not None and now <= self._last_issued_at:
            now = self._last_issued_at + timedelta(microseconds=1)
        self._last_issued_at = now
        return now

    # ── 真值解析（单专家）────────────────────────────────────────────

    def resolve_ground_truth(self, cluster_id: UUID) -> CalibrationGroundTruth | None:
        """Derive the current ground truth, or ``None`` if not yet annotated.

        D-2 单专家协议：该簇**最新一条**标注（append-only 历史的最后一条）
        直接构成真值 —— ``resolution='expert'``、``annotator_count=1``、
        单一 source annotation。无任何标注 → ``None``（不产生真值行，
        未完成标注无法进入评估集）。

        "最新"判据：``list_annotations`` 按 ``(created_at, id)`` 升序返回，
        最后一条即最新（读取侧契约 ``LATEST_ANNOTATION_ORDER``）。
        """
        annotations = self._repository.list_annotations(cluster_id)
        if not annotations:
            return None
        latest = annotations[-1]
        return CalibrationGroundTruth(
            cluster_id=cluster_id,
            verdict=latest.verdict,
            person_id=latest.person_id,
            resolution=RESOLUTION_EXPERT,
            difficulty_reason=latest.difficulty_reason,
            source_annotation_ids=(latest.id,),
            annotator_count=1,
        )

    # ── 冻结数据集 ────────────────────────────────────────────────────

    def freeze_dataset(
        self,
        dataset_id: UUID,
        version: str,
        notes: str | None = None,
        protocol_version: str = PROTOCOL_VERSION,
    ) -> CalibrationDataset:
        """Freeze the current resolvable truth into an immutable dataset.

        只有已解析出真值的簇进入数据集；未标注的簇计入 ``excluded_count``，
        **不**被静默丢弃。数据集一经冻结，其成员的
        ``dataset_id`` / ``dataset_version`` 即固定；重新标注须产生新的
        ``version``（不改旧集）。
        """
        included: list[CalibrationGroundTruth] = []
        excluded = 0
        for cluster_id in self._repository.list_annotated_cluster_ids():
            truth = self.resolve_ground_truth(cluster_id)
            if truth is None:
                excluded += 1
                continue
            versioned = CalibrationGroundTruth(
                cluster_id=truth.cluster_id,
                verdict=truth.verdict,
                person_id=truth.person_id,
                resolution=truth.resolution,
                difficulty_reason=truth.difficulty_reason,
                source_annotation_ids=truth.source_annotation_ids,
                annotator_count=truth.annotator_count,
                dataset_id=dataset_id,
                dataset_version=version,
            )
            self._repository.add_ground_truth(versioned)
            included.append(versioned)

        dataset = CalibrationDataset(
            version=version,
            protocol_version=protocol_version,
            cluster_count=len(included) + excluded,
            usable_count=len(included),
            excluded_count=excluded,
            notes=notes,
            id=dataset_id,
        )
        self._repository.add_dataset(dataset)
        return dataset

    def dataset_truth(
        self, dataset_id: UUID, dataset_version: str | None = None,
    ) -> list[CalibrationGroundTruth]:
        """Ground truth rows belonging to a frozen dataset (S4-B-2 的输入）。"""
        return self._repository.list_ground_truth(dataset_id, dataset_version)


__all__ = [
    "ANNOTATION_ROLES",
    "CalibrationAnnotationService",
    "DIFFICULTY_REASONS",
    "VERDICTS",
    "VERDICT_PERSON",
    "VERDICT_UNDECIDABLE",
]