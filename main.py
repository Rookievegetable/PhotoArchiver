import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
if SOURCE_ROOT.is_dir():
    sys.path.insert(0, str(SOURCE_ROOT))

from photo_archiver.app import PhotoArchiverApplication, bootstrap_application
from photo_archiver.application import ArchivePhotosCommand, ScanAndRegisterPhotosCommand


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
    return parser


def run_scan_command(arguments: Namespace) -> int:
    """Run the scan-and-register workflow from CLI arguments."""
    context = bootstrap_application()
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
        f"skipped={result.skipped_count}, "
        f"failed={result.failed_count}\n"
    )
    for error in result.errors:
        sys.stderr.write(f"Error: {error}\n")
    return 0 if result.succeeded else 1


def run_archive_command(arguments: Namespace) -> int:
    """Run the archive workflow from CLI arguments."""
    context = bootstrap_application()
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

    context = bootstrap_application()
    application = PhotoArchiverApplication(sys.argv, context=context)
    return application.run()


if __name__ == "__main__":
    sys.exit(main())
