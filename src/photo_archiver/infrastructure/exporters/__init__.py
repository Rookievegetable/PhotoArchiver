"""Exporter adapters for Step 14 Export + phase B4 HTML extension.

Concrete Exporter implementations (Excel/CSV/HTML) live here in the Infrastructure
layer. They implement the ``Exporter`` protocol defined in
``application/ports/exporter.py``. HTML adapter added in B4 (裁决 B4-a 已拍板：
零依赖 stdlib html.escape + string.Template；PDF 后续单独裁决)。
"""

from photo_archiver.infrastructure.exporters.csv_exporter import CsvExporter
from photo_archiver.infrastructure.exporters.excel_exporter import ExcelExporter
from photo_archiver.infrastructure.exporters.html_exporter import HtmlExporter

__all__ = [
    "CsvExporter",
    "ExcelExporter",
    "HtmlExporter",
]
