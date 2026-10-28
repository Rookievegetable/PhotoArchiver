"""DTOs for scan-and-register photo workflows."""

from dataclasses import dataclass, field
from uuid import UUID

from photo_archiver.domain import RecognitionRun


@dataclass(frozen=True, slots=True)
class ScanAndRegisterPhotosResult:
    """Outcome of scanning a folder and registering discovered photos."""

    folder_id: UUID | None = None
    discovered_count: int = 0
    registered_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)
    # 扫描即识别（任务书 §3 A1）：本次登记中"新注册 / 内容更新"的照片 id，
    # 供组合服务计算特征提取增量集；缺省空元组保持旧构造点兼容。
    registered_photo_ids: tuple[UUID, ...] = ()
    updated_photo_ids: tuple[UUID, ...] = ()

    @property
    def succeeded(self) -> bool:
        """Return whether the workflow completed without item-level failures."""
        return not self.errors


@dataclass(frozen=True, slots=True)
class ScanRegisterAnalyzeResult:
    """扫描即识别组合结果（任务书 §3 A1）：登记段 + 特征提取段。

    ``analysis_*`` 字段描述特征提取段的执行情况：

    - ``analysis_attempted``：是否实际执行了检测/嵌入（模型可用且增量非空）；
    - ``analysis_skipped_reason``：未执行原因（``model_unavailable`` /
      ``no_pending_photos`` / ``cancelled``），执行过则为 ``None``；
    - ``recognition_run``：本次扫描产生的识别运行（未执行分析时 ``None``）。
    """

    scan: ScanAndRegisterPhotosResult
    analysis_attempted: bool = False
    analysis_skipped_reason: str | None = None
    recognition_run: RecognitionRun | None = None

    @property
    def analyzed_photo_count(self) -> int:
        """本次特征提取实际处理的照片数（run 统计；未运行为 0）。

        口径 = run 照片级 outcome 计数之和（范围内/范围外有脸 + 无脸 +
        不可读 + 出错）；``face_count`` 是脸数不是照片数，不参与。
        run 实体把统计平铺为属性（缺 counters 的替身按 0 计）。
        """
        run = self.recognition_run
        if run is None:
            return 0
        return int(sum(
            getattr(run, name, 0)
            for name in (
                "in_scope_photo_count", "out_of_scope_photo_count",
                "no_face_count", "unreadable_count", "error_count",
            )
        ))
