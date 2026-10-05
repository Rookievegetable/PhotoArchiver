"""SQLite adapter for the ground-truth calibration tables (S4-B-1).

与业务仓储完全隔离：本文件不 import 任何 Assignment / Recognition /
PersonFaceSample 仓储类型，只操作 ``calibration_*`` 三张表。
"""

from __future__ import annotations

import json
from uuid import UUID

from photo_archiver.domain.entities.calibration_annotation import (
    CalibrationAnnotation,
    CalibrationDataset,
    CalibrationGroundTruth,
)
from photo_archiver.domain.entities.calibration_annotation import (
    DATASET_STATUS_FROZEN,
)
from photo_archiver.domain.exceptions import ValidationError


from photo_archiver.infrastructure.database.sqlite_mappers import (
    datetime_to_text,
    text_to_datetime,
)


def _require_created(entity):
    """Return the entity's ``created_at``, asserting the entity is constructed.

    The field is declared ``datetime | None`` for dataclass generation but is
    always set in ``__post_init__``; annotation history is immutable, so a
    missing timestamp is a construction bug rather than a tolerated state.
    """
    if entity.created_at is None:  # pragma: no cover - entity guarantees
        raise ValidationError("calibration entity must carry created_at")
    return entity.created_at


def _annotation_from_row(row) -> CalibrationAnnotation:
    return CalibrationAnnotation(
        cluster_id=UUID(row["cluster_id"]),
        annotator_id=row["annotator_id"],
        verdict=row["verdict"],
        protocol_version=row["protocol_version"],
        role=row["role"],
        person_id=UUID(row["person_id"]) if row["person_id"] is not None else None,
        difficulty_reason=row["difficulty_reason"],
        id=UUID(row["id"]),
        created_at=text_to_datetime(row["created_at"]),
    )


def _ground_truth_from_row(row) -> CalibrationGroundTruth:
    return CalibrationGroundTruth(
        cluster_id=UUID(row["cluster_id"]),
        verdict=row["verdict"],
        resolution=row["resolution"],
        source_annotation_ids=tuple(
            UUID(item) for item in json.loads(row["source_annotation_ids"])
        ),
        annotator_count=row["annotator_count"],
        person_id=UUID(row["person_id"]) if row["person_id"] is not None else None,
        difficulty_reason=row["difficulty_reason"],
        dataset_id=UUID(row["dataset_id"]) if row["dataset_id"] is not None else None,
        dataset_version=row["dataset_version"],
        id=UUID(row["id"]),
        created_at=text_to_datetime(row["created_at"]),
    )


def _dataset_from_row(row) -> CalibrationDataset:
    return CalibrationDataset(
        version=row["version"],
        cluster_count=row["cluster_count"],
        usable_count=row["usable_count"],
        excluded_count=row["excluded_count"],
        protocol_version=row["protocol_version"],
        notes=row["notes"],
        id=UUID(row["id"]),
        created_at=text_to_datetime(row["created_at"]),
    )


class SQLiteCalibrationAnnotationRepository:
    """Ground-truth annotation persistence (calibration tables only)."""

    def __init__(self, connection_provider) -> None:  # noqa: ANN001
        self._connection_provider = connection_provider

    # ── 原始标注 ──────────────────────────────────────────────────────

    def add_annotation(self, annotation: CalibrationAnnotation) -> None:
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO calibration_annotations
                    (id, cluster_id, annotator_id, role, verdict, person_id,
                     difficulty_reason, protocol_version, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(annotation.id),
                    str(annotation.cluster_id),
                    annotation.annotator_id,
                    annotation.role,
                    annotation.verdict,
                    str(annotation.person_id) if annotation.person_id is not None else None,
                    annotation.difficulty_reason,
                    annotation.protocol_version,
                    datetime_to_text(_require_created(annotation)),
                ),
            )

    def list_annotations(
        self, cluster_id: UUID, role: str | None = None,
    ) -> list[CalibrationAnnotation]:
        with self._connection_provider.connect() as connection:
            if role is None:
                rows = connection.execute(
                    "SELECT * FROM calibration_annotations WHERE cluster_id = ? "
                    "ORDER BY created_at, id",
                    (str(cluster_id),),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM calibration_annotations "
                    "WHERE cluster_id = ? AND role = ? ORDER BY created_at, id",
                    (str(cluster_id), role),
                ).fetchall()
        return [_annotation_from_row(row) for row in rows]

    def find_latest_own_annotation(
        self, cluster_id: UUID, annotator_id: str,
    ) -> CalibrationAnnotation | None:
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM calibration_annotations "
                "WHERE cluster_id = ? AND annotator_id = ? AND role = ? "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (str(cluster_id), annotator_id, "independent"),
            ).fetchone()
        return _annotation_from_row(row) if row is not None else None

    def list_annotated_cluster_ids(self) -> list[UUID]:
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT cluster_id FROM calibration_annotations ORDER BY cluster_id"
            ).fetchall()
        return [UUID(row["cluster_id"]) for row in rows]

    # ── 最终真值 ──────────────────────────────────────────────────────

    def add_ground_truth(self, ground_truth: CalibrationGroundTruth) -> None:
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO calibration_ground_truth
                    (id, cluster_id, verdict, person_id, difficulty_reason,
                     resolution, source_annotation_ids, annotator_count,
                     dataset_id, dataset_version, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(ground_truth.id),
                    str(ground_truth.cluster_id),
                    ground_truth.verdict,
                    str(ground_truth.person_id)
                    if ground_truth.person_id is not None else None,
                    ground_truth.difficulty_reason,
                    ground_truth.resolution,
                    json.dumps(
                        [str(item) for item in ground_truth.source_annotation_ids]
                    ),
                    ground_truth.annotator_count,
                    str(ground_truth.dataset_id)
                    if ground_truth.dataset_id is not None else None,
                    ground_truth.dataset_version,
                    datetime_to_text(_require_created(ground_truth)),
                ),
            )

    def find_ground_truth(self, cluster_id: UUID) -> CalibrationGroundTruth | None:
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM calibration_ground_truth WHERE cluster_id = ? "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (str(cluster_id),),
            ).fetchone()
        return _ground_truth_from_row(row) if row is not None else None

    def list_ground_truth(
        self, dataset_id: UUID | None = None, dataset_version: str | None = None,
    ) -> list[CalibrationGroundTruth]:
        clauses, params = [], []
        if dataset_id is not None:
            clauses.append("dataset_id = ?")
            params.append(str(dataset_id))
        if dataset_version is not None:
            clauses.append("dataset_version = ?")
            params.append(dataset_version)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM calibration_ground_truth{where} ORDER BY cluster_id, created_at",
                params,
            ).fetchall()
        return [_ground_truth_from_row(row) for row in rows]

    # ── 冻结数据集 ────────────────────────────────────────────────────

    def add_dataset(self, dataset: CalibrationDataset) -> None:
        """Persist one dataset descriptor.

        CP4.7：migration 011 的 ``calibration_datasets.status`` CHECK 只允许
        ``'frozen'``。本实现**显式拒绝**非 frozen 数据集，而不是静默写成
        ``frozen``——那会让调用方以为 draft 已持久化，实际是冻结态，破坏
        "draft 仍可随新标注变化"的语义。持久化 draft 需要放宽 CHECK 的新
        migration；本阶段不擅自扩展 schema。
        """
        if dataset.status != DATASET_STATUS_FROZEN:
            raise CalibrationPersistenceError(
                f"cannot persist dataset with status {dataset.status!r}: migration "
                "011 constrains calibration_datasets.status to 'frozen'. Storing "
                "'draft' needs a schema change; refusing to silently record it as "
                "'frozen'."
            )
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO calibration_datasets
                    (id, version, protocol_version, status, cluster_count,
                     usable_count, excluded_count, notes, created_at)
                VALUES (?,?,?,'frozen',?,?,?,?,?)
                """,
                (
                    str(dataset.id),
                    dataset.version,
                    dataset.protocol_version,
                    dataset.cluster_count,
                    dataset.usable_count,
                    dataset.excluded_count,
                    dataset.notes,
                    datetime_to_text(_require_created(dataset)),
                ),
            )

    def get_dataset(
        self, dataset_id: UUID, version: str | None = None,
    ) -> CalibrationDataset | None:
        """Return one dataset.

        S4-B-1 B-2：复合主键是 ``(id, version)``。传 ``version`` 时精确命中；
        省略时按创建序返回**最近**的版本——多版本共存后，"只按 id 查"已无唯一解，
        返回任意一条会让调用方拿到过期评估集，故显式定义为最新。
        """
        with self._connection_provider.connect() as connection:
            if version is not None:
                row = connection.execute(
                    "SELECT * FROM calibration_datasets WHERE id = ? AND version = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (str(dataset_id), version),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM calibration_datasets WHERE id = ? "
                    "ORDER BY created_at DESC, version DESC LIMIT 1",
                    (str(dataset_id),),
                ).fetchone()
        return _dataset_from_row(row) if row is not None else None

    def list_datasets(self) -> list[CalibrationDataset]:
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM calibration_datasets ORDER BY created_at, version"
            ).fetchall()
        return [_dataset_from_row(row) for row in rows]


class CalibrationPersistenceError(ValidationError):
    """Raised when the calibration schema cannot faithfully store an entity.

    例：migration 011 的 calibration_datasets.status CHECK 只允许 frozen，因此 draft 数据集无法被诚实持久化——此时报错而非静默改写。
    """
