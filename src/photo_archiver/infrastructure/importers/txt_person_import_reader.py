"""TXT/CSV-style implementation of the person import reader port."""

import csv
from pathlib import Path

from photo_archiver.application.dtos import PersonImportRow
from photo_archiver.application.ports import PersonImportReader


class TxtPersonImportReader(PersonImportReader):
    """Read people from delimited text files."""

    def __init__(self, *, delimiter: str = ",", encoding: str = "utf-8-sig") -> None:
        """Initialize the reader with text parsing options."""
        self._delimiter = delimiter
        self._encoding = encoding

    def read(
        self,
        source_path: Path,
        *,
        has_header: bool = True,
        sheet_name: str | None = None,
    ) -> list[PersonImportRow]:
        """Read people from a TXT/CSV-style source file.

        The sheet_name argument is accepted for port compatibility with
        spreadsheet readers and intentionally ignored for delimited text files.
        """
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Person import file does not exist: {path}")
        if not path.is_file():
            raise IsADirectoryError(f"Person import path is not a file: {path}")

        rows: list[PersonImportRow] = []
        with path.open("r", encoding=self._encoding, newline="") as file:
            reader = csv.reader(file, delimiter=self._delimiter)
            for row_number, columns in enumerate(reader, start=1):
                if has_header and row_number == 1:
                    continue
                if self._is_blank_row(columns):
                    continue
                rows.append(self._build_row(columns, row_number))
        return rows

    @staticmethod
    def _is_blank_row(columns: list[str]) -> bool:
        """Return whether all columns are empty or whitespace."""
        return not any(column.strip() for column in columns)

    @staticmethod
    def _build_row(columns: list[str], row_number: int) -> PersonImportRow:
        """Build a normalized person import row from parsed columns."""
        padded_columns = [column.strip() for column in columns[:4]]
        padded_columns.extend([""] * (4 - len(padded_columns)))
        name, identity, department, note = padded_columns
        return PersonImportRow(
            name=name,
            identity=identity or None,
            department=department or None,
            note=note or None,
            row_number=row_number,
        )