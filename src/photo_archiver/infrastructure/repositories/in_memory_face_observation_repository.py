"""In-memory implementation of the face observation repository interface（阶段 C）."""

from collections.abc import Sequence
from uuid import UUID

from photo_archiver.domain.entities.face_observation import FaceObservation
from photo_archiver.domain.repositories.face_observation_repository import (
    FaceObservationRepository,
)


class InMemoryFaceObservationRepository(FaceObservationRepository):
    """Store face observations in memory（测试替身）.

    镜像 SQLite 的 ``UNIQUE(run_id, photo_id, face_index)``——重复即
    ``ValueError``（对应 SQLite 的 IntegrityError），防止测试替身静默
    接受 C-SEM-1 禁止的同 run 重复/覆盖。排序键用 ``str(UUID)`` 以对齐
    SQLite TEXT 列的字典序。
    """

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._observations: dict[UUID, FaceObservation] = {}

    def add_many(self, observations: Sequence[FaceObservation]) -> None:
        """批量插入；空输入 no-op；唯一性冲突整体拒绝（不落半批）。"""
        existing_keys = {
            (observation.run_id, observation.photo_id, observation.face_index)
            for observation in self._observations.values()
        }
        batch_keys: set[tuple[UUID, UUID, int]] = set()
        for observation in observations:
            key = (observation.run_id, observation.photo_id, observation.face_index)
            if key in existing_keys or key in batch_keys:
                raise ValueError(
                    "Duplicate face observation for "
                    f"(run_id, photo_id, face_index) = {key}"
                )
            batch_keys.add(key)
        for observation in observations:
            self._observations[observation.id] = observation

    def list_by_run(self, run_id: UUID) -> list[FaceObservation]:
        """Return the run's observations ordered by ``photo_id, face_index``."""
        return sorted(
            (
                observation
                for observation in self._observations.values()
                if observation.run_id == run_id
            ),
            key=lambda observation: (str(observation.photo_id), observation.face_index),
        )

    def list_by_run_photo(self, run_id: UUID, photo_id: UUID) -> list[FaceObservation]:
        """Return one photo's observations within a run, ordered by ``face_index``."""
        return sorted(
            (
                observation
                for observation in self._observations.values()
                if observation.run_id == run_id and observation.photo_id == photo_id
            ),
            key=lambda observation: observation.face_index,
        )

    def list_by_photo(self, photo_id: UUID) -> list[FaceObservation]:
        """Return the photo's observations across runs, ordered by ``run_id, face_index``."""
        return sorted(
            (
                observation
                for observation in self._observations.values()
                if observation.photo_id == photo_id
            ),
            key=lambda observation: (str(observation.run_id), observation.face_index),
        )
