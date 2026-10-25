"""In-memory implementation of the recognition run repository interface（阶段 C）."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from photo_archiver.domain.entities.recognition_run import RecognitionRun, RunPhotoSnapshot
from photo_archiver.domain.repositories.recognition_run_repository import (
    RecognitionRunRepository,
)
from photo_archiver.domain.value_objects import FaceCountRange


class InMemoryRecognitionRunRepository(RecognitionRunRepository):
    """Store recognition runs in memory（测试替身）.

    不模拟 FK 级联（ADR-034 §4.4：级联语义的唯一裁判是真实 SQLite 集成
    测试）；排序契约与 SQLite 实现保持一致，由对照测试守护。
    """

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._runs: dict[UUID, RecognitionRun] = {}
        self._photos: dict[UUID, list[RunPhotoSnapshot]] = {}
        self._scopes: dict[UUID, list[FaceCountRange]] = {}

    def add_run(self, run: RecognitionRun) -> None:
        """Persist a run entity in memory."""
        self._runs[run.id] = run  # type: ignore[index]  # UUID | None guarantee

    def get_run(self, run_id: UUID) -> RecognitionRun | None:
        """Return the run or ``None`` when it does not exist."""
        return self._runs.get(run_id)

    def list_runs(self) -> list[RecognitionRun]:
        """Return all runs, newest first——与 SQLite 的 created_at DESC, id ASC 对齐."""
        # 两段稳定排序：先按 id（TEXT 形式与 SQLite TEXT 排序一致）升序，
        # 再按 created_at 降序——等价于 SQLite 的 ORDER BY created_at DESC, id。
        runs = sorted(self._runs.values(), key=lambda run: str(run.id))
        runs.sort(
            key=lambda run: run.created_at if run.created_at is not None else datetime.min,
            reverse=True,
        )
        return runs

    def update_run(self, run: RecognitionRun) -> int:
        """Replace the stored run；幂等：id 不存在返回 0。"""
        if run.id not in self._runs:
            return 0
        self._runs[run.id] = run  # type: ignore[index]  # membership check above
        return 1

    def add_run_photos(self, run_id: UUID, snapshots: Sequence[RunPhotoSnapshot]) -> None:
        """Append the run's photo snapshots（保持写入顺序）."""
        self._photos.setdefault(run_id, []).extend(snapshots)

    def update_run_photo_outcome(
        self, run_id: UUID, photo_id: UUID, outcome: str,
    ) -> int:
        """Update one snapshot photo's processing outcome（界面优化 §6.2）."""
        snapshots = self._photos.get(run_id, [])
        for index, snapshot in enumerate(snapshots):
            if snapshot.photo_id == photo_id:
                updated = RunPhotoSnapshot(
                    run_id=snapshot.run_id,
                    photo_id=snapshot.photo_id,
                    raw_path=snapshot.raw_path,
                    captured_at=snapshot.captured_at,
                    photo_outcome=outcome,
                )
                snapshots[index] = updated
                return 1
        return 0

    def add_run_scopes(self, run_id: UUID, ranges: Sequence[FaceCountRange]) -> None:
        """Append the run's selected ranges（ordinal = 传入顺序）."""
        self._scopes.setdefault(run_id, []).extend(ranges)

    def list_run_photos(self, run_id: UUID) -> list[RunPhotoSnapshot]:
        """Return the run's photo snapshots in write order."""
        return list(self._photos.get(run_id, []))

    def list_run_scopes(self, run_id: UUID) -> list[FaceCountRange]:
        """Return the run's selected ranges in write (ordinal) order."""
        return list(self._scopes.get(run_id, []))
