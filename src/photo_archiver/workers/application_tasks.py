"""Worker task wrappers for application use cases."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from photo_archiver.application.commands import (
    ArchivePhotosCommand,
    ImportPeopleCommand,
    MatchPersonsCommand,
    StartClusteringRunCommand,
    StartRecognitionRunCommand,
    ScanAndRegisterPhotosCommand,
)
from photo_archiver.application.commands.pairing import (
    AssignClusterPersonCommand,
    ConfirmAssignmentCommand,
)
from photo_archiver.application.dtos import (
    ArchiveResult,
    ImportConfirmResult,
    ImportPeopleResult,
    MatchResult,
    ScanAndRegisterPhotosResult,
    ScanRegisterAnalyzeResult,
)
from photo_archiver.application.services.pairing_workbench_service import (
    PairingWorkbenchService,
)
from photo_archiver.application.use_cases import (
    ArchivePhotosUseCase,
    ClusterFacesUseCase,
    ImportPeopleUseCase,
    MatchPersonsUseCase,
    RunRecognitionUseCase,
    ScanAndRegisterPhotosUseCase,
)
from photo_archiver.domain import FaceClusterRun, RecognitionRun
from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR
from photo_archiver.workers.task import WorkerTask


class ImportPeopleTask(WorkerTask[ImportPeopleResult]):
    """Run the people import use case as a worker task."""

    def __init__(self, use_case: ImportPeopleUseCase, command: ImportPeopleCommand) -> None:
        """Initialize the task with its application use case and command."""
        super().__init__("import_people")
        self._use_case = use_case
        self._command = command

    def execute(self) -> ImportPeopleResult:
        """Execute the import use case and emit coarse progress updates."""
        self.raise_if_cancelled()
        self.report_progress("Importing people")
        result = self._use_case.execute(self._command)
        self.raise_if_cancelled()
        self.report_progress(
            "People import finished",
            current=result.imported_count + result.skipped_count,
            total=result.imported_count + result.skipped_count + len(result.errors),
        )
        return result


class ScanAndRegisterPhotosTask(WorkerTask[ScanAndRegisterPhotosResult]):
    """Run the scan-and-register photos use case as a worker task."""

    def __init__(
        self,
        use_case: ScanAndRegisterPhotosUseCase,
        command: ScanAndRegisterPhotosCommand,
    ) -> None:
        """Initialize the task with its application use case and command."""
        super().__init__("scan_and_register_photos")
        self._use_case = use_case
        self._command = command

    def execute(self) -> ScanAndRegisterPhotosResult:
        """Execute the scan use case with per-item progress streamed through the task.

        Capability-sniffs for ``bind_progress_reporter`` via ``getattr`` so the
        worker layer depends only on the ``ScanAndRegisterPhotosUseCase`` Protocol
        and the ``ProgressReporter`` port, never on a concrete service class.
        """
        self.raise_if_cancelled()
        self.report_progress("Scanning photos")
        binder = getattr(self._use_case, "bind_progress_reporter", None)
        if binder is not None:
            with binder(self):
                result = self._use_case.execute(self._command)
        else:
            result = self._use_case.execute(self._command)
        self.raise_if_cancelled()
        self.report_progress(
            "Photo scan finished",
            current=result.registered_count + result.skipped_count + result.failed_count,
            total=result.discovered_count,
        )
        return result


class ScanRegisterAnalyzeTask(WorkerTask[ScanRegisterAnalyzeResult]):
    """扫描即识别组合任务（任务书 §3 A1）：登记段 + 特征提取段。

    两段服务经 :meth:`bind_progress_reporter` 共享本任务作为 reporter——
    进度随阶段切换（登记 x/y → 特征 x/y），状态栏消息如实反映当前段。
    取消经任务基线 ``cancel`` 转发组合服务（拦分析段启动 + 转发识别用例）。
    """

    def __init__(self, use_case, command: ScanAndRegisterPhotosCommand) -> None:
        """Initialize with the combined use case and scan command."""
        super().__init__("scan_photos")
        self._use_case = use_case
        self._command = command

    def execute(self) -> ScanRegisterAnalyzeResult:
        """Execute the combined use case with per-item progress streaming."""
        self.raise_if_cancelled()
        self.report_progress("Scanning photos")
        binder = getattr(self._use_case, "bind_progress_reporter", None)
        if binder is not None:
            with binder(self):
                result = self._use_case.execute(self._command)
        else:
            result = self._use_case.execute(self._command)
        self.raise_if_cancelled()
        self.report_progress(
            "Scan and analyze finished",
            current=result.scan.registered_count + result.scan.skipped_count,
            total=max(1, result.scan.discovered_count),
        )
        return result

    def cancel(self, reason: str = "") -> None:
        super().cancel(reason)
        cancel = getattr(self._use_case, "cancel", None)
        if cancel is not None:
            cancel()


class ConfirmImportTask(WorkerTask[ImportConfirmResult]):
    """Confirm a draft import batch as a worker task (batches > 500 rows).

    Stage A of the people-import redesign: the confirmation writes people in
    one transaction; large rosters run off the UI thread through the shared
    worker executor while small ones confirm synchronously in the dialog.
    """

    def __init__(self, use_case, command) -> None:  # noqa: ANN001
        """Initialize with the confirm use case and the batch command."""
        super().__init__("import_confirm")
        self._use_case = use_case
        self._command = command

    def execute(self) -> "ImportConfirmResult":
        """Execute the confirmation and emit a finish progress marker."""
        self.raise_if_cancelled()
        self.report_progress("Confirming imported people")
        result = self._use_case.execute(self._command)
        self.raise_if_cancelled()
        self.report_progress(
            "Import confirmation finished",
            current=result.imported_count + result.merged_count,
            total=result.imported_count + result.merged_count + result.skipped_count,
        )
        return result


class MatchPersonsTask(WorkerTask[tuple[MatchResult, ...]]):
    """Run the face matching use case as a worker task.

    Streams per-photo progress by binding itself as the use case's
    ``ProgressReporter`` (capability-sniffed via ``getattr`` so the worker
    layer depends only on the ``MatchPersonsUseCase`` Protocol, never on a
    concrete service class). The service reports first/every-10th/last photo
    through the task's ``report`` adapter; the task adds coarse start and
    finish markers around the batch, matching the scan task precedent.
    """

    def __init__(
        self,
        use_case: MatchPersonsUseCase,
        command: MatchPersonsCommand,
    ) -> None:
        """Initialize the task with its application use case and command."""
        super().__init__("match_persons")
        self._use_case = use_case
        self._command = command

    def execute(self) -> tuple[MatchResult, ...]:
        """Execute the match use case with per-photo progress streamed through the task."""
        self.raise_if_cancelled()
        self.report_progress("Matching faces")
        binder = getattr(self._use_case, "bind_progress_reporter", None)
        if binder is not None:
            with binder(self):
                results = self._use_case.execute(self._command)
        else:
            results = self._use_case.execute(self._command)
        self.raise_if_cancelled()
        self.report_progress(
            "Face matching finished",
            current=len(results),
            total=len(results),
        )
        return results


class RunRecognitionTask(WorkerTask[RecognitionRun]):
    """Run a traceable recognition run and forward cooperative cancellation."""

    def __init__(self, use_case: RunRecognitionUseCase,
                 command: StartRecognitionRunCommand) -> None:
        super().__init__("run_recognition")
        self._use_case = use_case
        self._command = command

    def execute(self) -> RecognitionRun:
        self.raise_if_cancelled()
        self.report_progress("Starting recognition run")
        binder = getattr(self._use_case, "bind_progress_reporter", None)
        if binder is None:
            return self._use_case.execute(self._command)
        with binder(self):
            result = self._use_case.execute(self._command)
        self.raise_if_cancelled()
        self.report_progress("Recognition run finished", current=1, total=1)
        return result

    def cancel(self, reason: str = "") -> None:
        super().cancel(reason)
        cancel = getattr(self._use_case, "cancel", None)
        if cancel is not None:
            cancel()


class ClusterFacesTask(WorkerTask[FaceClusterRun]):
    """Run a face clustering execution and forward cooperative cancellation."""

    def __init__(self, use_case: ClusterFacesUseCase,
                 command: StartClusteringRunCommand) -> None:
        super().__init__("face_clustering")
        self._use_case = use_case
        self._command = command

    def execute(self) -> FaceClusterRun:
        self.raise_if_cancelled()
        self.report_progress("Clustering face observations")
        binder = getattr(self._use_case, "bind_progress_reporter", None)
        if binder is None:
            return self._use_case.execute(self._command)
        with binder(self):
            result = self._use_case.execute(self._command)
        self.raise_if_cancelled()
        self.report_progress("Face clustering finished", current=1, total=1)
        return result

    def cancel(self, reason: str = "") -> None:
        super().cancel(reason)
        cancel = getattr(self._use_case, "cancel", None)
        if cancel is not None:
            cancel()


class ArchivePhotosTask(WorkerTask[ArchiveResult]):
    """Run the archive photos use case as a worker task.

    Streams coarse two-phase progress: planning (unknown total) then executing
    (per-photo via the result's outcomes). Archive is a batch operation without
    a natural per-item event hook in Step 11's Planner/Executor split — the
    planner is side-effect free and the executor runs synchronously inside the
    service. This task therefore emits two coarse progress updates rather than
    streaming per-item, matching the ImportPeopleTask precedent.
    """

    def __init__(self, use_case: ArchivePhotosUseCase, command: ArchivePhotosCommand) -> None:
        """Initialize the task with its application use case and command."""
        super().__init__("archive_photos")
        self._use_case = use_case
        self._command = command

    def execute(self) -> ArchiveResult:
        """Execute the archive use case with coarse planning/executing progress."""
        self.raise_if_cancelled()
        self.report_progress("Planning archive")
        result = self._use_case.execute(self._command)
        self.raise_if_cancelled()
        archived_total = result.archived_count + result.skipped_count + result.dry_run_count
        self.report_progress(
            "Archive finished",
            current=archived_total,
            total=result.planned_count,
        )
        return result

# ── 批量终审（Owner 2026-10-31 卡顿修复·A：批量确认/批量通过下放后台线程）──


@dataclass(frozen=True)
class PairingBatchItem:
    """One plan entry（与对话框 _plan_confirm/_plan_batch_pass 条目同构）.

    ``action``：confirm（payload=建议行 id）/ promote（payload=本组当前指派
    人 id）/ assign（person_id=批量目标人员）/ skip（payload=原因）。
    """

    action: str
    cluster_id: UUID
    label: str
    payload: str | None = None
    person_id: str | None = None


@dataclass
class PairingBatchOutcome:
    """逐项提交后的批量结果（部分成功如实呈现，§3.3）。"""

    action: str
    succeeded: int
    skipped: int
    failed: int
    outcomes: tuple[str, ...]


class PairingBatchFinalizeTask(WorkerTask[PairingBatchOutcome]):
    """Execute a pairing batch (confirm / promote / assign) off the UI thread.

    每项独立提交（允许部分成功，§3.3 边界）；项间为协作式取消检查点；整批
    共享一个 :class:`PairingBatchContext` 读快照（Owner 2026-10-31 卡顿修复
    ·B：成员/观测/忽略名单一次加载，消 O(簇数×代际) 重载放大）。
    """

    def __init__(
        self,
        workbench: PairingWorkbenchService,
        items: Sequence[PairingBatchItem],
        action: str,
    ) -> None:
        super().__init__("pairing_batch")
        self._workbench = workbench
        self._items = tuple(items)
        self._action = action

    def execute(self) -> PairingBatchOutcome:
        """Run every plan item with a shared snapshot and per-item progress."""
        context = self._workbench.create_batch_context()
        succeeded = skipped = failed = 0
        outcomes: list[str] = []
        total = len(self._items)
        for index, item in enumerate(self._items, start=1):
            self.raise_if_cancelled()
            self.report_progress(item.label, current=index, total=total)
            try:
                if item.action == "confirm" and item.payload is not None:
                    self._workbench.confirm(
                        ConfirmAssignmentCommand(UUID(item.payload)),
                        context=context,
                    )
                elif item.action == "promote" and item.payload is not None:
                    self._workbench.assign_person(
                        AssignClusterPersonCommand(
                            cluster_id=item.cluster_id,
                            person_id=UUID(item.payload),
                        ),
                        actor=HUMAN_ACTOR,
                        context=context,
                    )
                elif item.action == "assign" and item.person_id is not None:
                    self._workbench.assign_person(
                        AssignClusterPersonCommand(
                            cluster_id=item.cluster_id,
                            person_id=UUID(item.person_id),
                        ),
                        actor=HUMAN_ACTOR,
                        context=context,
                    )
                else:
                    skipped += 1
                    continue
                succeeded += 1
            except Exception as exc:  # noqa: BLE001 - per-item boundary（§3.3）
                failed += 1
                outcomes.append(f"失败[{item.label}]: {exc}")
        return PairingBatchOutcome(
            action=self._action,
            succeeded=succeeded,
            skipped=skipped,
            failed=failed,
            outcomes=tuple(outcomes),
        )
