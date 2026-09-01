"""Extension-based dispatch over the person import reader port (P0-3).

The import UI accepts both delimited text and Excel workbooks, while
``ImportPeopleService`` consumes a single ``PersonImportReader`` port. This
adapter keeps that single-port contract and routes to the concrete reader by
file extension, so both formats reach the real production import chain
without the service or Presentation knowing about file types.

Legacy ``.xls`` is intentionally NOT routed to the Excel reader: openpyxl
cannot read the binary .xls format, so such files would fail at parse time —
the import file picker no longer advertises it.
"""

from pathlib import Path

from photo_archiver.application.dtos import PersonImportRow
from photo_archiver.application.ports import PersonImportReader

# Extensions parsed by the openpyxl-backed reader; everything else goes to
# the delimited-text reader (which natively parses csv content).
_EXCEL_SUFFIXES = frozenset({".xlsx", ".xlsm"})


class DispatchingPersonImportReader(PersonImportReader):
    """Route person-import reads to the concrete reader by file extension."""

    def __init__(self, excel_reader: PersonImportReader, text_reader: PersonImportReader) -> None:
        """Initialize with the two concrete readers.

        Args:
            excel_reader: Reader for openpyxl-compatible workbooks.
            text_reader: Reader for delimited text/csv files.
        """
        self._excel_reader = excel_reader
        self._text_reader = text_reader

    def read(
        self,
        source_path: Path,
        *,
        has_header: bool = True,
        sheet_name: str | None = None,
    ) -> list[PersonImportRow]:
        """Read people, delegating to the reader matching the file extension.

        Args:
            source_path: Import file path; the suffix selects the reader.
            has_header: Passed through to the concrete reader.
            sheet_name: Passed through (only consumed by the Excel reader).
        """
        reader = (
            self._excel_reader
            if Path(source_path).suffix.lower() in _EXCEL_SUFFIXES
            else self._text_reader
        )
        return reader.read(source_path, has_header=has_header, sheet_name=sheet_name)
