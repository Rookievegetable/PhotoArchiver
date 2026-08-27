# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Commit-level history lives in git — this file is the user-facing digest.

## [2.0.0] - 2026-08-27

Breaking release executing the destructive window scheduled by ADR-030
(one-version deprecation grace promised by ADR-026 has elapsed).

### Removed (**BREAKING**)

- **Plugins: legacy `enable(context)` signature support dropped.** The plugin
  registry no longer detects or dispatches the deprecated one-parameter
  `enable(context)` signature. External plugins must implement the standard
  `ContextAwarePlugin` lifecycle (`set_context(context)` + no-arg `enable()`)
  or a plain no-arg `enable()`.
  - Impact: plugins still carrying the old signature with a required positional
    parameter fail to enable and are skipped with a logged error while the host
    keeps running; plugins whose old signature merely defaults the parameter
    (e.g. `context=None`) still enable through the no-arg call but receive no
    host context (misbehavior surfaces at execute_action time).
  - Migration guide: `docs/development/plugin-guide.md` §6.
  - Zero production/example consumers were affected (grep-verified, ADR-030).

### Changed

- Version chain bumped to 2.0.0 (`pyproject.toml`; `.env.example` example).

## [1.0.0] - 2026-08-25

First official release. Includes the complete 15-step product roadmap,
the Phase B business enhancements (B1–B5) and post-completion hardening
phases 0–4 (ADR-024 through ADR-030).

### Added

- **Desktop workbench** (PySide6): people import, recursive folder scan with
  thumbnail list, review dialog, archive preview, duplicate report, export
  dialog and settings (theme / language / match threshold / max workers,
  persisted via native QSettings).
- **Face pipeline**: InsightFace detection → embedding → 1:N Top-1 matching
  with a user-review lifecycle (`pending / approved / rejected`) and atomic
  persistence.
- **Archiving engine**: Planner → Plan → Executor split with dry-run mode,
  EXIF-based `{ARCHIVE_ROOT}/{person}/{date}/{file}` target paths and conflict
  strategies (`skip` / `overwrite` / `rename`).
- **Duplicate detection** via SHA-256 content hash with grouped read-only
  reporting and an idempotent one-time backfill CLI subcommand.
- **Search & filtering** pushed down to SQL (person / review status /
  capture-date range) with an in-memory parity implementation.
- **Export** to Excel / CSV / HTML across selectable data scopes.
- **Plugin system**: sandboxed-by-convention `PluginContext` facade
  (search_photos, detect_duplicates, import_people), ContextAwarePlugin
  lifecycle, structured plugin reports and three example plugins
  (hello, stats report, import demo).
- **Schema migrations** managed by Alembic from an empty stamp through full
  DDL ownership; structured Loguru logging; pydantic-settings configuration.
- **CI**: three-OS pytest matrix with model-pack cache, AI/UI non-skip
  assertions, plus a tag-triggered release pipeline building sdist & wheel.

### Changed

- Plugin photo queries resolve recognition statuses in ONE batched repository
  round trip instead of per-photo lookups (measured 18.2× faster on a
  2,600-photo library; ADR-029).

### Deferred by decision

- Export plugin write capability was closed as YAGNI (ADR-030); the host
  approval gate stays deferred until a high-risk plugin write use case
  appears. (The `enable(context)` removal once scheduled here was executed
  in v2.0.0 — see the [2.0.0] section above.)
