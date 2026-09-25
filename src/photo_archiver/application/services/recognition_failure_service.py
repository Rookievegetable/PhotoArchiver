"""Recognition failure report service — Stage F（重试照片 + 失败清单导出）.

owner 批准执行计划 Stage F："提供历史照片「重新分析」入口 + 进度/失败
报告（读取失败清单导出，联动现有导出体系）。"

语义与边界：

- **可重试照片** = 该识别运行的输入快照（run_photos）中**未产出人脸
  观测**的照片。Stage C 的 run_photos 不持久化逐照片结果分类，无法从
  数据上区分"未读取/检测异常/无脸"——三者共同表现为此集合（Spec Gap
  已记录）；重跑这些照片无害且符合"重试"意图。
- **失败清单导出**为只读操作（不改变任何业务状态），CSV UTF-8-BOM
  （Excel 中文兼容），重复导出内容一致；与现有导出体系的关系：失败
  清单是运维工件，不进入 ExportService 的业务报表格式（其结构面向
  people/photos/recognition 报告），导出为独立 CSV 文件。
- 范围：识别运行级失败。聚类失败（cluster_run.error）与归档失败
  （archive_records FAILED）不在"读取失败清单"规格内——结构上可后续
  扩展同一服务。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from uuid import UUID

from loguru import logger

from photo_archiver.domain import RecognitionRunRepository

_FAILURE_CLASSIFICATION = "未产出人脸观测（未读取 / 检测异常 / 无脸）"
_CSV_HEADER = ("photo_id", "raw_path", "classification", "recognition_run_id")


@dataclass(frozen=True, slots=True)
class RecognitionFailureReport:
    """One recognition run's failure report（只读追溯视图）。"""

    run_id: UUID
    run_status: str
    input_photo_count: int
    observed_photo_count: int
    retryable_count: int
    run_face_count: int
    run_unreadable_count: int
    run_no_face_count: int
    run_error_count: int
    rows: tuple[dict[str, str], ...]

    @property
    def retryable_photo_ids(self) -> tuple[UUID, ...]:
        """Return the retryable photo ids in report row order."""
        return tuple(UUID(row["photo_id"]) for row in self.rows)


class RecognitionFailureService:
    """Derive retryable photos and failure reports for recognition runs."""

    def __init__(self, recognition_run_repository: RecognitionRunRepository,
                 face_observation_repository) -> None:
        self._run_repository = recognition_run_repository
        self._observation_repository = face_observation_repository

    def latest_resumable_run_id(self) -> UUID | None:
        """Return the newest terminal recognition run, or ``None``.

        created/running 运行不参与（其失败尚未最终）。
        """
        for run in self._run_repository.list_runs():
            if run.status in ("completed", "failed", "cancelled"):
                return run.id
        return None

    def report(self, run_id: UUID) -> RecognitionFailureReport:
        """Build the failure report for one recognition run."""
        run = self._run_repository.get_run(run_id)
        if run is None:
            raise ValueError(f"RecognitionRun {run_id} does not exist")
        assert run.id is not None
        input_photos = self._run_repository.list_run_photos(run.id)
        observed_photo_ids = {
            observation.photo_id
            for observation in self._observation_repository.list_by_run(run.id)
        }
        rows = tuple(
            {
                "photo_id": str(snapshot.photo_id),
                "raw_path": snapshot.raw_path,
                "classification": _FAILURE_CLASSIFICATION,
                "recognition_run_id": str(run.id),
            }
            for snapshot in input_photos
            if snapshot.photo_id not in observed_photo_ids
        )
        return RecognitionFailureReport(
            run_id=run.id,
            run_status=run.status,
            input_photo_count=len(input_photos),
            observed_photo_count=len(observed_photo_ids & {
                snapshot.photo_id for snapshot in input_photos
            }),
            retryable_count=len(rows),
            run_face_count=run.face_count,
            run_unreadable_count=run.unreadable_count,
            run_no_face_count=run.no_face_count,
            run_error_count=run.error_count,
            rows=rows,
        )

    def export_csv(self, run_id: UUID, path) -> int:
        """Export the failure list as UTF-8-BOM CSV（只读，不改业务状态）。

        重复导出内容一致（确定性列序与行序）。Returns 数据行数。
        """
        report = self.report(run_id)
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(_CSV_HEADER)
            for row in report.rows:
                writer.writerow([row[column] for column in _CSV_HEADER])
        logger.info(
            "RecognitionFailureService: exported {} failure row(s) for run {} to {}",
            len(report.rows), run_id, path,
        )
        return len(report.rows)
