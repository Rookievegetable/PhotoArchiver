"""Recognition run repository interface（阶段 C）.

重跑语义（C-SEM-1）：``add_run`` 永远是新行插入——不存在"续跑"或
覆盖旧 run 的写路径；run 创建后的变更仅允许经 ``update_run`` 迁移
状态/统计，且 ``parameters`` 配置快照不可变（C-SEM-3）。
"""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities.recognition_run import RecognitionRun, RunPhotoSnapshot
from photo_archiver.domain.value_objects import FaceCountRange


class RecognitionRunRepository(Protocol):
    """Define persistence operations for recognition runs and their snapshots."""

    def add_run(self, run: RecognitionRun) -> None:
        """Persist a new run. 重跑 = 新行，绝不覆盖旧 run（C-SEM-1）。"""

    def get_run(self, run_id: UUID) -> RecognitionRun | None:
        """Return the run or ``None`` when it does not exist."""

    def list_runs(self) -> list[RecognitionRun]:
        """Return all runs, newest first (``created_at`` DESC, ``id`` ASC tiebreak)."""

    def update_run(self, run: RecognitionRun) -> int:
        """Persist the run's mutable fields (status/统计列/finished_at/error).

        ``parameters`` 配置快照不可变（C-SEM-3）——本方法刻意不更新
        parameters 列；运行结果统计只写独立统计列。

        Returns:
            The number of rows affected (1 on hit, 0 when the run id is
            missing). Callers SHOULD treat 0 as a concurrent-deletion signal
            rather than silently assuming success.
        """

    def add_run_photos(self, run_id: UUID, snapshots: Sequence[RunPhotoSnapshot]) -> None:
        """保存 run 创建时的照片输入快照（一次写入，之后不增不改）。空输入 no-op。"""

    def update_run_photo_outcome(self, run_id: UUID, photo_id: UUID, outcome: str) -> int:
        """Update one snapshot photo's processing outcome（界面优化 §6.2）.

        状态只来自实际处理分支（faces/no_face/unreadable/error），快照写入
        时即登记 ``not_processed``；历史 run 的 NULL 保持未知，不伪造回填。

        Returns:
            1 on hit, 0 when the snapshot row is missing (concurrent deletion).
        """

    def add_run_scopes(self, run_id: UUID, ranges: Sequence[FaceCountRange]) -> None:
        """保存 run 选中的人脸数范围（按传入顺序赋 ordinal，一次写入）。空输入 no-op。"""

    def list_run_photos(self, run_id: UUID) -> list[RunPhotoSnapshot]:
        """Return the run's photo snapshots in write (submission) order."""

    def list_run_scopes(self, run_id: UUID) -> list[FaceCountRange]:
        """Return the run's selected face-count ranges ordered by ``ordinal``."""
