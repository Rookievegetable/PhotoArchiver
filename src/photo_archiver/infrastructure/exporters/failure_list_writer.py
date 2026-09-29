"""CSV implementation of the failure list writer port（AUD-010）.

渲染细节（UTF-8-BOM——Excel 中文友好、csv 方言、确定性列序）归
Infrastructure；行结构与列序由服务层定义。重复写入内容逐字节一致
（既有确定性导出语义，Stage F）。
"""

import csv
from pathlib import Path
from typing import Sequence

from photo_archiver.application.ports import FailureListWriter


class CsvFailureListWriter(FailureListWriter):
    """UTF-8-BOM CSV failure list writer."""

    def write_failure_list(
        self,
        path: Path,
        header: Sequence[str],
        rows: Sequence[Sequence[str]],
    ) -> None:
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for row in rows:
                writer.writerow(row)
