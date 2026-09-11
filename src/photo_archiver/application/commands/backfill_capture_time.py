"""Command for the one-time captured_at backfill (Phase F F-1, ADR-035)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BackfillCaptureTimeCommand:
    """Request the one-time captured_at correction run (dry-run by default).

    dry_run: When True (default), the service only reads and counts the
    differences — no registration is written. The CLI ``--execute`` flag
    flips this to False.
    """

    dry_run: bool = True
