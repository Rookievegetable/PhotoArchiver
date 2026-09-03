# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Commit-level history lives in git — this file is the user-facing digest.

## [2.3.0] - 2026-09-02

Data-safety floor, runtime correctness, and flake elimination
(health-check-derived phases A/B/C + release engineering form-1; owner
authorized per phase, decisions D-B1~D-B8 and D-0 recorded in
`.ai/PROJECT_STATUS.md`).

### Added

- **Data-safety floor (Phase B)**: WAL journal mode + 5 s busy_timeout on
  every connection (a long scan no longer blocks concurrent review writes);
  startup integrity gate — a corrupted database fails fast with Chinese
  recovery guidance instead of a traceback (never rebuilt or swapped);
  `VACUUM INTO` snapshot backup on every GUI start (3 rolling copies in
  `data/backups/`); people import is batch-atomic (500 rows/batch — a crash
  leaves only fully committed batches) with identity-less rows deduplicated
  by name + department.
- **Model supply-chain pinning (P0-8)**: the buffalo_l release zip SHA-256 is
  pinned (`EXPECTED_SHA256`); CI dropped `--allow-unverified` and now fails
  closed on any mismatch.
- **Launch path warnings (P0-9)**: relative configured paths (database /
  models / outputs / logs) log a warning with the resolved absolute location
  at startup — launching from a different directory no longer silently
  switches databases unnoticed.
- **Thumbnails in the photo list**: a delegate now renders the cached
  thumbnail per row (previously generated but never displayed).
- **Plugin actions in the toolbar**: the example plugins' actions actually
  load and appear (a path bug had silently skipped them).
- **Excel people import**: `.xlsx` workbooks are routed to the openpyxl
  reader (previously parsed as text); the picker no longer advertises the
  unsupported legacy `.xls`.
- **Atomic exports**: CSV/XLSX/HTML exports write via a temp file and
  atomic swap — an interrupted export leaves the previous file intact.

### Fixed

- **Model download TLS (clean Windows)**: the downloader passed no SSL
  context, so CPython's default CA loading applied — on a clean Windows
  machine (no issuer for the github.com chain) the model bootstrap failed
  with `CERTIFICATE_VERIFY_FAILED`. The TLS context is now anchored to
  certifi's CA bundle (certificate and hostname verification stay fully
  enabled), and certifi is a declared runtime dependency so a clean machine
  always has the bundle.
- **Scan cancellation**: cancelling a scan now resets the UI to the
  cancelled state (previously stuck at "Cancelling ..."), and a second scan
  cannot start while one is running (single-flight guard on controller and
  UI levels).
- **Plugin loading**: the toolbar plugin directory anchor pointed at a
  nonexistent path, silently skipping the whole plugin UI chain.
- **To date-picker placement**: the filter bar's To edit was never added to
  the layout and floated over the Person axis, blocking its clicks.
- **Person filter order**: the people dropdown ordered same-batch imports
  randomly (UUID tiebreak); ordering is now deterministic (creation time,
  then name).
- **Match e2e test stability**: the two real-thread-pool match e2e tests
  poll the single-flight guard release instead of asserting immediately
  after the terminal signal (robust to cross-thread delivery ordering). The
  underlying guard-race remains a registered known limitation.

### Changed

- Export file picker no longer advertises legacy `.xls` (openpyxl cannot
  read it); tests and CI run the model download with pinned-digest
  verification (no escape hatch).

## [2.2.0] - 2026-08-29

Dead-weight model removal in the recognition pipeline (phase7 / ADR-033;
three pre-gate decisions confirmed 2026-08-29, all option A).

### Performance

- **~2× end-to-end recognition throughput**: the buffalo_l pack's two landmark
  models (1k3d68 + 2d106det, 35.4 ms/photo) and genderage (9.8 ms/photo) were
  pure dead weight — zero consumers in the codebase (grep-verified; the
  `Person` domain entity has no gender/age fields). The loader now passes
  `allowed_modules=("detection", "recognition")`, so `FaceAnalysis` loads and
  runs only the detection and recognition models (3 fewer ONNX sessions,
  faster startup; every photo skips ~45 ms of dead inference).
- Re-benchmarked full grid (`tools/bench_recognition.py`, same machine as the
  phase6 baseline): 2,600-photo serial 656.94 s → 332.02 s (**1.98×**);
  production 4-worker 5.06 → 11.22 photos/s (**2.22×**); 600×4 2.45×. Every
  cell 100% results / all PENDING — output equivalence invariants hold
  (bbox/kps/embedding byte-identical). Remaining non-inference segments
  (~38 ms/photo) deliberately deferred (ADR-033 W2-3=A).

## [2.1.0] - 2026-08-29

Recognition-pipeline throughput hardening round (phase6; five pre-gate
decisions recorded 2026-08-28, all per default recommendation).

### Added

- **Batched persistence**: `RecognitionRepository` gains `add_many` — the
  SQLite implementation commits a batch in a single transaction (round trips
  O(N) → O(1)); the in-memory implementation stays per-item equivalent.
- **Benchmark tool** `tools/bench_recognition.py`: library-scale × worker-count
  grid (100/600/2600 × 1/2/4) driving the real InsightFace adapters and the
  real `MatchPersonsService` path; baseline numbers recorded in its docstring
  (anti-regression convention, same as `bench_plugin_search.py`).

### Changed

- **Parallel recognition analysis**: the per-photo inference stage of
  `MatchPersonsService` now runs on a thread pool (reusing `MAX_WORKERS`).
  The parallel section is restricted to pure inference (detect+embed+cosine
  match); persistence stays on the main thread. Results are field-for-field
  equivalent to the serial path (locked by new equivalence tests); progress
  reporting semantics and per-photo failure isolation are unchanged, and the
  `max_workers=1` path is byte-for-byte the previous serial behavior.
- Measured scaling is modest (1.28× at 4 workers on the 2,600-photo CPU
  baseline): the onnxruntime session's internal intra-op pool already
  saturates cores during a single call, so worker threads mostly overlap
  Python-side overhead. Batch inference (phase6 §8 A-2=B) is the recorded
  follow-up candidate for real throughput gains — pending owner decision.



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
