"""Face observation repository interface（阶段 C）.

写路径只有批量插入：Observation 一旦落库即不可变（frozen 实体），
重跑产生的同照片新数据属于新 run，经 ``UNIQUE(run_id, photo_id,
face_index)`` 与既有 run 的数据天然隔离（C-SEM-1）——仓储不提供
update / delete。
"""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities.face_observation import FaceObservation


class FaceObservationRepository(Protocol):
    """Define persistence operations for face observations."""

    def add_many(self, observations: Sequence[FaceObservation]) -> None:
        """批量插入 Observation（识别管线按 50 条分批 flush 的落库单元）。

        空输入为 no-op（不开连接）。实现必须拒绝违反
        ``(run_id, photo_id, face_index)`` 唯一性的批次——重复即覆盖
        是 C-SEM-1 禁止的行为。
        """

    def list_by_run(self, run_id: UUID) -> list[FaceObservation]:
        """Return the run's observations ordered by ``photo_id, face_index``."""

    def list_by_run_photo(self, run_id: UUID, photo_id: UUID) -> list[FaceObservation]:
        """Return one photo's observations within a run, ordered by ``face_index``."""

    def list_by_photo(self, photo_id: UUID) -> list[FaceObservation]:
        """Return the photo's observations across runs, ordered by ``run_id, face_index``.

        跨 run 语义（哪次新、哪次旧）由 ``RecognitionRunRepository.list_runs``
        的 created_at 排序表达；本方法只保证确定性顺序。
        """
