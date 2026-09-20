"""Concrete roster table reader — encoding/delimiter resolution per file type.

People-import redesign stage A (owner plan §4.1, decisions D1/D2):

- ``.xlsx``/``.xlsm`` via openpyxl (existing dependency);
- ``.xls`` via ``xlrd`` (D1: owner approved the new dependency);
- text (``.csv``/``.tsv``/``.txt``/fallback) via an encoding ladder — BOM-aware
  ``utf-8-sig``/``utf-16`` first, then ``utf-8``/``gb18030`` trial decode,
  ``latin-1`` as the never-failing last resort (D2: no new dependency);
- delimiter detection by frequency among ``,``/``\\t``/``;`` over the leading
  lines, comma as fallback.
"""

import csv
from pathlib import Path

from photo_archiver.application.dtos.import_draft import RawRosterTable

EXCEL_SUFFIXES = frozenset({".xlsx", ".xlsm"})
XLS_SUFFIXES = frozenset({".xls"})
TEXT_SUFFIXES = frozenset({".csv", ".tsv", ".txt"})

_ENCODING_LADDER = ("utf-8", "gb18030", "utf-16-le", "utf-16-be", "latin-1")
_DELIMITER_CANDIDATES = (",", "\t", ";")
_MAX_DETECT_LINES = 10

_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"


def _decode_text(raw: bytes) -> str:
    """Decode bytes through the BOM-aware ladder (D2).

    BOMs decide outright; without a BOM the ladder runs strict decodes from
    the most common to the most permissive (``latin-1`` never fails). A bare
    ``utf-16`` pass is deliberately NOT in the ladder — without a BOM it
    happily decodes GB18030/UTF-8 bytes into garbage instead of failing.
    """
    if raw.startswith(_UTF8_BOM):
        return raw.decode("utf-8-sig")
    if raw.startswith(_UTF16_LE_BOM) or raw.startswith(_UTF16_BE_BOM):
        return raw.decode("utf-16")
    for encoding in _ENCODING_LADDER:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("latin-1")


def _detect_delimiter(lines: list[str]) -> str:
    """Pick the most frequent candidate delimiter over the leading lines."""
    sample = "\n".join(lines[:_MAX_DETECT_LINES])
    best, best_count = ",", 0
    for candidate in _DELIMITER_CANDIDATES:
        count = sample.count(candidate)
        if count > best_count:
            best, best_count = candidate, count
    return best


def _split_lines(text: str) -> list[str]:
    """Split decoded text into non-empty cell rows (no delimiter chosen yet)."""
    return [line for line in text.splitlines() if line.strip()]


class FileRosterTableReader:
    """Read roster files into raw tables by extension (stage A)."""

    def list_sheets(self, source_path: Path) -> tuple[str, ...]:
        """List worksheet names of a workbook; empty for text files."""
        path = Path(source_path)
        suffix = path.suffix.lower()
        try:
            if suffix in EXCEL_SUFFIXES:
                from openpyxl import load_workbook

                workbook = load_workbook(path, read_only=True)
                try:
                    return tuple(workbook.sheetnames)
                finally:
                    workbook.close()
            if suffix in XLS_SUFFIXES:
                import xlrd  # type: ignore[import-untyped]  # no stubs published

                book = xlrd.open_workbook(str(path))
                try:
                    return tuple(book.sheet_names())
                finally:
                    book.release_resources()
        except Exception:  # noqa: BLE001  探测失败返回空，导入主流程会给出明确错误
            return ()
        return ()

    def read_raw(
        self,
        source_path: Path,
        *,
        has_header: bool = True,
        sheet_name: str | None = None,
    ) -> RawRosterTable:
        """Dispatch on the file suffix; unknown suffixes go to the text path."""
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Roster file does not exist: {path}")
        suffix = path.suffix.lower()
        if suffix in EXCEL_SUFFIXES:
            return self._read_excel(path, has_header, sheet_name)
        if suffix in XLS_SUFFIXES:
            return self._read_xls(path, has_header, sheet_name)
        return self._read_text(path, has_header)

    def _read_excel(self, path: Path, has_header: bool, sheet_name: str | None) -> RawRosterTable:
        """Read .xlsx/.xlsm via openpyxl (values-only, active or named sheet)."""
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            worksheet = (
                workbook[sheet_name] if sheet_name is not None else workbook.active
            )
            grid: list[list[str]] = [
                ["" if value is None else str(value).strip() for value in row]
                for row in worksheet.iter_rows(values_only=True)
            ]
        finally:
            workbook.close()
        return self._finalize(grid, "xlsx", encoding=None, delimiter=None,
                              sheet_name=sheet_name or (worksheet.title if worksheet else None),
                              has_header=has_header)

    def _read_xls(self, path: Path, has_header: bool, sheet_name: str | None) -> RawRosterTable:
        """Read legacy .xls via xlrd (D1: owner-approved dependency)."""
        import xlrd  # type: ignore[import-untyped]  # no stubs published

        book = xlrd.open_workbook(str(path))
        try:
            worksheet = (
                book.sheet_by_name(sheet_name) if sheet_name is not None else book.sheet_by_index(0)
            )
            grid = []
            for row_index in range(worksheet.nrows):
                grid.append([
                    self._xls_cell(worksheet.cell_value(row_index, col_index))
                    for col_index in range(worksheet.ncols)
                ])
        finally:
            book.release_resources()
        return self._finalize(grid, "xls", encoding=None, delimiter=None,
                              sheet_name=sheet_name or book.sheet_names()[0],
                              has_header=has_header)

    @staticmethod
    def _xls_cell(value) -> str:  # noqa: ANN001
        """Normalize an xlrd cell value into display text."""
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    def _read_text(self, path: Path, has_header: bool) -> RawRosterTable:
        """Read delimited text through the encoding ladder (D2)."""
        text = _decode_text(path.read_bytes())
        lines = _split_lines(text)
        delimiter = _detect_delimiter(lines)
        grid = [row for row in csv.reader(lines, delimiter=delimiter) if any(cell.strip() for cell in row)]
        return self._finalize(grid, path.suffix.lower().lstrip(".") or "txt",
                              encoding="auto", delimiter=delimiter,
                              sheet_name=None, has_header=has_header)

    @staticmethod
    def _finalize(
        grid: list[list[str]],
        source_type: str,
        *,
        encoding: str | None,
        delimiter: str | None,
        sheet_name: str | None,
        has_header: bool,
    ) -> RawRosterTable:
        """Split the grid into header/rows and drop fully blank lines."""
        grid = [row for row in grid if any(cell for cell in row)]
        if not grid:
            return RawRosterTable(source_type=source_type, header=None, rows=[],
                                  encoding=encoding or "", delimiter=delimiter,
                                  sheet_name=sheet_name)
        if has_header:
            return RawRosterTable(source_type=source_type, header=grid[0],
                                  rows=grid[1:], encoding=encoding or "",
                                  delimiter=delimiter, sheet_name=sheet_name)
        return RawRosterTable(source_type=source_type, header=None, rows=grid,
                              encoding=encoding or "", delimiter=delimiter,
                              sheet_name=sheet_name)
