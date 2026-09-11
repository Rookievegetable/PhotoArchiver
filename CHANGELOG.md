# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Commit-level history lives in git — this file is the user-facing digest.

## [2.5.0] - 2026-09-12

Phase F correctness closeout (ADR-035/036): the library survives hostile
filenames and linked directories, filtered results stop duplicating rows,
long tasks became cancellable, and the CLI reaches parity with the GUI —
including the same startup-backup safety net.

### Added

- **CLI parity**（CLI 对等）: `import-people` brings the Excel/TXT people
  import pipeline to the command line; `export` writes xlsx/csv/html with
  `--scope filtered` driven by `--status` / `--person` / `--captured-from` /
  `--captured-to`. Both run through the same Application services as the UI.
- **CLI startup backup**: write-capable CLI commands now take the same
  `VACUUM INTO` snapshot as the GUI before touching the database (best-effort,
  never blocks the run) — revised the documented "CLI skips backup" behavior.
- **"未匹配" filter sentinel**: `PhotoSearchCriteria` accepts an `UNMATCHED`
  sentinel so "photos with no recognition results at all" can be selected
  programmatically (LEFT JOIN … IS NULL push-down; not yet a UI radio).
- **Coverage visibility**: pytest-cov added as a dev dependency; baseline
  recorded at 92% line coverage (no gate enforced yet).

### Fixed

- **Filtered results no longer duplicate rows**: a photo with several faces
  (multiple recognition rows) appeared once per row in person/status-filtered
  lists — the recognition JOIN is now DISTINCT.
- **Windows reserved filenames**（Windows 保留名）: person names like `con`
  and source files like `nul.jpg` made archiving fail systematically. The
  three naming segments are now sanitized (illegal characters and control
  characters → `_`, trailing dots/spaces removed, reserved device names
  prefixed with `_`); sanitized values are what previews and records show,
  and each replacement leaves a warning in the log.
- **Scanner link-loop guard**（扫描环防护）: scanning no longer follows
  symlinked or junctioned directories (realpath loop detection + depth cap),
  so a self-referencing junction can neither recurse out of control nor
  register the same photos twice. Discovery itself got ~6× faster on a
  2000-file tree by switching from `glob("**/*")` to iterative `os.scandir`.
- **Cancellable import & export**: cancelling an import no longer leaves the
  UI stuck at "Cancelling …"; exports can be cancelled cooperatively at task
  boundaries. Terminal events now also clear the window's active-run handle.
- **README contradictions removed**: the stale "待实现" section that listed
  finished steps (Export, Plugins, Alembic) is gone; test counts now point to
  `.ai/PROJECT_STATUS.md` instead of an outdated snapshot.

### Changed

- The people-file picker now also lists `.xlsm` (the reader always supported it).
- Review rows display the photo file name and person name instead of bare
  UUIDs; a deleted person renders as 未知人员.
- The photo wall shows an empty-state hint when the library (or the current
  filter) has no rows.
- The settings language dropdown is annotated as Out-of-Scope instead of
  silently doing nothing.

## [2.4.0] - 2026-09-08

Library management (Phase E, ADR-034): the photo library is no longer
append-only — photo and person registrations can be removed safely,
duplicate groups can be disposed of, and re-scans now reconcile changed
files. Every deletion is preview-confirmed, transactional, idempotent and
audit-logged; disk files are never touched, and the startup backup remains
the recovery path.

### Added

- **Delete photo registrations** (删除登记): multi-select photos in the wall
  and remove their registry entries. The confirmation dialog previews the
  cascade (recognition results and archive records removed with the photo)
  and explicitly states that disk files are never touched. Idempotent —
  ids that are no longer in the library are skipped.
- **Delete persons** (删除人员): pick a person from a dropdown with a live
  cascade preview. Face embeddings are removed with the person, their
  recognition results stay but lose their attribution (rendered as
  "未知人员"), and all of the person's photos — and disk files — are
  preserved.
- **Duplicate disposal** (按建议处置): the duplicate report now offers a
  dispose action. Each group keeps its earliest-registered photo (id as the
  deterministic tiebreak) and the rest of the registrations are removed
  after a second confirmation; the executor re-validates every id against
  the current proposal so keepers and unique photos can never be removed.
- **Rescan reconciliation** (重扫对账): re-scanning a folder detects changed
  files — strong comparison by content hash, falling back to modification
  time + size for legacy registrations without a hash — and refreshes their
  metadata through the new `PhotoRepository.update_metadata`. Snapshot
  columns (captured_at, created_at) are never rewritten. Scan output now
  reports `updated=<n>` alongside registered/skipped.
- **`prune-missing` CLI**: list registry entries whose disk file is gone —
  dry-run by default, printing the expected path for each entry.
  `--execute` removes those registrations. Files that disappear are never
  deleted from the library automatically during scans (protecting against
  unmounted drives), and unresolvable relative paths are conservatively
  skipped.

### Changed

- `python main.py scan` output now includes `updated=<n>` (rescan
  reconciliation count).
- The duplicate report dialog is no longer strictly read-only: with the
  disposal use case wired it offers the dispose action described above;
  without it (legacy/CLI wiring) it stays read-only.

## [2.3.2] - 2026-09-06

Desktop-review fixes: photo-wall layout, reliable filter placeholder, and
the EXIF capture-time correction for real camera photos.

### Fixed

- **EXIF capture time for real camera photos (ISSUE-019)**: the metadata
  reader only looked at tag 36868 in the IFD0 top level, while the EXIF
  standard places DateTimeOriginal(36867)/DateTimeDigitized(36868) inside
  the Exif sub-IFD — real camera/phone photos silently fell back to the
  file modification time, so archive date bucketing and date filters used
  the wrong date. The reader now resolves, in order: sub-IFD
  DateTimeOriginal → sub-IFD DateTimeDigitized → IFD0 top-level 36868
  (legacy compatibility) → mtime. Photos already registered keep their
  stored captured_at (no backfill); new scans get the true capture time.
- **Person filter placeholder was never drawn**: the editable person
  combo's "全部人员" hint was not rendered by the Windows style; it is now
  carried by the internal line edit and displays reliably (owner-verified
  on the real desktop).

### Changed

- **Photo grid layout**: the photo list switched from one giant thumbnail
  per row to a wrapped multi-column photo wall (~160 px cells with the
  file name beneath); the delegate cell size is constant so the layout
  stays stable while thumbnails load asynchronously.

## [2.3.1] - 2026-09-05

Desktop UI polish (owner-directed rounds after v2.3.0): Chinese
localization, a production-only toolbar, and a searchable person filter —
folded into v2.3.1 per owner decision (no separate version).

### Changed

- **Settings dialog**: the Theme and Language dropdowns now show Chinese
  labels (跟随系统 / 浅色 / 深色; 跟随系统 / 中文 / 英语) while their stored
  contract values (`system` / `light` / `dark`, `system` / `zh` / `en`) are
  unchanged — persisted preferences stay compatible.
- **Qt standard texts localized**: the app installs PySide6's bundled
  `qtbase_zh_CN` translation at startup, so standard buttons (保存 / 取消 /
  确定 / 关闭) and system dialogs (file pickers) render in Chinese. If the
  catalog is missing the app logs a warning and falls back to English.
- **Searchable person filter**: the person dropdown accepts typing — the
  completion list filters instantly with smart ranking (exact match →
  prefix → contiguous containment by leftmost position → in-order
  subsequence by smallest window span; e.g. "ab" ranks `ab`, `abxxx`,
  `xabx`, `xxab`, `axbx`, `axxb`). Typing alone never changes the filter —
  picking an entry (dropdown or completion) applies it; Clear resets.
- **Filter dropdowns show only real options**: the status dropdown lists
  待审核 / 已通过 / 已拒绝 and the person dropdown lists imported people —
  no more "全部" / "全部人员" entries inside the list. An unselected combo
  (grey placeholder text in the closed box) means "no constraint on this
  axis"; the Clear button returns both axes to that state. Filter semantics
  are unchanged (unselected = full listing).

- **Chinese desktop UI**: all user-visible text across the main window
  (toolbar, filter bar, status bar) and every dialog (import, scan, review,
  archive preview, export, settings, duplicate report, plugin report) is now
  Chinese. Logic identifiers (worker task names, enum and strategy values)
  are unchanged — only display text moved. All strings live in a single
  catalog (`presentation/ui_text.py`), prepared for future translation
  (ui-rules §24).
- Conflict-strategy and status filter options now show Chinese labels;
  the underlying contract values (`skip` / `overwrite` / `rename`,
  `pending` / `approved` / `rejected`) are unchanged.

### Removed

- Example plugins are no longer auto-loaded into the production toolbar
  ("Say Hello" / "Import People (Demo)" / "Stats Report" no longer appear in
  the main window). The plugin mechanism is fully retained as an external
  extension point (`PluginRegistry.load_from_path`); the example files stay
  in `examples/plugins/` for developer reference.

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
- **Terminal events lost to late signal wiring (macOS CI race)**: a task
  that terminated between the executor's `submit()` and the view's signal
  wiring fired its terminal event with zero receivers connected — the UI
  never learned the task ended and the affected action stayed disabled
  forever (surfaced as the export e2e 15s timeout on macOS CI). The worker
  runnable now retains its terminal event, and all four connect sites
  replay it right after the wiring completes.
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
  underlying guard-race was subsequently root-caused as a real production
  race and fixed via terminal-event replay (see above).

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
