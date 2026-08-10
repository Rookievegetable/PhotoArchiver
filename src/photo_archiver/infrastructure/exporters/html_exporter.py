"""HTML exporter for phase B4 export extension.

零依赖导出器（裁决 B4-a 已拍板：先做 HTML 零依赖档；PDF 后续单独裁决）。
仅用 stdlib ``html.escape`` 转义防 XSS + ``string.Template`` 模板替注入，
无 Jinja2/BeautifulSoup 等三方依赖，与 CsvExporter 同模式同步走 Exporter Protocol。

输出结构：单文件 ``<table>`` 含 header + 数据行，UTF-8 编码，可直浏览器打开。
"""

from html import escape
from pathlib import Path
from string import Template

from photo_archiver.application.ports.exporter import ExportRow


class HtmlExporter:
    """Write export rows to a UTF-8 ``.html`` file with one ``<table>``.

    Zero third-party dependency: only stdlib ``html.escape`` (XSS hardening) +
    ``string.Template`` (placeholder substitution). Implements the ``Exporter``
    Protocol defined in ``application/ports/exporter.py`` so ExportService can
    inject it polymorphically without code change.

    Column order coupling（review Minor-2 fix 文档化）：
        ``_HEADERS`` 列名顺序与 ``_to_row`` 字段顺序必须手工对齐——改一处必
        改另一处，否则表头与数据列错位。当前无机制守护（如 dataclass fields
        直取），后续轮可改用 ``dataclasses.fields(ExportRow)`` 直取消耦。
    """

    _HEADERS = [
        "person_name",
        "department",
        "note",
        "photo_path",
        "original_name",
        "folder",
        "captured_at",
        "match_confidence",
        "match_status",
        "archive_status",
        "archive_target",
        "archived_at",
    ]

    # 单文件骨架：DOCTYPE + <table> + header + 行槽。每行经 html.escape 转义
    # 防 XSS——ExportRow 字段含用户输入（person_name/photo_original_name），
    # 不转义会致注入。$row 占位由 string.Template 安全替（非 str.format % 转义歧义）。
    _DOCUMENT_TEMPLATE = Template(
        """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PhotoArchiver Export</title>
<style>
body { font-family: sans-serif; }
table { border-collapse: collapse; }
th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: left; }
th { background: #f0f0f0; }
tr:nth-child(even) { background: #fafafa; }
</style>
</head>
<body>
<h1>PhotoArchiver Export</h1>
<table>
<thead>
<tr>$header</tr>
</thead>
<tbody>
$rows
</tbody>
</table>
</body>
</html>
""",
    )

    _ROW_TEMPLATE = Template("<tr>$cells</tr>\n")
    _CELL_TEMPLATE = Template("<td>$value</td>")

    def export(self, rows: list[ExportRow], output_path: str) -> str:
        """Write rows as a single-table HTML document.

        Args:
            rows: Flattened export rows assembled by the application layer.
            output_path: Where the HTML file should be written.

        Returns:
            A human-readable summary (e.g. "Exported 42 rows to /tmp/report.html").

        Raises:
            OSError: When the output path is unwritable.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        header_cells = "".join(self._CELL_TEMPLATE.substitute(value=escape(h)) for h in self._HEADERS)
        body = "".join(self._render_row(row) for row in rows)
        document = self._DOCUMENT_TEMPLATE.substitute(header=header_cells, rows=body)

        with open(str(out), "w", encoding="utf-8") as f:
            f.write(document)

        return f"Exported {len(rows)} rows to {out}"

    def _render_row(self, row: ExportRow) -> str:
        """Render one ExportRow as a ``<tr>`` with escaped ``<td>`` cells."""
        values = self._to_row(row)
        cells = "".join(
            self._CELL_TEMPLATE.substitute(value=escape(self._format_cell(v))) for v in values
        )
        return self._ROW_TEMPLATE.substitute(cells=cells)

    @staticmethod
    def _format_cell(value: object) -> str:
        """Render a cell value to its display string; None → empty (no "None")."""
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _to_row(row: ExportRow) -> list[object]:
        """Flatten an ExportRow into a header-aligned list (object covers float | None)."""
        return [
            row.person_name,
            row.person_department,
            row.person_note,
            row.photo_path,
            row.photo_original_name,
            row.photo_folder,
            row.photo_captured_at,
            row.match_confidence,
            row.match_status,
            row.archive_status,
            row.archive_target,
            row.archive_archived_at,
        ]
