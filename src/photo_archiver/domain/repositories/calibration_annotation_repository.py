"""Ground Truth 标注仓储契约（S4-B-1 / Checkpoint 2）。

**隔离性是契约本身的一部分**：本协议**不包含**任何读写
``cluster_person_assignments`` / ``recognition_results`` /
``person_face_embeddings`` / ``archive_records`` 的方法。Calibration 服务因此在
**结构上**无法把业务链写进标注流程——测试
``test_calibration_contract_excludes_business_capabilities`` 逐个断言下列业务方法名
不出现在契约中。

三个正交约束：

1. **盲标注（CP2.2）**：``find_latest_own_annotation``（own 视图）与
   ``list_annotations``（审计视图）分离到**方法粒度**——不允许
   ``list_all()`` 再由调用方在内存中过滤，那等于没做隔离。
2. **append-only（CP2.3）**：契约只提供 ``add_*``；**不提供**
   ``update_*`` / ``delete_*``。重新标注 = 新建行（单专家协议，S4-B-2 D-2：
   每簇最新一条即当前答案）。历史真实性由"接口里根本没有改删"保证。
3. **冻结数据集（CP2.4）**：``status='frozen'`` 的数据集内容不可原地修改；
   新一轮标注必须以新的 ``(id, version)`` 落地，旧版本成员保持原样。
"""

from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities.calibration_annotation import (
    LATEST_ANNOTATION_ORDER,
    CalibrationAnnotation,
    CalibrationDataset,
    CalibrationGroundTruth,
)
from photo_archiver.domain.exceptions import ValidationError


class CalibrationAnnotationRepository(Protocol):
    """Persistence for ground-truth annotations, ground truth and datasets."""

    # ── 原始标注（append-only：只有 add，没有 update/delete） ──────────

    def add_annotation(self, annotation: CalibrationAnnotation) -> None:
        """Append one annotation row. Never merges or overwrites.

        重复标注 = 追加新行（CP2.3）；历史行永久保留，"最新"由
        ``find_latest_own_annotation`` / 调用方按
        :data:`LATEST_ANNOTATION_ORDER` 判定。
        """

    def list_annotations(
        self, cluster_id: UUID, role: str | None = None,
    ) -> list[CalibrationAnnotation]:
        """Return every annotation of a cluster — **audit view only**.

        盲标注边界（CP2.2）：本方法**不得**用于渲染标注者自己的表单，否则等于
        泄露另一标注者的答案。实现必须按
        :data:`LATEST_ANNOTATION_ORDER` 升序返回（最新 = 最后一条）。

        ``role`` 过滤出独立标注或仲裁标注；调用方据此实现
        "每位标注者取其最新一条"的一致性判定。
        """

    def find_latest_own_annotation(
        self, cluster_id: UUID, annotator_id: str,
    ) -> CalibrationAnnotation | None:
        """Return one annotator's most recent row — **the blind view**.

        这是标注者 UI **唯一**允许使用的标注查询：只返回该标注者自己的行，
        不泄露他人结果，也不返回仲裁记录。
        """

    def list_annotated_cluster_ids(self) -> list[UUID]:
        """Cluster ids that carry at least one annotation (freeze traversal)."""

    # ── 最终真值 ──────────────────────────────────────────────────────

    def add_ground_truth(self, ground_truth: CalibrationGroundTruth) -> None:
        """Append one resolved truth row.

        只有 ``annotator_count >= 2`` 的真值才会被构造（实体强制），因此本方法
        天然不接受"单条标注即真值"。重新冻结产生新行 + 新 dataset version，
        旧行不被覆盖。
        """

    def find_ground_truth(self, cluster_id: UUID) -> CalibrationGroundTruth | None:
        """Return the current ground truth of a cluster, if any."""

    def list_ground_truth(
        self, dataset_id: UUID | None = None, dataset_version: str | None = None,
    ) -> list[CalibrationGroundTruth]:
        """Return resolved truths, optionally restricted to one dataset version.

        **输入边界（CP2.5）**：只返回**已解析完成**的
        :class:`CalibrationGroundTruth`。本方法不得被用来临时把 annotation 当
        truth、不得从 Assignment 生成 truth、不得读取 Top-1 或 machine score
        作为 truth——评估层的唯一输入是真值行。

        每行至少可表达 ``cluster_id`` / ``verdict`` / ``person_id`` /
        ``difficulty_reason`` / ``resolution`` / ``source_annotation_ids``。
        """

    # ── 冻结数据集 ────────────────────────────────────────────────────

    def add_dataset(self, dataset: CalibrationDataset) -> None:
        """Persist one dataset descriptor (draft or frozen)."""

    def get_dataset(
        self, dataset_id: UUID, version: str | None = None,
    ) -> CalibrationDataset | None:
        """Return one dataset.

        冻结粒度是 ``(id, version)``（S4-B-1 B-2）：同一数据集可有多个版本共存。
        传 ``version`` 精确命中；省略时返回**最新**版本——多版本共存后"只按 id 查"
        已无唯一解，返回任意一条会让调用方拿到过期评估集。
        """

    def list_datasets(self) -> list[CalibrationDataset]:
        """Return all datasets (version history)."""


class CalibrationAnnotationServiceError(ValidationError):
    """Raised when an annotation violates the ground-truth protocol."""


def assert_independent(annotation: CalibrationAnnotation) -> None:
    """Guard that adjudication rows cannot masquerade as independent annotations."""
    if annotation.role not in ("independent", "adjudication"):  # pragma: no cover
        raise CalibrationAnnotationServiceError(
            f"Unknown annotation role: {annotation.role}"
        )


__all__ = [
    "CalibrationAnnotationRepository",
    "CalibrationAnnotationServiceError",
    "LATEST_ANNOTATION_ORDER",
    "assert_independent",
]