"""SQLite implementation of the face observation repository interface（阶段 C）.

bbox / embedding 以 JSON 文本存储（与 ``person_embeddings`` 的 SEC-030
决策一致：JSON 是数据专用反序列化，避免 pickle 任意代码执行面）。
"""

import json
from collections.abc import Sequence
from uuid import UUID

from photo_archiver.domain.entities.face_observation import FaceObservation
from photo_archiver.domain.repositories.face_observation_repository import (
    FaceObservationRepository,
)
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_mappers import face_observation_from_row


class SQLiteFaceObservationRepository(FaceObservationRepository):
    """Persist face observations in SQLite；``add_many`` 是管线 50 条 flush 的落库单元."""

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the repository with a connection provider."""
        self._connection_provider = connection_provider

    def add_many(self, observations: Sequence[FaceObservation]) -> None:
        """批量 INSERT（单连接单事务 executemany；空输入 no-op 不开连接）.

        无 ``ON CONFLICT``——``UNIQUE(run_id, photo_id, face_index)`` 违反
        即抛 IntegrityError，从存储层杜绝同 run 重复/覆盖（C-SEM-1）。
        """
        if not observations:
            return
        rows = [
            (
                str(observation.id),
                str(observation.run_id),
                str(observation.photo_id),
                observation.face_index,
                observation.photo_face_count,
                observation.det_score,
                json.dumps(
                    [
                        observation.box.x1,
                        observation.box.y1,
                        observation.box.x2,
                        observation.box.y2,
                    ]
                ),
                observation.quality_score,
                json.dumps(list(observation.embedding.vector)),
                observation.scope_verdict,
            )
            for observation in observations
        ]
        with self._connection_provider.connect() as connection:
            connection.executemany(
                """
                INSERT INTO face_observations (
                    id, run_id, photo_id, face_index, photo_face_count,
                    det_score, bbox, quality_score, embedding, scope_verdict
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def list_by_run(self, run_id: UUID) -> list[FaceObservation]:
        """Return the run's observations ordered by ``photo_id, face_index``."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM face_observations WHERE run_id = ? "
                "ORDER BY photo_id, face_index",
                (str(run_id),),
            ).fetchall()
        return [face_observation_from_row(row) for row in rows]

    def list_by_run_photo(self, run_id: UUID, photo_id: UUID) -> list[FaceObservation]:
        """Return one photo's observations within a run, ordered by ``face_index``."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM face_observations WHERE run_id = ? AND photo_id = ? "
                "ORDER BY face_index",
                (str(run_id), str(photo_id)),
            ).fetchall()
        return [face_observation_from_row(row) for row in rows]

    def list_by_photo(self, photo_id: UUID) -> list[FaceObservation]:
        """Return the photo's observations across runs, ordered by ``run_id, face_index``."""
        with self._connection_provider.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM face_observations WHERE photo_id = ? "
                "ORDER BY run_id, face_index",
                (str(photo_id),),
            ).fetchall()
        return [face_observation_from_row(row) for row in rows]
