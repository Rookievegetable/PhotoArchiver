"""Failure list writer port — persist the recognition failure report.

AUD-010（Stage 12E）：识别失败清单的用户可见导出（UTF-8-BOM CSV，Excel
友好）是基础设施渲染职责——服务层定义行结构与确定性列序，本端口承载
落盘能力；实现位于 ``infrastructure/exporters``。重复写入内容必须一致
（确定性导出语义，见 RecognitionFailureService.export_csv）。
"""

from pathlib import Path
from typing import Protocol, Sequence


class FailureListWriter(Protocol):
    """Write one failure-list report as a user-facing CSV file."""

    def write_failure_list(
        self,
        path: Path,
        header: Sequence[str],
        rows: Sequence[Sequence[str]],
    ) -> None:
        """Write ``header`` + ``rows`` to ``path`` (deterministic, Excel-friendly).

        Implementations must overwrite existing files and keep repeated
        writes byte-identical for identical inputs.
        """
        ...
