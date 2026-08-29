"""Benchmark: ``PluginContextService.search_photos`` recognition N+1 lookups.

Phase 4 tech-debt round evidence tool (draft ``docs/development/phase4-adr-draft.md``
§2). Measures wall time and per-photo repository call count of the plugin search
path against a real temporary SQLite database at several photo scales, so the
N+1 pattern (one ``RecognitionRepository.list_by_photo`` call per matched photo,
see ``plugin_context_service.py`` search loop) is quantified rather than assumed.

**Cumulative-scale semantics**: sweeps share ONE database — the ``photos``
column reports the TOTAL library size accumulated across sweeps (100 → 600 →
2600), not per-sweep increments. Read ADR-029 before/after numbers against the
same cumulative column.

Zero third-party dependencies — stdlib only, safe to run offline:

    python tools/bench_plugin_search.py

Baseline numbers (durable anchor; review MINOR-3 fix, 2026-08-27):

    scale = cumulative photos   | repo_calls | wall_ms
                100             |     1      |   5.0
                600             |     1      |  16.2
               2600             |     1      |  63.4

    ADR-029 optimized baseline: 62.5 ms @2600 — delta +1.4% is a single-run
    noise band; calls stayed constant at 1 ⇒ zero regression (v2.0.0 tag
    retest). Record future retests here so the anti-regression anchor survives
    status-file housekeeping.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = PROJECT_ROOT / "src"
if SOURCE_ROOT.is_dir():
    sys.path.insert(0, str(SOURCE_ROOT))

from photo_archiver.application.dtos.plugin_context import PluginPhotoQuery  # noqa: E402
from photo_archiver.application.services.detect_duplicates_service import (  # noqa: E402
    DetectDuplicatesService,
)
from photo_archiver.application.services.import_people_service import ImportPeopleService  # noqa: E402
from photo_archiver.application.services.plugin_context_service import (  # noqa: E402
    PluginContextService,
)
from photo_archiver.application.services.search_photos_service import SearchPhotosService  # noqa: E402
from photo_archiver.app.repositories import ApplicationRepositories, build_sqlite_repositories  # noqa: E402
from photo_archiver.domain import Photo  # noqa: E402
from photo_archiver.domain.entities.recognition import RecognitionResult  # noqa: E402
from photo_archiver.domain.value_objects import PhotoPath  # noqa: E402
from photo_archiver.infrastructure.importers.txt_person_import_reader import (  # noqa: E402
    TxtPersonImportReader,
)

SCALES = (100, 500, 2000)


class _CountingRecognitionRepo:
    """Duck-typed wrapper counting EVERY delegated repository call.

    Phase 4 meter: after the N+1 fix the plugin search path must issue exactly
    ONE recognition repository call per search regardless of photo count.
    """

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.calls = 0

    def __getattr__(self, name: str) -> object:
        attr = getattr(self._inner, name)

        if callable(attr):

            def counted(*args: object, **kwargs: object) -> object:
                self.calls += 1
                return attr(*args, **kwargs)  # type: ignore[arg-type]

            return counted

        return attr


def _seed(repositories: ApplicationRepositories, scale: int, count: int) -> None:
    """Register ``count`` photos each with exactly one pending recognition result.

    Paths are namespaced by ``scale`` so successive sweeps into the same
    database never collide on the ``photos.raw_path`` UNIQUE constraint.
    """
    for index in range(count):
        photo_path = PhotoPath(Path(f"/bench/s{scale}/photo_{index}.jpg"))
        repositories.photos.add(Photo(path=photo_path))
    for photo in repositories.photos.list_all():
        repositories.recognition.add(RecognitionResult(photo_id=photo.id, confidence=0.9))  # type: ignore[arg-type]


def _build_context(
    repositories: ApplicationRepositories,
) -> tuple[PluginContextService, _CountingRecognitionRepo]:
    counting = _CountingRecognitionRepo(repositories.recognition)
    service = PluginContextService(
        SearchPhotosService(repositories.photos),
        DetectDuplicatesService(repositories.photos),
        counting,  # type: ignore[arg-type]
        ImportPeopleService(TxtPersonImportReader(), repositories.people),
    )
    return service, counting


def main() -> int:
    """Run the scale sweep and print one timing row per scale."""
    print("scale | photos | recognition repo calls | wall time (ms)")
    print("------|--------|------------------------|----------------")
    with tempfile.TemporaryDirectory(prefix="pabench_", ignore_cleanup_errors=True) as tmp:
        database_path = Path(tmp) / "bench.sqlite3"
        repositories = build_sqlite_repositories(database_path)
        seeded_total = 0
        for scale in SCALES:
            _seed(repositories, scale, scale)
            seeded_total += scale
            service, counting = _build_context(repositories)
            counting.calls = 0
            started = time.perf_counter()
            summaries = service.search_photos(PluginPhotoQuery())
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            assert len(summaries) == seeded_total, (
                "sanity: every seeded photo must match "
                f"(expected {seeded_total}, got {len(summaries)})"
            )
            print(
                f"search | {len(summaries):>6} | {counting.calls:>22} | {elapsed_ms:>14.1f}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())