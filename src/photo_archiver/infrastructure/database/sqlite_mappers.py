"""Mapping helpers between SQLite rows and domain entities."""

import json
from datetime import datetime
from pathlib import Path
from sqlite3 import Row
from uuid import UUID

from photo_archiver.domain import Folder, Person, PersonIdentity, Photo, PhotoMetadata, PhotoPath
from photo_archiver.domain.entities import (
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceObservation,
    MatchStatus,
    RecognitionResult,
    RecognitionRun,
)
from photo_archiver.domain.entities.archive import ArchiveRecord, ArchiveStatus
from photo_archiver.domain.value_objects import FaceBox, FaceEmbedding, PhotoPathBase


def datetime_to_text(value: datetime) -> str:
    """Serialize a datetime value for SQLite storage."""
    return value.isoformat()


def text_to_datetime(value: str) -> datetime:
    """Deserialize a datetime value from SQLite storage."""
    return datetime.fromisoformat(value)


def path_to_columns(path: PhotoPath) -> tuple[str, str]:
    """Convert a PhotoPath to SQLite path columns."""
    return str(path.raw_path), str(path.base)


def columns_to_path(raw_path: str, path_base: str) -> PhotoPath:
    """Convert SQLite path columns to a PhotoPath value object."""
    return PhotoPath(Path(raw_path), PhotoPathBase(path_base))


def person_from_row(row: Row) -> Person:
    """Convert a SQLite row to a Person entity.

    ``roster_order``/``source_batch_id`` are stage-A columns; the ``in row.keys()``
    guards keep the mapper usable over hand-built rows in older tests.
    """
    identity = PersonIdentity(row["identity"]) if row["identity"] is not None else None
    source_batch = row["source_batch_id"] if "source_batch_id" in row.keys() else None
    return Person(
        id=UUID(row["id"]),
        name=row["name"],
        identity=identity,
        department=row["department"],
        note=row["note"],
        created_at=text_to_datetime(row["created_at"]),
        roster_order=row["roster_order"] if "roster_order" in row.keys() else None,
        source_batch_id=UUID(source_batch) if source_batch else None,
    )


def folder_from_row(row: Row) -> Folder:
    """Convert a SQLite row to a Folder entity."""
    return Folder(
        id=UUID(row["id"]),
        path=columns_to_path(row["raw_path"], row["path_base"]),
        display_name=row["display_name"],
        total_photos=row["total_photos"],
        scanned_photos=row["scanned_photos"],
        created_at=text_to_datetime(row["created_at"]),
    )


def photo_from_row(row: Row) -> Photo:
    """Convert a SQLite row to a Photo entity."""
    metadata = None
    if any(
        row[column] is not None
        for column in (
            "metadata_width",
            "metadata_height",
            "metadata_file_size_bytes",
            "metadata_modified_at",
            "metadata_content_hash",
        )
    ):
        metadata = PhotoMetadata(
            width=row["metadata_width"],
            height=row["metadata_height"],
            file_size_bytes=row["metadata_file_size_bytes"],
            modified_at=(
                text_to_datetime(row["metadata_modified_at"])
                if row["metadata_modified_at"] is not None
                else None
            ),
            content_hash=row["metadata_content_hash"],
        )

    folder_id = UUID(row["folder_id"]) if row["folder_id"] is not None else None
    captured_at = (
        text_to_datetime(row["captured_at"])
        if row["captured_at"] is not None
        else None
    )
    return Photo(
        id=UUID(row["id"]),
        path=columns_to_path(row["raw_path"], row["path_base"]),
        folder_id=folder_id,
        metadata=metadata,
        original_name=row["original_name"],
        created_at=text_to_datetime(row["created_at"]),
        captured_at=captured_at,
    )


def recognition_result_from_row(row: Row) -> RecognitionResult:
    """Convert a SQLite row to a RecognitionResult entity.

    The entity is rebuilt in the already-finalized state when ``status`` is
    ``approved`` or ``rejected`` by directly setting the field via ``__new__``
    (bypassing ``__post_init__``), since the public ``approve``/``reject``
    methods refuse to transition a finalized result. This keeps the
    reconstructed entity's invariant intact without re-running the user-review
    workflow.

    Fragility note: ``__new__`` reflection bypasses ``__post_init__``, so if
    RecognitionResult gains fields or changes initialization logic this mapper
    must be updated in lockstep to avoid silently dropping columns.
    """
    status = MatchStatus(row["status"])
    result = RecognitionResult.__new__(RecognitionResult)
    result.photo_id = UUID(row["photo_id"])
    result.confidence = row["confidence"]
    result.id = UUID(row["id"])
    result.person_id = UUID(row["person_id"]) if row["person_id"] is not None else None
    result.status = status
    result.created_at = text_to_datetime(row["created_at"])
    return result


def archive_record_from_row(row: Row) -> ArchiveRecord:
    """Convert a SQLite row to an ArchiveRecord entity.

    The entity is rebuilt already-finalized (past PLANNED) by directly setting
    fields via ``__new__`` (bypassing ``__post_init__``), since the public
    ``mark_*`` methods refuse to re-transition a finalized record. This keeps
    the reconstructed entity's invariant intact without re-running the archive
    workflow.

    Fragility note: ``__new__`` reflection bypasses ``__post_init__``, so if
    ArchiveRecord gains fields or changes initialization logic this mapper
    must be updated in lockstep to avoid silently dropping columns.
    """
    status = ArchiveStatus(row["status"])
    archived_at = (
        text_to_datetime(row["archived_at"])
        if row["archived_at"] is not None
        else None
    )
    record = ArchiveRecord.__new__(ArchiveRecord)
    record.photo_id = UUID(row["photo_id"])
    record.target_archive_root = row["target_archive_root"]
    record.target_person_name = row["target_person_name"]
    record.target_event_or_date = row["target_event_or_date"]
    record.target_original_name = row["target_original_name"]
    record.status = status
    record.id = UUID(row["id"])
    record.archived_at = archived_at
    record.error = row["error"]
    # Stage 4 BLK-1：稳定 Person identity（存量行可能为 NULL）。
    record.person_id = UUID(row["person_id"]) if row["person_id"] is not None else None
    return record


def recognition_run_from_row(row: Row) -> RecognitionRun:
    """Convert a SQLite row to a RecognitionRun entity（阶段 C）.

    经**正常构造器**重建——RecognitionRun 构造器接受任意合法 status
    （历史 run 读回不重演生命周期；状态机守护在 start/complete/fail/
    cancel 方法上），因此无需 ``__new__`` 反射。``parameters`` 以 JSON
    读回配置快照；统计列原样还原。
    """
    finished_at = row["finished_at"]
    return RecognitionRun(
        id=UUID(row["id"]),
        status=row["status"],
        parameters=json.loads(row["parameters"]),
        face_count=row["face_count"],
        unreadable_count=row["unreadable_count"],
        no_face_count=row["no_face_count"],
        error_count=row["error_count"],
        in_scope_photo_count=row["in_scope_photo_count"],
        out_of_scope_photo_count=row["out_of_scope_photo_count"],
        error=row["error"],
        created_at=text_to_datetime(row["created_at"]),
        finished_at=text_to_datetime(finished_at) if finished_at is not None else None,
    )


def face_observation_from_row(row: Row) -> FaceObservation:
    """Convert a SQLite row to a frozen FaceObservation（阶段 C）.

    FaceObservation 不可变且无状态机方法，正常构造器即可完成重建并
    顺带重验不变量——刻意不沿用 ``recognition_result_from_row`` 的
    ``__new__`` 反射技巧（该技巧依赖字段增减时人工同步，较脆弱）。
    bbox / embedding 以 JSON 文本存储（与 person_embeddings 的 SEC-030
    决策一致：JSON 是数据专用反序列化，无 pickle 代码执行面）。
    """
    x1, y1, x2, y2 = json.loads(row["bbox"])
    return FaceObservation(
        id=UUID(row["id"]),
        run_id=UUID(row["run_id"]),
        photo_id=UUID(row["photo_id"]),
        face_index=row["face_index"],
        photo_face_count=row["photo_face_count"],
        det_score=row["det_score"],
        box=FaceBox(x1=x1, y1=y1, x2=x2, y2=y2),
        embedding=FaceEmbedding(tuple(json.loads(row["embedding"]))),
        scope_verdict=row["scope_verdict"],
        quality_score=row["quality_score"],
    )


def face_cluster_run_from_row(row: Row) -> FaceClusterRun:
    """Convert a SQLite row to a FaceClusterRun entity（阶段 D）.

    与 RecognitionRun 同约定：经正常构造器重建，历史 cluster run 读回
    不重演生命周期；``parameters`` 以 JSON 读回配置快照。
    """
    finished_at = row["finished_at"]
    return FaceClusterRun(
        id=UUID(row["id"]),
        recognition_run_id=UUID(row["recognition_run_id"]),
        algorithm_version=row["algorithm_version"],
        parameters=json.loads(row["parameters"]),
        status=row["status"],
        created_at=text_to_datetime(row["created_at"]),
        finished_at=text_to_datetime(finished_at) if finished_at is not None else None,
        error=row["error"],
        cluster_count=row["cluster_count"],
        member_count=row["member_count"],
        excluded_count=row["excluded_count"],
    )


def face_cluster_from_row(row: Row) -> FaceCluster:
    """Convert a SQLite row to a FaceCluster entity（阶段 D）."""
    first_captured_at = row["first_captured_at"]
    return FaceCluster(
        id=UUID(row["id"]),
        cluster_run_id=UUID(row["cluster_run_id"]),
        run_id=UUID(row["run_id"]),
        ordinal=row["ordinal"],
        member_count=row["member_count"],
        sort_key=row["sort_key"],
        status=row["status"],
        first_captured_at=(
            text_to_datetime(first_captured_at) if first_captured_at is not None else None
        ),
        created_at=text_to_datetime(row["created_at"]),
    )


def face_cluster_member_from_row(row: Row) -> FaceClusterMember:
    """Convert a SQLite row to a FaceClusterMember entity（阶段 D）."""
    return FaceClusterMember(
        id=UUID(row["id"]),
        cluster_id=UUID(row["cluster_id"]),
        observation_id=UUID(row["observation_id"]),
        source=row["source"],
        confidence=row["confidence"],
        created_at=text_to_datetime(row["created_at"]),
    )
