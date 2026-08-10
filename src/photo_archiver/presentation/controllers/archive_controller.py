"""Controller coordinating the archive workflow with the UI.

落 Phase 2 Step 12 裁决 #3：ArchivePlanner/Executor 拆分让 UI 可先调 plan()
预览再调 execute() 落盘。本 controller 呈两个方法对应两段：
    preview() → 调 planner.plan() 返回 ArchivePlan（同步，快，无 IO 副作用）
    execute() → 包 ArchivePhotosTask 走 QtWorkerExecutor 后台跑（长耗时）

preview 不走 Worker 是因为 planner 是纯领域计算 + 仓储只读，<50ms 可同步；
execute 走 Worker 是因为 executor 真碰文件系统 copy，数百张照片时秒级。
"""

from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QObject, Slot

from photo_archiver.application import ArchivePhotosCommand, ArchivePhotosUseCase
from photo_archiver.application.dtos import ArchivePlan
from photo_archiver.workers import ArchivePhotosTask, QtWorkerExecutor


class ArchiveController(QObject):
    """Bridge archive use case requests to worker execution with plan-preview support.

    review M-3 fix: holds the ArchivePhotosUseCase Protocol only (not the
    concrete ArchivePlanner), so presentation → application dependencies stay
    at the Protocol boundary per DEP-010. preview() delegates to the use
    case's preview method which the service implements via its planner.
    """

    def __init__(
        self,
        use_case: ArchivePhotosUseCase,
        executor: QtWorkerExecutor,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with its use case and worker executor.

        Args:
            use_case: ArchivePhotosUseCase — preview() + execute() both delegate here.
            executor: QtWorkerExecutor to run the archive task off the UI thread.
        """
        super().__init__(parent)
        self._use_case = use_case
        self._executor = executor

    def preview(
        self,
        archive_root: Path,
        person_ids: tuple[UUID, ...] = (),
        photo_ids: tuple[UUID, ...] = (),
    ) -> ArchivePlan:
        """Synchronously plan the archive and return the plan for UI preview.

        Delegates to the UseCase's preview method — no worker submission, no
        filesystem mutation. The UI can inspect the returned ArchivePlan
        before deciding whether to call execute(). B3 透 photo_ids 入 preview
        批量归档路径（用户多选的 photos 直下推 plan 过滤）。
        """
        return self._use_case.preview(
            archive_root=str(archive_root),
            person_ids=person_ids,
            photo_ids=photo_ids,
        )

    def execute(
        self,
        archive_root: Path,
        person_ids: tuple[UUID, ...] = (),
        photo_ids: tuple[UUID, ...] = (),
        conflict_strategy: str | None = None,
        dry_run: bool = False,
    ):
        """Start an archive task and return its runnable handle.

        The returned runnable exposes a ``signals`` attribute the caller uses
        to connect UI slots via :meth:`connect_signals`. B3 透 photo_ids 入
        ArchivePhotosCommand 批量归档路径。
        """
        command = ArchivePhotosCommand(
            archive_root=archive_root,
            person_ids=person_ids,
            photo_ids=photo_ids,
            conflict_strategy=conflict_strategy,
            dry_run=dry_run,
        )
        task = ArchivePhotosTask(self._use_case, command)
        return self._executor.submit(task)  # type: ignore[arg-type]  # WorkerTask[ArchiveResult] vs [object] generics variance

    @staticmethod
    def connect_signals(runnable, started: Slot, progress: Slot, completed: Slot, failed: Slot) -> None:
        """Connect the runnable's task signals to the provided UI slots."""
        signals = runnable.signals
        signals.started.connect(started)
        signals.progress.connect(progress)
        signals.completed.connect(completed)
        signals.failed.connect(failed)
