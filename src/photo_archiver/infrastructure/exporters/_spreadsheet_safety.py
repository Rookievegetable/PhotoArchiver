"""Spreadsheet formula-injection sanitization shared by the CSV/Excel exporters.

P2-003 fix (Phase 3 audit): user-controlled ``ExportRow`` string fields are
written verbatim into cells; when the export is opened in Excel/LibreOffice a
cell text starting with ``=``, ``+``, ``-``, ``@``, tab or CR is interpreted
as a formula (DDE / HYPERLINK / CMD injection). Prefixing a single quote
forces text interpretation (OWASP CSV injection guidance).

Numeric values are written as real numbers (never as formulas), so they pass
through unchanged; a leading ``-`` on a *string* is only neutralized when the
remainder does not parse as a number, so legitimate negative numbers keep
their sign.
"""

_NEUTRALIZING_PREFIX = "'"
# Leading characters that spreadsheet applications may treat as formulas.
_FORMULA_PREFIXES = ("=", "+", "@", "\t", "\r")


def _looks_like_negative_number(text: str) -> bool:
    """Return whether ``text`` is a plain negative number (e.g. ``-0.5``)."""
    try:
        float(text)
    except ValueError:
        return False
    return True


def sanitize_spreadsheet_cell(value: str | float | None) -> str | float | None:
    """Return a cell value safe to write into a CSV/Excel document.

    Args:
        value: Raw cell value from an ``ExportRow`` field.

    Returns:
        The value unchanged for ``None``/numbers/safe strings; a single-quote
        prefixed copy for strings that a spreadsheet would otherwise parse
        as a formula.
    """
    if not isinstance(value, str):
        return value
    if value.startswith(_FORMULA_PREFIXES):
        return _NEUTRALIZING_PREFIX + value
    if value.startswith("-") and not _looks_like_negative_number(value[1:]):
        return _NEUTRALIZING_PREFIX + value
    return value
