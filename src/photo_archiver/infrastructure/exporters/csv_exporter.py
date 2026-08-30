"""CSV exporter for Step 14 Export.

Uses the standard-library ``csv`` module (no extra dependency).  Produces a
UTF-8-BOM CSV so Excel can open it without guessing the encoding.
"""

from csv import writer as csv_writer
from pathlib import Path

from photo_archiver.application.ports.exporter import ExportRow
from photo_archiver.infrastructure.exporters._spreadsheet_safety import (
    sanitize_spreadsheet_cell,
)


class CsvExporter:
    """Write export rows to a UTF-8-BOM ``.csv`` file."""

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

    def export(self, rows: list[ExportRow], output_path: str) -> str:
        """Write rows as a CSV file with a header row."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        with open(str(out), "w", newline="", encoding="utf-8-sig") as f:
            w = csv_writer(f)
            w.writerow(self._HEADERS)
            for row in rows:
                w.writerow(self._to_row(row))

        return f"Exported {len(rows)} rows to {out}"

    @staticmethod
    def _to_row(row: ExportRow) -> list[str | float | None]:
        """Flatten an ExportRow into a header-aligned list.

        P2-003 fix: string cells pass through formula-injection sanitization
        so opening the export in Excel/LibreOffice cannot execute injected
        formulas from user-controlled fields.
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
