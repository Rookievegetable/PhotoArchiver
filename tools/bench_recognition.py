"""Offline throughput benchmark for the recognition pipeline (phase6 pre-gate A-1).

Measures end-to-end per-photo recognition cost (detect -> embed -> match ->
persist) across library scales and worker counts, driving the REAL InsightFace
adapters and the REAL ``MatchPersonsService`` parallel path (``max_workers``).
No database is involved: persistence goes to an in-memory collecting stub and
candidate embeddings are seeded from the real sample face, so the numbers
isolate pipeline throughput from SQLite write cost.

Usage (repo root, project venv active):

    python tools/bench_recognition.py                           # full grid
    python tools/bench_recognition.py --scales 100 --workers 1  # single cell
    python tools/bench_recognition.py --scales 100,600 --workers 1,2

Grid per phase6 spec: scales 100/600/2600 x workers 1/2/4. The full grid on
CPU takes a while; smoke a single cell first. Re-run numbers are recorded in
this docstring (anti-regression baseline, same convention as
bench_plugin_search.py).

Recorded results (local Windows, CPUExecutionProvider, 2026-08-29 — phase6 A-1
baseline, full grid exit 0, every cell 100% results / all PENDING / equivalence
invariants hold at every worker count):

    scale workers   wall_s  photos/s
     100     1      23.50     4.26
     100     2      23.81     4.20
     100     4      20.96     4.77
     600     1     161.79     3.71
     600     2     131.37     4.57
     600     4     123.08     4.88
    2600     1     656.94     3.96   (serial path)
    2600     2     574.69     4.52   1.14x vs serial
    2600     4     514.00     5.06   1.28x vs serial

Finding: per-photo thread scaling is modest — the onnxruntime session's internal
intra-op pool already saturates CPU cores during a single FaceAnalysis.get(), so
worker threads mostly overlap Python-side overhead. Batch inference (phase6 §8
A-2=B) is the follow-up candidate for real throughput gains.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from tempfile import mkdtemp
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from photo_archiver.ai.insightface_detector import InsightFaceDetector  # noqa: E402
from photo_archiver.ai.insightface_recognizer import InsightFaceRecognizer  # noqa: E402
from photo_archiver.ai.similarity_matcher import CosinePersonMatcher  # noqa: E402
from photo_archiver.application.commands.match_persons import (  # noqa: E402
    MatchPersonsCommand,
)
from photo_archiver.application.services.match_persons_service import (  # noqa: E402
    MatchPersonsService,
)
from photo_archiver.domain.entities.person import Person  # noqa: E402
from photo_archiver.domain.repositories.face_embedding_repository import (  # noqa: E402
    FaceEmbeddingRepository,
)
from photo_archiver.domain.repositories.recognition_repository import (  # noqa: E402
    RecognitionRepository,
)
from photo_archiver.infrastructure.ai.insightface_loader import (  # noqa: E402
    InsightFaceLoader,
)

SAMPLE_FACE = REPO_ROOT / "tests" / "integration" / "resources" / "sample_face.jpg"
MODEL_ROOT = REPO_ROOT / "resources" / "models"


class _CollectingRecognitionRepository(RecognitionRepository):
    """In-memory sink for recognition results — never touches SQLite."""

    def __init__(self) -> None:
        self.results: list = []

    def add(self, result) -> None:
        self.results.append(result)

    def add_many(self, results) -> None:
        self.results.extend(results)


class _SeededEmbeddingRepository(FaceEmbeddingRepository):
    """In-memory candidate store seeded with the real sample-face embedding.

    Candidate lookups accept any call shape and always return the full seeded
    set (1:N matching is global by design); ``save`` mirrors the port API.
    """

    def __init__(self) -> None:
        self._items: dict = {}

    def save(self, person_id, embedding) -> None:
        self._items[person_id] = embedding

    def list_all(self, *args, **kwargs):
        return dict(self._items)

    def load_all(self, *args, **kwargs):
        return list(self._items.items())

    def list_by_person(self, *args, **kwargs):
        return list(self._items.items())

    def list_embeddings(self, *args, **kwargs):
        return list(self._items.items())


class _NoopProgress:
    """Swallows any progress-reporting call shape (A-4 semantics not timed)."""

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def _status_of(result):
    """Best-effort status extraction across RecognitionResult field names."""
    for attr in ("status", "match_status"):
        value = getattr(result, attr, None)
        if value is not None:
            return value
    return "matched" if getattr(result, "person_id", None) is not None else "unknown"


def _build_library(scale: int, target_dir: Path) -> list[Path]:
    """Replicate the real sample face into ``scale`` jpeg files."""
    if not SAMPLE_FACE.exists():
        raise SystemExit(f"sample face not found: {SAMPLE_FACE}")
    paths: list[Path] = []
    for i in range(scale):
        target = target_dir / f"photo_{i:05d}.jpg"
        if not target.exists():
            shutil.copyfile(SAMPLE_FACE, target)
        paths.append(target)
    return paths


def _seed_candidates(embedding_repo, detector) -> None:
    """Create one anchor person whose embedding comes from the sample face."""
    boxes = detector.detect_with_embeddings(SAMPLE_FACE)
    if not boxes:
        raise SystemExit("sample face produced no embedding — model pack broken?")
    person = Person(name="bench-anchor")
    embedding_repo.save(person.id, boxes[0].embedding)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recognition pipeline throughput benchmark (phase6 A-1)."
    )
    parser.add_argument("--scales", default="100,600,2600", help="comma-separated")
    parser.add_argument("--workers", default="1,2,4", help="comma-separated")
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()
    scales = [int(s) for s in args.scales.split(",") if s.strip()]
    worker_grid = [int(w) for w in args.workers.split(",") if w.strip()]

    loader = InsightFaceLoader(MODEL_ROOT)
    if not loader.is_available():
        print(f"model pack not available under {MODEL_ROOT} — nothing to measure")
        return 1
    analysis = loader.load()
    detector = InsightFaceDetector(analysis)
    recognizer = InsightFaceRecognizer(analysis)
    matcher = CosinePersonMatcher()

    workdir = Path(mkdtemp(prefix="bench_recognition_"))
    print(f"building synthetic library ({max(scales)} photos) under {workdir}")
    all_paths = _build_library(max(scales), workdir)
    emb_repo = _SeededEmbeddingRepository()
    _seed_candidates(emb_repo, detector)

    header = f"{'scale':>6} {'workers':>7} {'wall_s':>9} {'photos/s':>9} {'results':>8}  statuses"
    print(header)
    print("-" * len(header))
    for scale in scales:
        paths = all_paths[:scale]
        for workers in worker_grid:
            rec_repo = _CollectingRecognitionRepository()
            service = MatchPersonsService(
                detector=detector,
                recognizer=recognizer,
                matcher=matcher,
                face_embedding_repository=emb_repo,
                recognition_repository=rec_repo,
                progress_reporter=_NoopProgress(),
                max_workers=workers,
            )
            command = MatchPersonsCommand(
                photo_ids=tuple(uuid4() for _ in paths),
                images=tuple(paths),
            )
            start = time.perf_counter()
            service.execute(command)
            wall = time.perf_counter() - start
            histogram = ", ".join(
                f"{k}={v}" for k, v in sorted(Counter(str(_status_of(r)) for r in rec_repo.results).items())
            )
            print(
                f"{scale:>6} {workers:>7} {wall:>9.2f} {scale / wall:>9.2f}"
                f" {len(rec_repo.results):>8}  {histogram}"
            )
    if not args.keep_temp:
        shutil.rmtree(workdir, ignore_errors=True)
    print("done — record numbers in this file's docstring (anti-regression baseline)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())