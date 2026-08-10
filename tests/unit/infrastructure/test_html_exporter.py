"""Unit tests for HtmlExporter — phase B4 HTML export (零依赖导出器).

覆盖：
- 输出文件可打开（UTF-8 HTML 文档 + DOCTYPE + <table>）
- 字段完整（12 列 header + 行数据对齐 ExportRow）
- XSS 转义安全（person_name/photo_original_name 含 <script> 经 html.escape 转义）
- None 字段渲染为空字符串（非 "None"）
- 返回 summary 字符串含行数 + 路径
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from photo_archiver.application.ports.exporter import ExportRow
from photo_archiver.infrastructure.exporters import HtmlExporter


def _make_row(
    person_name: str = "Alice",
    photo_original_name: str | None = "a.jpg",
    match_confidence: float | None = 0.95,
) -> ExportRow:
    """Build a minimal ExportRow for HtmlExporter tests."""
    return ExportRow(
        person_name=person_name,
        person_department="Eng",
        person_note="note",
        photo_path="/src/a.jpg",
        photo_original_name=photo_original_name,
        photo_folder="/src",
        photo_captured_at="2024-05-01",
        match_confidence=match_confidence,
        match_status="approved",
        archive_status="planned",
        archive_target="/archive/Alice/a.jpg",
        archive_archived_at="2024-06-01",
    )


def test_html_exporter_writes_openable_utf8_html_document(tmp_path: Path) -> None:
    """输出文件是 UTF-8 HTML 文档含 DOCTYPE + <table>，可浏览器打开。"""
    exporter = HtmlExporter()
    out = tmp_path / "report.html"

    summary = exporter.export([_make_row()], str(out))

    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert content.startswith("<!DOCTYPE html>")
    assert "<table>" in content
    assert "</table>" in content
    assert "charset=\"utf-8\"" in content
    assert "Exported 1 rows" in summary
    assert str(out) in summary


def test_html_exporter_headers_complete_12_columns(tmp_path: Path) -> None:
    """HTML 含全部 12 列 header（与 CSV/Excel exporter 对齐）。"""
    exporter = HtmlExporter()
    out = tmp_path / "report.html"

    exporter.export([_make_row()], str(out))
    content = out.read_text(encoding="utf-8")

    expected_headers = [
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
    for h in expected_headers:
        assert h in content, f"header '{h}' missing in HTML output"


def test_html_exporter_escapes_xss_in_user_fields(tmp_path: Path) -> None:
    """person_name/photo_original_name 含 <script> 经 html.escape 转义防 XSS."""
    exporter = HtmlExporter()
    out = tmp_path / "report.html"

    evil_row = _make_row(
        person_name="<script>alert('xss')</script>",
        photo_original_name="<img src=x onerror=alert(1)>",
    )
    exporter.export([evil_row], str(out))
    content = out.read_text(encoding="utf-8")

    # 原始恶意标签不得直现——必经 html.escape 转成 &lt;script&gt; 等。
    assert "<script>alert('xss')</script>" not in content
    assert "&lt;script&gt;" in content
    assert "<img src=x onerror=alert(1)>" not in content
    assert "&lt;img" in content


def test_html_exporter_none_fields_render_empty_not_literal_none(tmp_path: Path) -> None:
    """None 字段渲染为空字符串，非字面量 "None"."""
    exporter = HtmlExporter()
    out = tmp_path / "report.html"

    row = _make_row(photo_original_name=None, match_confidence=None)
    exporter.export([row], str(out))
    content = out.read_text(encoding="utf-8")

    # "None" 字面量不得现于 <td>——None → "" 经 _format_cell。
    assert ">None<" not in content


def test_html_exporter_empty_rows_yields_table_with_header_only(tmp_path: Path) -> None:
    """空 rows 输出含 header 行 + 空 tbody（非崩溃，非空文件）。"""
    exporter = HtmlExporter()
    out = tmp_path / "report.html"

    summary = exporter.export([], str(out))
    content = out.read_text(encoding="utf-8")

    assert out.exists()
    assert "<table>" in content
    assert "<thead>" in content
    # 空 tbody：$rows 替空字符串后模板里 \n 残留，断言含 tbody 标签即可。
    assert "<tbody>" in content and "</tbody>" in content
    assert "Exported 0 rows" in summary


def test_html_exporter_creates_parent_directory(tmp_path: Path) -> None:
    """output_path 父目录不存在时 exporter 自动 mkdir 创建。"""
    exporter = HtmlExporter()
    nested = tmp_path / "nested" / "dir" / "report.html"

    exporter.export([_make_row()], str(nested))
    assert nested.exists()


def test_html_exporter_implements_exporter_protocol() -> None:
    """HtmlExporter 满足 Exporter Protocol 夰 export(rows, output_path) → str."""
    from photo_archiver.application.ports.exporter import Exporter

    exporter: Exporter = HtmlExporter()  # type: ignore[assignment]
    with TemporaryDirectory() as td:
        result = exporter.export([], str(Path(td) / "x.html"))
    assert isinstance(result, str)
