"""扫描即识别组合服务（任务书 §3 A1）.

把"扫描文件夹"从"仅登记"升级为"登记 + 特征提取"两段一体的组合用例：

1. **登记段**：委托既有 :class:`ScanAndRegisterPhotosService`（枚举/登记/
   对账逻辑不变），结果携带新注册与内容更新照片 id；
2. **特征提取段**：计算增量集后委托既有 :class:`RunRecognitionUseCase`
   （检测/嵌入/观测/兼容审核行逻辑不变），**每次扫描产生一个识别运行**。

增量集（delta）= 新注册 ∪ 内容更新 ∪ {已登记照片中"最近一次处理结果"
未成功的照片} ∪ {从未进入任何运行的照片}。最近一次处理结果按运行
created_at 降序首个含该照片的 run_photos 行判定（与聚类数据集 resolver
同规则）；"未成功" = outcome ∈ (unreadable, error, not_processed) 或未知
（None）——不可读/出错照片由此在后续扫描中自动重试，模型缺失期登记的
照片在装好模型后的下次扫描自动补齐。

模型包缺失（识别用例为 None）时降级为仅登记并明示原因，不算失败。

取消语义：``cancel()`` 同时置本服务事件（拦在分析段启动前）并转发识别
用例（分析段进行中生效）。登记段无取消点（元数据读取，速度快）；在登记
段与识别 ``execute`` 清除其内部事件之间的极小窗口内请求的取消可能不生效，
再次取消即可——不为该窗口改造审计加固过的识别服务。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Event

from loguru import logger

from photo_archiver.application.commands import (
    ScanAndRegisterPhotosCommand,
    StartRecognitionRunCommand,
)
from photo_archiver.application.dtos import (
    ScanAndRegisterPhotosResult,
    ScanRegisterAnalyzeResult,
)
from photo_archiver.application.services.scan_and_register_photos_service import (
    ScanAndRegisterPhotosService,
)
from photo_archiver.domain import (
    FaceCountRange,
    PhotoRepository,
    RecognitionRunRepository,
)
from photo_archiver.domain.entities.recognition_run import (
    RUN_PHOTO_OUTCOME_ERROR,
    RUN_PHOTO_OUTCOME_NOT_PROCESSED,
    RUN_PHOTO_OUTCOME_UNREADABLE,
)

# 扫描期兼容审核行的脸数口径（任务书 D6）：仅单脸照片进入审核队列种子，
# 合影不产生识别行——与 Owner 现行实践一致。
_SCAN_COMPAT_RANGES: tuple[FaceCountRange, ...] = (FaceCountRange(1, 1),)

# 视为"需要重新提取"的最近处理结果。
_RETRY_OUTCOMES = frozenset({
    RUN_PHOTO_OUTCOME_UNREADABLE,
    RUN_PHOTO_OUTCOME_ERROR,
    RUN_PHOTO_OUTCOME_NOT_PROCESSED,
})


@dataclass(frozen=True, slots=True)
class _PendingAnalysis:
    """特征提取段输入：增量照片 id 与其原图路径快照。"""

    photo_ids: tuple
    images: tuple


class ScanRegisterAnalyzeService:
    """Scan a folder, register photos, then extract features for the delta."""

    def __init__(
        self,
        scan_service: ScanAndRegisterPhotosService,
        recognition_use_case,  # RunRecognitionUseCase | None（模型缺失时 None）
        photo_repository: PhotoRepository,
        recognition_run_repository: RecognitionRunRepository,
    ) -> None:
        """注入登记服务、识别用例（可缺省）与增量判定所需的只读端口."""
        self._scan_service = scan_service
        self._recognition = recognition_use_case
        self._photo_repository = photo_repository
        self._run_repository = recognition_run_repository
        self._cancel_event = Event()

    # ── 主线程预枚举（ADR-041 LIMIT-006 规避，透传登记服务） ────────────

    def enumerate_files(self, command: ScanAndRegisterPhotosCommand) -> list:
        """Enumerate candidate files on the main thread (delegates to scan)."""
        return self._scan_service.enumerate_files(command)

    # ── 取消（分析段生效；见模块 docstring 取消语义） ────────────────────

    def cancel(self) -> None:
        """Request cancellation: gate the analysis phase and forward in-flight."""
        self._cancel_event.set()
        cancel = getattr(self._recognition, "cancel", None)
        if cancel is not None:
            cancel()

    @property
    def analysis_available(self) -> bool:
        """Whether the recognition use case (model pack) is available."""
        return self._recognition is not None

    # ── 执行 ─────────────────────────────────────────────────────────────

    def execute(self, command: ScanAndRegisterPhotosCommand) -> ScanRegisterAnalyzeResult:
        """登记段 → 增量判定 → 特征提取段（识别用例可降级/跳过）。"""
        # 执行前已请求的取消必须生效（事件在 execute 内重建，先捕获状态）。
        cancelled_before_start = self._cancel_event.is_set()
        self._cancel_event = Event()
        scan_result: ScanAndRegisterPhotosResult = self._scan_service.execute(command)
        if scan_result.folder_id is None:
            # 登记整体失败（如目录枚举失败）：无本次登记增量可谈，且不应
            # 触发全库重试——原样返回。
            return ScanRegisterAnalyzeResult(
                scan=scan_result, analysis_skipped_reason="scan_failed",
            )
        if self._recognition is None:
            logger.warning(
                "ScanRegisterAnalyze: model pack unavailable - photos registered "
                "without feature extraction ({})",
                scan_result.registered_count + scan_result.updated_count,
            )
            return ScanRegisterAnalyzeResult(
                scan=scan_result, analysis_skipped_reason="model_unavailable",
            )
        if cancelled_before_start or self._cancel_event.is_set():
            return ScanRegisterAnalyzeResult(
                scan=scan_result, analysis_skipped_reason="cancelled",
            )
        pending = self._pending_analysis(scan_result)
        if not pending.photo_ids:
            return ScanRegisterAnalyzeResult(
                scan=scan_result, analysis_skipped_reason="no_pending_photos",
            )
        run = self._recognition.execute(StartRecognitionRunCommand(
            photo_ids=pending.photo_ids,
            images=pending.images,
            selected_ranges=_SCAN_COMPAT_RANGES,
            parameters={
                "photo_scope": "scan",
                "photo_count": len(pending.photo_ids),
                "folder_display_name": (
                    command.folder_display_name or command.folder_path.name
                ),
                "face_count_ranges": [
                    str(face_range) for face_range in _SCAN_COMPAT_RANGES
                ],
            },
        ))
        return ScanRegisterAnalyzeResult(
            scan=scan_result, analysis_attempted=True, recognition_run=run,
        )

    # ── 进度绑定（两段服务共用同一 reporter，worker 任务经此流式汇报） ──

    @contextmanager
    def bind_progress_reporter(self, reporter) -> Iterator[None]:
        """Bind the reporter to both phases for the duration of one execute."""
        with self._scan_service.bind_progress_reporter(reporter):
            binder = getattr(self._recognition, "bind_progress_reporter", None)
            if binder is not None:
                with binder(reporter):
                    yield
            else:
                yield

    # ── 增量判定 ─────────────────────────────────────────────────────────

    def _pending_analysis(self, scan_result: ScanAndRegisterPhotosResult) -> _PendingAnalysis:
        """登记段产物 ∪ 失败重试 ∪ 从未分析的照片 → (photo_ids, images)。"""
        pending_ids: set = set(scan_result.registered_photo_ids)
        pending_ids.update(scan_result.updated_photo_ids)
        latest_outcomes = self._latest_outcome_by_photo()
        for photo in self._photo_repository.list_all():
            if photo.id is None:
                continue
            if photo.id not in latest_outcomes:
                pending_ids.add(photo.id)  # 从未处理（含历史登记、模型缺失期登记）
                continue
            outcome = latest_outcomes[photo.id]
            if outcome is None or outcome in _RETRY_OUTCOMES:
                pending_ids.add(photo.id)  # 最近一次未成功（自动重试）
        photos = []
        for pending_id in sorted(pending_ids, key=str):
            record = self._photo_repository.find_by_id(pending_id)
            if record is not None:
                photos.append(record)
        return _PendingAnalysis(
            photo_ids=tuple(photo.id for photo in photos if photo.id is not None),
            images=tuple(photo.path.raw_path for photo in photos),
        )

    def _latest_outcome_by_photo(self) -> dict:
        """photo_id → 最近一次处理 outcome（运行 created_at 降序，首见即最新）。"""
        latest: dict = {}
        for run in self._run_repository.list_runs():
            if run.id is None:  # pragma: no cover - 实体恒生成 id
                continue
            for snapshot in self._run_repository.list_run_photos(run.id):
                if snapshot.photo_id is not None and snapshot.photo_id not in latest:
                    latest[snapshot.photo_id] = snapshot.photo_outcome
        return latest
