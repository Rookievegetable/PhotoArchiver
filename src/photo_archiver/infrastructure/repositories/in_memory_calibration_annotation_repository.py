"""In-memory test double for the ground-truth calibration tables (S4-B-1).

与 SQLite 实现保持同语义（排序、latest 判定），使 domain/service 测试可以
脱离数据库运行；SQLite 路径另有真实数据库测试覆盖。
"""

from __future__ import annotations

from uuid import UUID

from photo_archiver.domain.entities.calibration_annotation import (
    DATASET_STATUS_FROZEN,
    ROLE_INDEPENDENT,
    CalibrationAnnotation,
    CalibrationDataset,
    CalibrationGroundTruth,
)
from photo_archiver.domain.exceptions import ValidationError


from photo_archiver.infrastructure.database.sqlite_calibration_annotation_repository import (  # noqa: E501
    _annotation_from_row,  # noqa: F401  # re-exported for symmetry tests
)


def _sort_key(annotation: CalibrationAnnotation) -> tuple:
    created = annotation.created_at
    return (created is not None, created, str(annotation.id))


class InMemoryCalibrationAnnotationRepository:
    """Calibration annotation store mirroring the SQLite adapter's semantics."""

    def __init__(self) -> None:
        self._annotations: dict[UUID, CalibrationAnnotation] = {}
        self._ground_truth: dict[UUID, CalibrationGroundTruth] = {}
        self._datasets: dict[tuple[UUID, str], CalibrationDataset] = {}

    # ── 原始标注 ──────────────────────────────────────────────────────

    def add_annotation(self, annotation: CalibrationAnnotation) -> None:
        self._annotations[annotation.id] = annotation

    def list_annotations(
        self, cluster_id: UUID, role: str | None = None,
    ) -> list[CalibrationAnnotation]:
        rows = [
            annotation
            for annotation in self._annotations.values()
            if annotation.cluster_id == cluster_id
            and (role is None or annotation.role == role)
        ]
        return sorted(rows, key=_sort_key)

    def find_latest_own_annotation(
        self, cluster_id: UUID, annotator_id: str,
    ) -> CalibrationAnnotation | None:
        rows = [
            annotation
            for annotation in self._annotations.values()
            if annotation.cluster_id == cluster_id
            and annotation.annotator_id == annotator_id
            and annotation.role == ROLE_INDEPENDENT
        ]
        return max(rows, key=_sort_key) if rows else None

    def list_annotated_cluster_ids(self) -> list[UUID]:
        return sorted({a.cluster_id for a in self._annotations.values()})

    # ── 最终真值 ──────────────────────────────────────────────────────

    def add_ground_truth(self, ground_truth: CalibrationGroundTruth) -> None:
        self._ground_truth[ground_truth.id] = ground_truth

    def find_ground_truth(self, cluster_id: UUID) -> CalibrationGroundTruth | None:
        rows = [
            truth
            for truth in self._ground_truth.values()
            if truth.cluster_id == cluster_id
        ]
        return max(rows, key=lambda t: (t.created_at is not None, t.created_at, str(t.id))) \
            if rows else None

    def list_ground_truth(
        self, dataset_id: UUID | None = None, dataset_version: str | None = None,
    ) -> list[CalibrationGroundTruth]:
        rows = list(self._ground_truth.values())
        if dataset_id is not None:
            rows = [t for t in rows if t.dataset_id == dataset_id]
        if dataset_version is not None:
            rows = [t for t in rows if t.dataset_version == dataset_version]
        return sorted(rows, key=lambda t: (str(t.cluster_id), str(t.id)))

    # ── 冻结数据集 ────────────────────────────────────────────────────

    def add_dataset(self, dataset: CalibrationDataset) -> None:
        """Mirror the SQLite backend's draft rejection (CP4.8 backend parity).

        内存双必须与 SQLite 表达**同一**限制：只持久化 frozen。若这里接受 draft
        而 SQLite 拒绝，测试就会掩盖真实的行为分歧。
        """
        if dataset.status != DATASET_STATUS_FROZEN:
            raise CalibrationPersistenceError(
                f"cannot persist dataset with status {dataset.status!r}: the "
                "calibration schema constrains datasets to 'frozen'."
            )
        self._datasets[(dataset.id, dataset.version)] = dataset

    def get_dataset(
        self, dataset_id: UUID, version: str | None = None,
    ) -> CalibrationDataset | None:
        """S4-B-1 B-2：按 (id, version) 定位；省略 version 时返回最新版本。"""
        if version is not None:
            return self._datasets.get((dataset_id, version))
        candidates = [
            dataset for key, dataset in self._datasets.items() if key[0] == dataset_id
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda d: (d.created_at, d.version))

    def list_datasets(self) -> list[CalibrationDataset]:
        return sorted(self._datasets.values(), key=lambda d: (d.created_at, d.version))


class CalibrationPersistenceError(ValidationError):
    """Raised when the calibration schema cannot faithfully store an entity.

    Mirrors the SQLite adapter so both backends enforce identical limits (CP4.8).
    """
