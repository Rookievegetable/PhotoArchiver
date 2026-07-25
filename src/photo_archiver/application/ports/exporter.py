"""Exporter port protocol for Step 14 Export.

The ``Exporter`` Protocol lives in the Application layer port boundary so that
``ExportService`` (Application) depends only on the protocol, not on concrete
Infrastructure implementations. Infrastructure adapters (Excel, CSV, …) implement
this Protocol.

openpyxl / pandas 仅在 Infrastructure 层（DEP-032），Application 不引入。
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExportRow:
    """One flattened row of export data, shared across all exporters.

    Application layer assembles lists of ``ExportRow`` from domain entities and
    passes them to a concrete ``Exporter``; the exporter writes them out without
    needing to understand any domain model.
    """

    # --- Person ---
    person_name: str = ""
    person_department: str | None = None
    person_note: str | None = None

    # --- Photo ---
    photo_path: str = ""
    photo_original_name: str | None = None
    photo_folder: str = ""
    photo_captured_at: str = ""

    # --- Recognition / Match ---
    match_confidence: float | None = None
    match_status: str = ""

    # --- Archive ---
    archive_status: str = ""
    archive_target: str = ""
    archive_archived_at: str = ""


class Exporter(Protocol):
    """Protocol for writing export data to an output file.

    Each exporter receives a sequence of flattened rows and writes them to
    the given output path. The protocol is intentionally synchronous; long-
    running exports are offloaded to a Worker task that calls export() on a
    background thread.
    """

    def export(self, rows: list[ExportRow], output_path: str) -> str:
        """Write rows to ``output_path`` and return a summary message.

        Args:
            rows: Flattened export rows assembled by the application layer.
            output_path: Absolute or relative path for the output file.

        Returns:
            A human-readable summary (e.g. "Exported 42 rows to /tmp/report.xlsx").

        Raises:
            OSError: When the output path is unwritable.
        """
        ...
