import sys
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
if SOURCE_ROOT.is_dir():
    sys.path.insert(0, str(SOURCE_ROOT))

from photo_archiver.app import ApplicationContext, PhotoArchiverApplication, bootstrap_application  # noqa: E402  # sys.path injection above is required before app imports
from photo_archiver.application import (  # noqa: E402  # sys.path injection above is required before app imports
    ArchivePhotosCommand,
    BackfillCaptureTimeCommand,
    ImportPeopleCommand,
    PruneMissingCommand,
    ScanAndRegisterPhotosCommand,
)
from photo_archiver.application.commands import MatchPersonsCommand  # noqa: E402
from photo_archiver.app.services import ModelPackMissing  # noqa: E402
from photo_archiver.application.dtos.export import ExportScope  # noqa: E402
from photo_archiver.domain import MatchStatus, PhotoSearchCriteria  # noqa: E402
from photo_archiver.infrastructure.exporters import (  # noqa: E402
    CsvExporter,
    ExcelExporter,
    HtmlExporter,
)
from photo_archiver.infrastructure.config import AppSettings  # noqa: E402
from photo_archiver.infrastructure.config.settings import (  # noqa: E402
    default_database_path,
    default_database_url,
)
from photo_archiver.infrastructure.database.backup import backup_database, copy_database  # noqa: E402
from photo_archiver.infrastructure.database.integrity import (  # noqa: E402
    BACKUP_DIRECTORY_NAME,
    CorruptedDatabaseError,
)
from photo_archiver.presentation.startup_failure import (  # noqa: E402
    corrupted_database_guidance,
    show_corrupted_database_dialog,
)


def _corrupted_database_message(error: CorruptedDatabaseError) -> str:
    """Build the user-facing Chinese guidance for a corrupted database file."""
    return corrupted_database_guidance(
        database_path=error.database_path,
        backup_directory=error.database_path.parent / BACKUP_DIRECTORY_NAME,
        issues=error.issues,
    )


def _bootstrap_for_cli() -> ApplicationContext | None:
    """Bootstrap for CLI commands; on corruption report guidance and give up.

    ADR-036 D8：CLI 与 GUI 对齐——写库子命令同样先做启动备份（best-effort，
    失败只告警不阻断）。修订 ``docs/development/configuration.md`` 既定的
    "CLI 不生成启动备份"行为（CLI 与 GUI 的写库风险面同量级）。

    Returns:
        The application context, or ``None`` when the database is corrupted
        (guidance has been written to stderr by then).
    """
    try:
        context = bootstrap_application()
    except CorruptedDatabaseError as error:
        sys.stderr.write(_corrupted_database_message(error) + "\n")
        return None
    _backup_database_best_effort(context)
    return context


def _backup_database_best_effort(context: ApplicationContext) -> None:
    """Take a startup backup snapshot (D-B3 semantics), never blocking the run."""
    settings = getattr(context, "settings", None)
    database_path = getattr(settings, "database_path", None)
    if database_path is None:
        return
    try:
        backup_database(database_path)
    except Exception as error:  # noqa: BLE001 - backup is best-effort by design (D-B3)
        logger.warning("CLI startup database backup failed (non-fatal): {}", error)


def build_argument_parser() -> ArgumentParser:
    """Build the command-line parser for desktop and utility commands."""
    parser = ArgumentParser(prog="photo-archiver")
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="scan and register photos from a folder")
    scan_parser.add_argument("folder", type=Path, help="folder containing photos to import")
    scan_parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="scan only the selected folder instead of nested folders",
    )
    scan_parser.add_argument("--name", dest="folder_display_name", help="display name for the folder")

    archive_parser = subparsers.add_parser(
        "archive",
        help="archive approved photos into ARCHIVE_ROOT/{person}/{date}/{file}",
    )
    archive_parser.add_argument(
        "--archive-root",
        type=Path,
        dest="archive_root",
        help="override AppSettings.archive_root for this run",
    )
    archive_parser.add_argument(
        "--conflict-strategy",
        dest="conflict_strategy",
        choices=("skip", "overwrite", "rename"),
        help="how to handle target files that already exist (default: skip)",
    )
    archive_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="log intended operations without touching the filesystem",
    )

    subparsers.add_parser(
        "backfill-content-hash",
        help="one-time backfill of content_hash for photos registered before B1 wiring",
    )

    prune_parser = subparsers.add_parser(
        "prune-missing",
        help="list registry entries whose disk file is missing; with --execute, remove those registrations",
    )
    prune_parser.add_argument(
        "--execute",
        action="store_true",
        help="really remove the missing registrations (default: dry-run preview only)",
    )

    capture_parser = subparsers.add_parser(
        "backfill-capture-time",
        help="one-time captured_at correction for photos registered before the ISSUE-019 EXIF fix (dry-run by default)",
    )
    capture_parser.add_argument(
        "--execute",
        action="store_true",
        help="really update the registrations (default: dry-run preview only)",
    )

    import_parser = subparsers.add_parser(
        "import-people",
        help="import people from a TXT/CSV/Excel file (same pipeline as the UI import)",
    )
    import_parser.add_argument("source", type=Path, help="people file (.txt/.csv/.xlsx/.xlsm)")
    import_parser.add_argument(
        "--no-header",
        action="store_true",
        help="the source file has no header row (default: header expected)",
    )
    import_parser.add_argument(
        "--sheet-name",
        help="Excel sheet name for xlsx/xlsm sources (default: first sheet)",
    )

    migrate_parser = subparsers.add_parser(
        "migrate",
        help="copy a legacy CWD database (data/photo_archiver.db) into the anchored user-data location",
    )
    migrate_parser.add_argument(
        "--execute",
        action="store_true",
        help="really perform the copy (default: dry-run plan only)",
    )

    recognize_parser = subparsers.add_parser(
        "recognize",
        help="run face detection/recognition/matching on registered photos (requires the model pack)",
    )
    recognize_parser.add_argument(
        "--all",
        action="store_true",
        help="re-match every registered photo (default: only photos without any recognition result)",
    )
    recognize_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap the number of photos processed this run",
    )

    cleanup_parser = subparsers.add_parser(
        "cleanup-thumbnails",
        help="remove orphaned thumbnail cache entries (dry-run by default)",
    )
    cleanup_parser.add_argument(
        "--execute",
        action="store_true",
        help="really remove the orphans (default: dry-run preview only)",
    )

    export_parser = subparsers.add_parser(
        "export",
        help="export the library to Excel/CSV/HTML (ALL scope by default)",
    )
    export_parser.add_argument("output", type=Path, help="output file path")
    export_parser.add_argument(
        "--format",
        dest="format_name",
        choices=("xlsx", "csv", "html"),
        help="output format (default: derived from the output suffix, else csv)",
    )
    export_parser.add_argument(
        "--scope",
        choices=("all", "filtered"),
        default="all",
        help="export scope: all, or the result of the --status/--person/--captured-* filters",
    )
    export_parser.add_argument(
        "--status",
        choices=("pending", "approved", "rejected"),
        help="filtered scope: only photos with >=1 recognition result in this status",
    )
    export_parser.add_argument(
        "--person",
        help="filtered scope: person name (exact match) or UUID",
    )
    export_parser.add_argument(
        "--captured-from",
        dest="captured_from",
        help="filtered scope: inclusive lower bound, YYYY-MM-DD",
    )
    export_parser.add_argument(
        "--captured-to",
        dest="captured_to",
        help="filtered scope: inclusive upper bound, YYYY-MM-DD",
    )
    return parser


def run_scan_command(arguments: Namespace) -> int:
    """Run the scan-and-register workflow from CLI arguments."""
    context = _bootstrap_for_cli()
    if context is None:
        return 2
    result = context.services.scan_and_register_photos.execute(
        ScanAndRegisterPhotosCommand(
            folder_path=arguments.folder,
            recursive=not arguments.no_recursive,
            folder_display_name=arguments.folder_display_name,
        )
    )
    sys.stdout.write(
        "Scan complete: "
        f"discovered={result.discovered_count}, "
        f"registered={result.registered_count}, "
        f"updated={result.updated_count}, "
        f"skipped={result.skipped_count}, "
        f"failed={result.failed_count}\n"
    )
    for error in result.errors:
        sys.stderr.write(f"Error: {error}\n")
    return 0 if result.succeeded else 1


def run_archive_command(arguments: Namespace) -> int:
    """Run the archive workflow from CLI arguments."""
    context = _bootstrap_for_cli()
    if context is None:
        return 2
    archive_root = arguments.archive_root or context.settings.archive_root
    if archive_root is None:
        sys.stderr.write(
            "Archive root is not configured. Set ARCHIVE_ROOT in .env or pass --archive-root.\n"
        )
        return 2
    command = ArchivePhotosCommand(
        archive_root=archive_root,
        conflict_strategy=arguments.conflict_strategy,
        dry_run=arguments.dry_run,
    )
    result = context.services.archive_photos.execute(command)
    sys.stdout.write(
        "Archive complete: "
        f"planned={result.planned_count}, "
        f"archived={result.archived_count}, "
        f"skipped={result.skipped_count}, "
        f"renamed={sum(1 for o in result.outcomes if o.status.value == 'renamed')}, "
        f"overwritten={sum(1 for o in result.outcomes if o.status.value == 'overwritten')}, "
        f"dry_run={result.dry_run_count}, "
        f"failed={result.failed_count}\n"
    )
    for error in result.errors:
        sys.stderr.write(f"Error: {error}\n")
    return 0 if result.succeeded else 1


def run_backfill_content_hash_command(arguments: Namespace) -> int:
    """One-time backfill of content_hash for photos registered before B1 wiring.

    B1-a 裁决已拍板：历史 NULL 哈希照片走显式 CLI 子命令而非启动时惰性补齐——
    显式、可测、不拖慢启动。Idempotent：对已全回填的数据库再调用是 no-op。
    """
    context = _bootstrap_for_cli()
    if context is None:
        return 2
    result = context.services.backfill_content_hash.execute()
    sys.stdout.write(
        "Backfill complete: "
        f"scanned={result.scanned}, "
        f"backfilled={result.backfilled}, "
        f"skipped_missing={result.skipped_missing}, "
        f"failed={result.failed}\n"
    )
    return 0 if result.succeeded else 1


def run_prune_missing_command(arguments: Namespace) -> int:
    """List (or, with --execute, remove) registrations whose file is missing.

    Phase E E-5（ADR-034 D5）：文件消失**不自动删库**（防移动盘未挂载误判）。
    默认 dry-run 只列失联登记（含期望磁盘路径，供用户核实）；带 ``--execute``
    才移除这些登记——磁盘文件一律不动（D3）。无法解析路径者保守跳过不计入。
    """
    context = _bootstrap_for_cli()
    if context is None:
        return 2
    service = context.services.prune_missing_photos
    preview = service.preview()
    if preview.is_empty:
        sys.stdout.write(
            "Prune-missing: no missing registrations found — every registered "
            "photo has a file on disk.\n"
        )
        return 0
    sys.stdout.write(
        f"Prune-missing: {preview.missing_count} registration(s) whose file is gone "
        f"(scanned {preview.scanned}; unresolvable {preview.unresolvable} skipped "
        "conservatively):\n"
    )
    for item in preview.items:
        sys.stdout.write(f"  {item.photo_id}  {item.disk_path}\n")
    if not arguments.execute:
        sys.stdout.write(
            "Dry-run: nothing pruned. Re-run with --execute to remove these "
            "registrations (disk files are never touched).\n"
        )
        return 0
    command = PruneMissingCommand(
        photo_ids=tuple(item.photo_id for item in preview.items)
    )
    result = service.execute(command)
    sys.stdout.write(
        f"Prune complete: pruned={result.pruned}, rejected={result.rejected}, "
        f"missing={result.missing}, unresolvable={result.unresolvable}\n"
    )
    return 0


def run_backfill_capture_time_command(arguments: Namespace) -> int:
    """One-time captured_at correction for pre-ISSUE-019 registrations.

    Phase F F-1（ADR-035）：历史照片拍摄时刻全量重读对齐（EXIF 事实源），
    dry-run 默认只报差异计数，``--execute`` 才写。幂等：重跑差异归零。
    """
    context = _bootstrap_for_cli()
    if context is None:
        return 2
    command = BackfillCaptureTimeCommand(dry_run=not arguments.execute)
    result = context.services.backfill_capture_time.execute(command)
    diff_label = "would_update" if command.dry_run else "updated"
    diff_value = result.would_update if command.dry_run else result.updated
    sys.stdout.write(
        "Backfill capture-time complete: "
        f"scanned={result.scanned}, "
        f"{diff_label}={diff_value}, "
        f"unchanged={result.unchanged}, "
        f"failed={result.failed}, "
        f"skipped_missing={result.skipped_missing}\n"
    )
    if command.dry_run:
        sys.stdout.write(
            "Dry-run: nothing written. Re-run with --execute to apply the corrections.\n"
        )
    return 0 if result.succeeded else 1


def run_import_people_command(arguments: Namespace) -> int:
    """Run the people-import workflow from CLI arguments (ADR-036 F-6)."""
    context = _bootstrap_for_cli()
    if context is None:
        return 2
    result = context.services.import_people.execute(
        ImportPeopleCommand(
            source_path=arguments.source,
            has_header=not arguments.no_header,
            sheet_name=arguments.sheet_name,
        )
    )
    sys.stdout.write(
        "Import complete: "
        f"imported={result.imported_count}, "
        f"skipped={result.skipped_count}, "
        f"failed={len(result.errors)}\n"
    )
    for error in result.errors:
        sys.stderr.write(f"Error: {error}\n")
    return 0 if not result.errors else 1


def _resolve_cli_export_criteria(
    context: ApplicationContext, arguments: Namespace
) -> PhotoSearchCriteria | None:
    """Build the FILTERED-scope criteria from CLI filter flags.

    Returns ``None`` for the ALL scope. FILTERED without any filter flag is
    rejected here (the Service would independently reject it — this surfaces
    the cause at the CLI boundary instead of a generic error).
    """
    if arguments.scope != "filtered":
        return None
    if not (arguments.status or arguments.person or arguments.captured_from or arguments.captured_to):
        raise ValueError(
            "scope=filtered requires at least one of --status/--person/--captured-from/--captured-to"
        )
    person_id = None
    if arguments.person:
        try:
            person_id = UUID(arguments.person)
        except ValueError:
            match = next(
                (p for p in context.repositories.people.list_all() if p.name == arguments.person),
                None,
            )
            if match is None:
                raise ValueError(f"person not found: {arguments.person!r}") from None
            person_id = match.id
    date_format = "%Y-%m-%d"
    return PhotoSearchCriteria(
        match_status=MatchStatus(arguments.status) if arguments.status else None,
        person_id=person_id,
        captured_from=(
            datetime.strptime(arguments.captured_from, date_format)
            if arguments.captured_from
            else None
        ),
        captured_to=(
            datetime.strptime(arguments.captured_to, date_format)
            + timedelta(days=1)
            - timedelta(seconds=1)
            if arguments.captured_to
            else None
        ),
    )


def run_export_command(arguments: Namespace) -> int:
    """Run the export workflow from CLI arguments (ADR-036 F-6)."""
    context = _bootstrap_for_cli()
    if context is None:
        return 2
    try:
        criteria = _resolve_cli_export_criteria(context, arguments)
    except ValueError as error:
        sys.stderr.write(f"Error: {error}\n")
        return 2
    format_name = arguments.format_name or arguments.output.suffix.lstrip(".").lower()
    exporters = {"xlsx": ExcelExporter(), "csv": CsvExporter(), "html": HtmlExporter()}
    if format_name not in exporters:
        sys.stderr.write(
            f"Error: cannot derive an export format from {arguments.output.name!r}; "
            "pass --format xlsx|csv|html.\n"
        )
        return 2
    scope = ExportScope.FILTERED if arguments.scope == "filtered" else ExportScope.ALL
    path = context.services.export.execute(
        exporters[format_name],
        str(arguments.output),
        scope,
        criteria=criteria,
    )
    sys.stdout.write(f"Export complete: {path}\n")
    return 0


def run_cleanup_thumbnails_command(arguments: Namespace) -> int:
    """Remove orphaned thumbnail cache entries (ISSUE-023; dry-run default)."""
    context = _bootstrap_for_cli()
    if context is None:
        return 2
    result = context.services.cleanup_thumbnails.execute(dry_run=not arguments.execute)
    label = "would_remove" if result.dry_run else "removed"
    sys.stdout.write(
        "Thumbnail cache cleanup: "
        f"{label}={result.removed}, "
        f"retained={result.retained}\n"
    )
    if result.dry_run:
        sys.stdout.write(
            "Dry-run: nothing deleted. Re-run with --execute to remove the orphans "
            "(thumbnails are derived data — they regenerate on demand).\n"
        )
    return 0


_LEGACY_CWD_DATABASE = Path("data") / "photo_archiver.db"
_MIGRATION_EMPTY_DB_TABLES = ("photos", "people", "folders")


def _is_empty_archiver_database(path: Path) -> bool:
    """Return whether the database exists but holds no user data (ADR-039).

    A fresh bootstrap creates the anchored database with the full schema and
    zero rows; such a file is safe to take over during migration (the startup
    backup in ``backups/`` already snapshots it). Unreadable/foreign files are
    conservatively treated as non-empty.
    """
    import sqlite3

    try:
        connection = sqlite3.connect(path)
        try:
            for table in _MIGRATION_EMPTY_DB_TABLES:
                count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if count:
                    return False
        finally:
            connection.close()
    except sqlite3.Error:
        return False
    return True


def _resolve_migration_paths(settings) -> tuple[Path, Path] | None:
    """Return (legacy source, anchored target) for the migrate command.

    ``None`` when migration does not apply: the effective DATABASE_URL is an
    explicit user configuration (migrate only serves the anchored-default
    takeover), or the legacy CWD database does not exist.
    """
    if settings.database_url != default_database_url():
        return None
    legacy = _LEGACY_CWD_DATABASE
    if not legacy.exists():
        return None
    return legacy, default_database_path()


def run_migrate_command(arguments: Namespace) -> int:
    """Copy the legacy CWD database into the anchored location (ADR-039).

    Copy, never move (D3): the legacy file is left untouched. Dry-run by
    default; ``--execute`` performs the copy. A bootstrap-created empty
    anchored database is taken over (its startup backup already snapshots
    it); a non-empty target is refused.
    """
    settings = AppSettings()
    resolved = _resolve_migration_paths(settings)
    if resolved is None:
        if settings.database_url != default_database_url():
            sys.stderr.write(
                "Migrate only applies when DATABASE_URL is at its anchored default "
                f"({default_database_url()}); the effective value is an explicit "
                "configuration — nothing to migrate.\n"
            )
        else:
            sys.stderr.write(
                f"No legacy database found at {_LEGACY_CWD_DATABASE} — nothing to migrate.\n"
            )
        return 2
    source, target = resolved
    target_exists = target.exists()
    target_state = "absent"
    if target_exists:
        target_state = "empty (safe to take over)" if _is_empty_archiver_database(target) else "non-empty"
    sys.stdout.write(
        "Migration plan (dry-run):\n"
        f"  source: {source.resolve()}\n"
        f"  target: {target}\n"
        f"  target state: {target_state}\n"
        "  method: VACUUM INTO consistent snapshot; the legacy file is NOT moved.\n"
    )
    if not arguments.execute:
        sys.stdout.write(
            "Dry-run: nothing copied. Re-run with --execute to perform the migration.\n"
        )
        return 0
    if target_exists and target_state != "empty (safe to take over)":
        sys.stderr.write(
            f"Error: migration target already exists and holds data: {target}\n"
            "Move it aside manually (or point DATABASE_URL at the legacy file) and re-run.\n"
        )
        return 2
    try:
        if target_exists:
            target.unlink()  # 空库接管：bootstrap 的启动备份已留有快照
        copy_database(source, target)
    except (OSError, RuntimeError) as error:
        sys.stderr.write(f"Error: migration failed: {error}\n")
        return 1
    sys.stdout.write(
        f"Migration complete: {target}\n"
        f"The legacy database at {source.resolve()} was left in place; "
        "archive or delete it manually once the app verifies the data.\n"
    )
    return 0


class _CliProgressReporter:
    """Print first/last/every-10th progress events from the service cadence."""

    def __init__(self, total: int) -> None:
        self._total = total
        self._last_reported = 0

    def report(self, current: int, total: int, message: str) -> None:
        if current - self._last_reported < 25 and current not in (1, total):
            return
        self._last_reported = current
        sys.stdout.write(f"  [{current}/{total}] {message}\n")


def run_recognize_command(arguments: Namespace) -> int:
    """Run the face-recognition pipeline over registered photos (G-1, FEAT-15).

    Mirrors the UI resume semantics: by default only photos without any
    recognition result are submitted, so an interrupted run resumes the
    remainder instead of duplicating results. ``--all`` re-matches everything;
    ``--limit`` caps the batch.
    """
    context = _bootstrap_for_cli()
    if context is None:
        return 2
    repositories = context.repositories
    if not repositories.people.list_all():
        sys.stderr.write(
            "Error: no persons registered — import people first (import-people).\n"
        )
        return 2
    photos = repositories.photos.list_all()
    if not photos:
        sys.stderr.write(
            "Error: no photos registered — scan a folder first (scan).\n"
        )
        return 2
    photo_ids = tuple(photo.id for photo in photos if photo.id is not None)
    if arguments.all:
        pending = photo_ids
    else:
        already_matched = repositories.recognition.list_first_by_photo_ids(photo_ids)
        pending = tuple(pid for pid in photo_ids if pid not in already_matched)
    if not pending:
        sys.stdout.write(
            "Recognize: every registered photo already has a recognition result "
            "(use --all to re-match).\n"
        )
        return 0
    if arguments.limit is not None:
        if arguments.limit < 0:
            sys.stderr.write("Error: --limit must be >= 0.\n")
            return 2
        pending = pending[: arguments.limit]
    pending_set = set(pending)
    command = MatchPersonsCommand(
        photo_ids=pending,
        images=tuple(photo.path.raw_path for photo in photos if photo.id in pending_set),
    )
    try:
        with context.services.match_persons.bind_progress_reporter(
            _CliProgressReporter(total=len(pending))
        ):
            results = context.services.match_persons.execute(command)
    except ModelPackMissing as error:
        sys.stderr.write(
            f"Error: face recognition model pack is missing or incomplete: {error}\n"
            "Run scripts/download_models.py first "
            "(see docs/user-guide/installation.md).\n"
        )
        return 2
    faces = sum(1 for result in results if result.box is not None)
    sys.stdout.write(
        "Recognize complete: "
        f"processed={len(results)}, "
        f"faces_found={faces}, "
        f"no_face={len(results) - faces}\n"
        "Review the results in the app (审核) or export them (export).\n"
    )
    return 0


def main(arguments: list[str] | None = None) -> int:
    """Run the PhotoArchiver desktop application.

    Returns:
        The application exit code.
    """
    raw_arguments = sys.argv[1:] if arguments is None else arguments
    parsed_arguments = build_argument_parser().parse_args(raw_arguments)
    if parsed_arguments.command == "scan":
        return run_scan_command(parsed_arguments)
    if parsed_arguments.command == "archive":
        return run_archive_command(parsed_arguments)
    if parsed_arguments.command == "backfill-content-hash":
        return run_backfill_content_hash_command(parsed_arguments)
    if parsed_arguments.command == "prune-missing":
        return run_prune_missing_command(parsed_arguments)
    if parsed_arguments.command == "backfill-capture-time":
        return run_backfill_capture_time_command(parsed_arguments)
    if parsed_arguments.command == "import-people":
        return run_import_people_command(parsed_arguments)
    if parsed_arguments.command == "export":
        return run_export_command(parsed_arguments)
    if parsed_arguments.command == "cleanup-thumbnails":
        return run_cleanup_thumbnails_command(parsed_arguments)
    if parsed_arguments.command == "migrate":
        return run_migrate_command(parsed_arguments)
    if parsed_arguments.command == "recognize":
        return run_recognize_command(parsed_arguments)

    try:
        context = bootstrap_application()
    except CorruptedDatabaseError as error:
        show_corrupted_database_dialog(_corrupted_database_message(error))
        return 2
    # P0-6（D-B3）：GUI 启动成功即做一致性快照备份。
    # P0-8 轮（审查 F-1）：备份失败只告警不阻断启动——不可写目录/磁盘满
    # 等场景不得击穿 P0-6 要加固的启动链路。
    try:
        backup_database(context.settings.database_path)
    except Exception as error:  # noqa: BLE001 - backup is best-effort by design (D-B3)
        logger.warning("Startup database backup failed (non-fatal): {}", error)
    application = PhotoArchiverApplication(sys.argv, context=context)
    return application.run()


if __name__ == "__main__":
    sys.exit(main())
