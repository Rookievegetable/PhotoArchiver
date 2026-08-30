"""Excel exporter for Step 14 Export.

Uses openpyxl (already in ``requirements/base.txt``, DEP-032) to write a
single-sheet workbook from flattened :class:`ExportRow` data. The exporter
exists solely in the Infrastructure layer and is never imported in
Domain, Application, or Presentation.
"""

from pathlib import Path

from openpyxl import Workbook

from photo_archiver.application.ports.exporter import ExportRow
from photo_archiver.infrastructure.exporters._spreadsheet_safety import (
    sanitize_spreadsheet_cell,
)


class ExcelExporter:
    """Write export rows to an ``.xlsx`` workbook."""

    _HEADERS = [
        "Person Name",
        "Department",
        "Note",
        "Photo Path",
        "Original Name",
        "Folder",
        "Captured At",
        "Match Confidence",
        "Match Status",
        "Archive Status",
        "Archive Target",
        "Archived At",
    ]

    def export(self, rows: list[ExportRow], output_path: str) -> str:
        """Write rows to a single-sheet Excel workbook.

        Each row becomes one worksheet row; the first row is the header.
        The workbook uses auto-dimensions for readability.
        """
        wb = Workbook()
        ws = wb.active
        ws.title = "Export"

        ws.append(self._HEADERS)

        for row in rows:
            ws.append(self._to_row(row))

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(out))

        return f"Exported {len(rows)} rows to {out}"

    @staticmethod
    def _to_row(row: ExportRow) -> list[str | float | None]:
        """Flatten an ExportRow into a header-aligned list.

        P2-003 fix: string cells pass through formula-injection sanitization
        so opening the workbook cannot execute injected formulas from
        user-controlled fields (``=CMD``/``=HYPERLINK``/DDE payloads).
        """
        return [
            sanitize_spreadsheet_cell(value)
            for value in (
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
            )
        ]
