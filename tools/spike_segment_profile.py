"""Segment decomposition spike for the recognition hot path (W2 pre-gate evidence).

Question: where do the ~143 ms/photo of non-inference time go (phase6 W1 verdict:
end-to-end 5.06 photos/s vs ~13.7 pure-inference ceiling, gap is GIL-serial)?

Method (wraps pure-Python model objects only - ORT InferenceSession is pybind
and read-only, so session.run cannot be patched):
- wrap FaceAnalysis.models['detection'].detect  -> t_det  (preprocess+ORT+decode/NMS)
- wrap models['w600k_r50'].get                  -> t_rec  (alignment+ORT)
- wrap models['genderage'].get                  -> t_ga   (attrs discarded by production)
- wrap every models['landmark_*'].get           -> t_lm   (dead weight: production consumes only bbox+kps+embedding)
- wrap analysis.get                             -> t_get  (whole black box)
- time cv2.imread separately (production reads the file per photo)
- time the numpy->tuple pair conversion separately
residue = t_get - t_det - t_rec - t_ga - t_lm   (anchor decode/NMS + misc python)

A/B removal: pop landmark (then landmark+genderage) models out of
analysis.models and re-measure detect_with_embeddings wall - the direct
production gain of a loader-side pack filter (phase7 candidate fix).

Accounting note (v2): serial rows are snapshotted immediately after the
serial loop, and every accumulator is reset before wall_check / concurrency.
v1 bug (recorded for honesty): the serial rows were computed AFTER the
concurrency phase had polluted every accumulator, producing garbage rows
like det=886ms; only the phase-local timers were valid in v1.

Concurrency stretch: a 4-thread pass over the same images; comparing cumulative
model-ORT time vs wall time gives the empirical GIL-serial ceiling.

Output is ASCII-only to survive PowerShell redirection. Numbers are recorded in
docs/development/phase7-adr-draft.md once drafted.

RESULTS (v2, 2026-08-29, Ryzen 7 5800H 8C16T, ORT 1.27.0 CPU, intra=ORT default 8):

== A/B dead-weight removal (ms/photo, mean of 15) ==
  full pack                254.4
  - landmark models        167.1  (1.522x)   <- 1k3d68 + 2d106det, zero production consumers
  - landmark + genderage   128.2  (1.985x)   <- Person domain has no gender/age fields

== serial decomposition (ms/photo, mean of 30; accounting closes: 251.3 ~ 249.4 ~ 254.4) ==
  imread 1.9 | det.detect 96.2 (ORT ~57) | rec.get 107.8 (ORT ~30, rest cv2 align)
  | genderage 9.8 | landmarks 35.4 | residue 0.2

== concurrency (4 threads, 60 tasks) ==
  5.66 photos/s (1.44x); cumulative ORT = 390% of wall -> inference overlaps well,
  remainder is the GIL-serial non-inference segment.

VERDICT: biggest win is two lines of loader config (allowed_modules), not
concurrency surgery. Phase 7 pre-gate drafted on this evidence.

"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import cv2  # noqa: E402

from photo_archiver.infrastructure.ai.insightface_loader import (  # noqa: E402
    InsightFaceLoader,
)

SAMPLE_FACE = REPO_ROOT / "tests" / "integration" / "resources" / "sample_face.jpg"
MODEL_ROOT = REPO_ROOT / "resources" / "models"

WARMUP = 3
ITERS = 30
WALL_ITERS = 10
THREADS = 4
CONC_TASKS = 60
ABL_ITERS = 15


class _Timed:
    """Cumulative wall-time accumulator with optional function wrapping."""

    def __init__(self) -> None:
        self.total = 0.0
        self.calls = 0
        self._lock = Lock()

    def add(self, seconds: float) -> None:
        with self._lock:
            self.total += seconds
            self.calls += 1

    def wrap(self, fn):
        def inner(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                self.add(time.perf_counter() - t0)

        return inner

    def snapshot(self) -> tuple[float, int]:
        with self._lock:
            return self.total, self.calls


def _convert_pairs(faces) -> int:
    """Replicate detect_with_embeddings' numpy->plain-python conversion cost."""
    n = 0
    for face in faces:
        float(face["bbox"][0])
        tuple(float(x) for x in face["embedding"].tolist())
        n += 1
    return n


def _pick(models: dict, *needles: str):
    for key, model in models.items():
        low = key.lower()
        if any(n in low for n in needles):
            return key, model
    return None, None


def main() -> int:
    print(f"cpu_count={os.cpu_count()}")
    loader = InsightFaceLoader(MODEL_ROOT)
    if not loader.is_available():
        print(f"model pack not available under {MODEL_ROOT}")
        return 1
    analysis = loader.load()
    models = analysis.models
    det_key, det_model = _pick(models, "detection")
    rec_key, rec_model = _pick(models, "w600k", "arcface", "recognition")
    ga_key, ga_model = _pick(models, "genderage")
    print(f"models: det={det_key} rec={rec_key} ga={ga_key}")

    t_imread, t_get = _Timed(), _Timed()
    t_det, t_rec, t_ga, t_lm = _Timed(), _Timed(), _Timed(), _Timed()
    det_model.detect = t_det.wrap(det_model.detect)
    if rec_model is not None:
        rec_model.get = t_rec.wrap(rec_model.get)
    if ga_model is not None:
        ga_model.get = t_ga.wrap(ga_model.get)
    lm_wrapped = 0
    for key, model in models.items():
        if "landmark" in key.lower() and hasattr(model, "get"):
            model.get = t_lm.wrap(model.get)
            lm_wrapped += 1
    analysis.get = t_get.wrap(analysis.get)
    print(f"landmark models wrapped: {lm_wrapped}")

    def imread(path: Path):
        t0 = time.perf_counter()
        out = cv2.imread(str(path))
        t_imread.add(time.perf_counter() - t0)
        return out

    conv_total = 0.0
    for i in range(WARMUP + ITERS):
        img = imread(SAMPLE_FACE)
        faces = analysis.get(img, max_num=0)
        t0 = time.perf_counter()
        _convert_pairs(faces)
        conv_total += time.perf_counter() - t0
        if i == WARMUP - 1:  # drop warmup from accumulators
            for acc in (t_imread, t_get, t_det, t_rec, t_ga, t_lm):
                acc.total, acc.calls = 0.0, 0
            conv_total = 0.0

    # ── v2 fix: snapshot serial rows BEFORE later phases pollute the accumulators ──
    n = ITERS
    serial_rows = [
        ("imread (jpeg decode)", t_imread.total / n),
        ("det.detect (pre+ort+post)", t_det.total / n),
        ("rec.get (align+ort)", t_rec.total / n),
        ("ga.get (align+ort)", t_ga.total / n),
        ("lm.get (landmark dead wt)", t_lm.total / n),
        ("get residue (py/NMS/misc)", (t_get.total - t_det.total - t_rec.total - t_ga.total - t_lm.total) / n),
        ("pair conversion", conv_total / n),
    ]
    serial_get_ms = t_get.total / n * 1000
    for acc in (t_imread, t_get, t_det, t_rec, t_ga, t_lm):  # reset: later phases must be clean
        acc.total, acc.calls = 0.0, 0

    from photo_archiver.ai.insightface_detector import InsightFaceDetector  # noqa: E402

    detector = InsightFaceDetector(analysis)
    wall_check = 0.0
    for _ in range(WALL_ITERS):
        t0 = time.perf_counter()
        detector.detect_with_embeddings(SAMPLE_FACE)
        wall_check += time.perf_counter() - t0

    for acc in (t_get, t_det, t_rec, t_ga, t_lm):  # reset again: concurrency must be phase-clean
        acc.total, acc.calls = 0.0, 0

    tasks = [SAMPLE_FACE] * CONC_TASKS
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        list(pool.map(lambda _: detector.detect_with_embeddings(SAMPLE_FACE), tasks))
    conc_wall = time.perf_counter() - t0
    ort_cum = t_det.total + t_rec.total + t_ga.total + t_lm.total
    serial_wall = (wall_check / WALL_ITERS) * CONC_TASKS

    # ── A/B: pop dead-weight models, re-measure wall, restore ──
    def _abl(label: str, pop_needles: tuple[str, ...]) -> float:
        keys = [k for k in analysis.models if any(nd in k.lower() for nd in pop_needles)]
        removed = {k: analysis.models.pop(k) for k in keys}
        for _ in range(3):  # warmup with reduced pack
            detector.detect_with_embeddings(SAMPLE_FACE)
        t0 = time.perf_counter()
        for _ in range(ABL_ITERS):
            detector.detect_with_embeddings(SAMPLE_FACE)
        wall = (time.perf_counter() - t0) / ABL_ITERS
        analysis.models.update(removed)  # restore
        print(f"  A/B {label:<30} {wall * 1000:8.1f} ms/photo  popped: {','.join(keys) or 'none'}")
        return wall

    base_ms = wall_check / WALL_ITERS * 1000
    print()
    print(f"== A/B dead-weight removal (ms/photo, mean of {ABL_ITERS}) ==")
    print(f"  {'baseline (full pack)':<30} {base_ms:8.1f}")
    abl_lm = _abl("without landmark models", ("landmark",))
    abl_lm_ga = _abl("without landmark+genderage", ("landmark", "genderage"))

    accounted = sum(v for _, v in serial_rows)
    print()
    print("== serial decomposition (ms/photo, mean of %d) ==" % n)
    for name, v in serial_rows:
        print(f"  {name:<28} {v * 1000:8.1f}")
    print(f"  {'sum (accounted)':<28} {accounted * 1000:8.1f}")
    print(f"  {'analysis.get total':<28} {serial_get_ms:8.1f}")
    print(f"  {'detect_with_embed wall':<28} {base_ms:8.1f}")
    print()
    print(f"== concurrency ({THREADS} threads, {CONC_TASKS} tasks) ==")
    print(f"  wall_s                {conc_wall:8.2f}")
    print(f"  photos/s              {CONC_TASKS / conc_wall:8.2f}")
    print(f"  ort_cumulative_s      {ort_cum:8.2f}")
    print(f"  ort share of wall     {ort_cum / conc_wall * 100:8.1f}%")
    print(f"  serial-equiv wall_s   {serial_wall:8.2f}")
    print(f"  speedup vs serial     {serial_wall / conc_wall:8.2f}x")
    print()
    print("== A/B summary ==")
    print(f"  full pack              {base_ms:8.1f} ms/photo")
    print(f"  - landmarks            {abl_lm * 1000:8.1f} ms/photo  ({base_ms / (abl_lm * 1000):6.3f}x)")
    print(f"  - landmarks+genderage  {abl_lm_ga * 1000:8.1f} ms/photo  ({base_ms / (abl_lm_ga * 1000):6.3f}x)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
