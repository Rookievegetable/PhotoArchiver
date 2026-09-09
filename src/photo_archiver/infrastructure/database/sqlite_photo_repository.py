"""SQLite implementation of the photo repository interface."""

from collections.abc import Sequence
from uuid import UUID

from photo_archiver.domain import (
    Photo,
    PhotoMetadata,
    PhotoPath,
    PhotoRepository,
    PhotoSearchCriteria,
)
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import (
    datetime_to_text,
    path_to_columns,
    photo_from_row,
)

# ADR-029 先例：SQLite 绑定参数上限规避——IN 子句按 500 参数分块。
_SQLITE_PARAMETER_CHUNK = 500


class SQLitePhotoRepository(PhotoRepository):
    """Persist photos in SQLite."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def add(self, photo: Photo) -> None:
        """Persist a photo entity in SQLite using an idempotent upsert by id."""
        raw_path, path_base = path_to_columns(photo.path)
        metadata = photo.metadata
        with self._connection_provider.connect() as connection:
            connection.execute(
                """
                INSERT INTO photos (
                    id,
                    raw_path,
                    path_base,
                    folder_id,
                    original_name,
                    created_at,
                    captured_at,
                    metadata_width,
                    metadata_height,
                    metadata_file_size_bytes,
                    metadata_modified_at,
                    metadata_content_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    raw_path = excluded.raw_path,
                    path_base = excluded.path_base,
                    folder_id = excluded.folder_id,
                    original_name = excluded.original_name,
                    created_at = excluded.created_at,
                    captured_at = excluded.captured_at,
                    metadata_width = excluded.metadata_width,
                    metadata_height = excluded.metadata_height,
                    metadata_file_size_bytes = excluded.metadata_file_size_bytes,
                    metadata_modified_at = excluded.metadata_modified_at,
                    metadata_content_hash = excluded.metadata_content_hash
                """,
                (
                    str(photo.id),
                    raw_path,
                    path_base,
                    str(photo.folder_id) if photo.folder_id is not None else None,
                    photo.original_name,
                    datetime_to_text(photo.created_at),  # type: ignore[arg-type]  # guaranteed non-None by __post_init__
                    datetime_to_text(photo.captured_at) if photo.captured_at is not None else None,
                    metadata.width if metadata is not None else None,
                    metadata.height if metadata is not None else None,
                    metadata.file_size_bytes if metadata is not None else None,
                    datetime_to_text(metadata.modified_at)
                    if metadata is not None and metadata.modified_at is not None
                    else None,
                    metadata.content_hash if metadata is not None else None,
                ),
            )

    def remove(self, photo_ids: Sequence[UUID]) -> int:
        """Remove the given photos; return the actually removed row count.

        ADR-034（D1）：识别结果与归档记录由外键 ``ON DELETE CASCADE`` 自动
        级联删除（连接强制 ``foreign_keys=ON``）——本方法只删 ``photos``
        行，不手写级联。按 500 参数分块（ADR-029 先例）；幂等：不存在的
        id 计 0 行。磁盘文件一律不动（D3）。
        """
        if not photo_ids:
            return 0
        removed = 0
        with self._connection_provider.connect() as connection:
            for chunk_start in range(0, len(photo_ids), _SQLITE_PARAMETER_CHUNK):
                chunk = photo_ids[chunk_start : chunk_start + _SQLITE_PARAMETER_CHUNK]
                placeholders = ", ".join("?" for _ in chunk)
                cursor = connection.execute(
                    f"DELETE FROM photos WHERE id IN ({placeholders})",
                    [str(photo_id) for photo_id in chunk],
                )
                removed += cursor.rowcount
        return removed

    def update_metadata(self, photo_id: UUID, metadata: PhotoMetadata | None) -> int:
        """Update only the metadata columns; return the updated row count.

        Phase E E-5（ADR-034 D5）：重扫对账刷新元数据。只 UPDATE metadata_*
        五列，**不触碰 captured_at / created_at / folder_id / raw_path**——
        快照列保持原值（ISSUE-019 已入库不回填拍摄时刻的语义延续）。幂等：
        id 不存在返回 0，不抛错。
        """
        width = height = file_size = modified_at_text = content_hash = None
        if metadata is not None:
            width = metadata.width
            height = metadata.height
            file_size = metadata.file_size_bytes
            modified_at_text = (
                datetime_to_text(metadata.modified_at)
                if metadata.modified_at is not None
                else None
            )
            content_hash = metadata.content_hash
        with self._connection_provider.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE photos
                SET metadata_width = ?,
                    metadata_height = ?,
                    metadata_file_size_bytes = ?,
                    metadata_modified_at = ?,
                    metadata_content_hash = ?
                WHERE id = ?
                """,
                (width, height, file_size, modified_at_text, content_hash, str(photo_id)),
            )
        return cursor.rowcount

    def find_by_id(self, photo_id: UUID) -> Photo | None:
        """Find a photo by its domain identifier."""
        with self._connection_provider.connect() as connection:
            row = connection.execute("SELECT * FROM photos WHERE id = ?", (str(photo_id),)).fetchone()
        return photo_from_row(row) if row is not None else None

    def find_by_path(self, path: PhotoPath) -> Photo | None:
        """Find a photo by its path value."""
        raw_path, path_base = path_to_columns(path)
        with self._connection_provider.connect() as connection:
            row = connection.execute(
                "SELECT * FROM photos WHERE raw_path = ? AND path_base = ?",
                (raw_path, path_base),
            ).fetchone()
        return photo_from_row(row) if row is not None else None

    def list_all(self) -> list[Photo]:
        """Return all known photos."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute("SELECT * FROM photos ORDER BY created_at, id").fetchall()
        return [photo_from_row(row) for row in rows]

    def list_by_folder_id(self, folder_id: UUID) -> list[Photo]:
        """Return photos belonging to the given folder."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM photos WHERE folder_id = ? ORDER BY created_at, id",
                (str(folder_id),),
            ).fetchall()
        return [photo_from_row(row) for row in rows]

    def search(self, criteria: PhotoSearchCriteria) -> list[Photo]:
        """Return photos matching every supplied criterion (AND combination).

        SQLite 下推：动态拼 WHERE + 可选 JOIN recognition_results。person_id 与
        match_status 均涉 recognition_results，走同一 JOIN（person_id 过滤 person_id
        列、match_status 过滤 status 列）。captured_from/to 走 photos.captured_at
        区间。SQL 仅在本 infrastructure/database 层（ADR-004），参数化防注入。
        """
        clauses: list[str] = []
        params: list[str] = []
        join_needed = criteria.person_id is not None or criteria.match_status is not None
        if criteria.person_id is not None:
            clauses.append("rr.person_id = ?")
            params.append(str(criteria.person_id))
        if criteria.match_status is not None:
            clauses.append("rr.status = ?")
            params.append(criteria.match_status.value)
        if criteria.captured_from is not None:
            clauses.append("p.captured_at >= ?")
            params.append(datetime_to_text(criteria.captured_from))
        if criteria.captured_to is not None:
            clauses.append("p.captured_at <= ?")
            params.append(datetime_to_text(criteria.captured_to))
        where = " AND ".join(clauses) if clauses else "1 = 1"
        sql = "SELECT p.* FROM photos p"
        if join_needed:
            sql += " JOIN recognition_results rr ON rr.photo_id = p.id"
        sql += f" WHERE {where} ORDER BY p.created_at, p.id"
        with self._connection_provider.connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return [photo_from_row(row) for row in rows]

    def list_duplicate_groups(self) -> list[list[Photo]]:
        """Return groups of photos sharing the same non-null content hash.

        SQLite 下推：单查询 ``WHERE metadata_content_hash IN (SELECT ... GROUP BY ... HAVING ...)``
        一次性取所有重复组的照片行，Python 层按哈希切片分组。避免 N+1 查询（review-rules §15
        性能；ai-rules §18 避免重复数据库查询）——万级照片中若有 M 组重复，旧实现 M+1 次查询，
        新实现固定 2 次（含子查询）。NULL 哈希的历史照片被 ``WHERE metadata_content_hash IS NOT NULL``
        显式排除，与 Protocol 契约一致——它们走一次性回填 CLI 而非混入本查询。

        组间顺序：Python 层按 ``-len(members)`` 降序（与 DetectDuplicatesService 排序键一致，
        虽 service 会再排一次，但仓储侧先排保证对照测试稳定）。组内顺序：``created_at, id``。
        """
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM photos
                WHERE metadata_content_hash IN (
                    SELECT metadata_content_hash
                    FROM photos
                    WHERE metadata_content_hash IS NOT NULL
                    GROUP BY metadata_content_hash
                    HAVING COUNT(*) > 1
                )
                ORDER BY metadata_content_hash, created_at, id
                """,
            ).fetchall()
        # Python 层按哈希切片分组——rows 已按 metadata_content_hash 排序，连续同哈希归一组
        groups: list[list[Photo]] = []
        current_hash: str | None = None
        current_group: list[Photo] = []
        for row in rows:
            hash_value = row["metadata_content_hash"]
            if hash_value != current_hash:
                if current_group:
                    groups.append(current_group)
                current_group = []
                current_hash = hash_value
            current_group.append(photo_from_row(row))
        if current_group:
            groups.append(current_group)
        # 组间按成员数降序，与 DetectDuplicatesService 排序键对齐便于对照测试
        groups.sort(key=lambda g: -len(g))
        return groups
