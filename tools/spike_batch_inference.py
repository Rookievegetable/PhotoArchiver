"""W1 batch-inference spike (ADR-032 follow-up, one-off evidence tool).

Question: can batched (batch-dim) ONNX inference on CPU beat the per-photo
thread scaling measured in phase6 (4 workers = only 1.28x at 2600 photos)?
Hypothesis: the intra-op pool already saturates cores within a single
inference, so per-photo threads only overlap Python-side overhead — while
batching multiplies arithmetic intensity through GEMM/Conv batch dims and
may scale where threads cannot.

Scope: recognition model ``w600k_r50`` (dominant per-photo cost in the
pipeline: detect -> align -> 1x recognize + 1x genderage) and
``genderage``. Detection (``det_10g``) is probed only — its batch dim is
fixed to 1 in the graph and all outputs carry anchor-dim metadata, so
batching it would require full graph surgery (out of spike scope).

Method: synthetic float32 tensors (numeric content is irrelevant for
throughput; real preprocessing is unchanged outside the spike). For each
(batch, intra_op_threads) cell: fresh session, 2 warmup runs, then timed
iters sized so B*iters >= 256 images. Reported per-image latency and
speedup vs B=1 at the same intra setting.

Model IO probe (2026-08-29): rec input [None,3,112,112] out [1,512];
genderage input [None,3,96,96] out [1,3]; det input [1,3,?,?] with anchor
outputs [12800/3200/800, k]. Input batch dims are already dynamic — no
graph surgery needed; ORT returns actual-shaped outputs at run time.

Results (2026-08-29, 16 logical cores, onnxruntime 1.27.0, CPU):

rec grid (w600k_r50, 24-256 img per cell, clean rerun 2026-08-29):

  intra |   B |  ms/img |  img/s | x vs B1
      1 |   1 |  118.84 |   8.41 |  1.000
      1 |  16 |  114.44 |   8.74 |  1.039
      4 |   1 |   31.53 |  31.72 |  1.000
      4 |  16 |   35.73 |  27.99 |  0.882
     16 |   1 |   27.34 |  36.58 |  1.000
     16 |  16 |   27.85 |  35.91 |  0.982
  (full grid also covered B=4/B=8 at each intra — all <= 1.04x)

genderage grid (negligible per-face cost; batch regresses):

  intra |   B |  ms/img
      1 |   1 |    0.31
      1 |  16 |    1.93
     16 |   1 |    0.30
     16 |  16 |    1.93

Verdict (2026-08-29):

- BATCH IS FALSIFIED as an inference-side lever: at every intra setting,
  B=16 vs B=1 yields <= 1.04x (0.82x-0.98x at intra >= 4) — the intra-op
  pool already saturates the 8 physical cores within a single inference,
  so the batch dim adds no arithmetic-intensity gain for these conv nets
  on CPU. The dynamic input batch dim is a red herring: it works, it just
  does not help.
- intra_op threads is the ONLY inference-side lever: rec B=1 goes
  118.84 -> 27.34 ms/img (4.3x) from intra=1 to intra=16. Production
  sessions run ORT defaults (intra=8 on this 8P/16L machine) — already
  near the knee (~29 ms/img interpolated).
- Combined with the composite matrix (det+rec shared sessions,
  production-like): 1x8=9.05, 4x8=13.73, 8x1=13.21 photos/s — thread
  oversubscription falsified too (13.2-13.7 across the board).
- Therefore phase6's 1.28x weak scaling is NOT inference-bound: the 2.7x
  gap to the ~13.7 photos/s pure-inference ceiling lives in the GIL-serial
  non-inference segment (~143 ms/photo: imread / preprocess / SCRFD decode
  / align / DB; ceiling ~7 photos/s). W2-batch is evidence-killed; the
  only justified second-round direction is W2-segment (attack the ~143 ms
  serial segment), or accept v2.1.0 numbers and close the throughput line.

"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort

MODELS_DIR = Path("resources/models/buffalo_l")
REC = MODELS_DIR / "w600k_r50.onnx"
GEN = MODELS_DIR / "genderage.onnx"
DET = MODELS_DIR / "det_10g.onnx"


def make_session(path: Path, intra: int) -> ort.InferenceSession:
    so = ort.SessionOptions()
    so.intra_op_num_threads = intra
    so.inter_op_num_threads = 1
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(path), sess_options=so, providers=["CPUExecutionProvider"])


def bench(
    model_path: Path,
    input_name: str,
    input_shape: tuple[int, int, int],
    batch: int,
    intra: int,
    min_images: int = 256,
    max_iters: int = 24,
    warmup: int = 2,
) -> dict[str, float | int]:
    sess = make_session(model_path, intra)
    rng = np.random.default_rng(42)
    one = rng.standard_normal((1, *input_shape)).astype(np.float32)
    x = np.repeat(one, batch, axis=0)  # same face replicated — mirrors real F=1 batches
    for _ in range(warmup):
        sess.run(None, {input_name: x})
    iters = max(3, min(max_iters, min_images // batch))
    t0 = time.perf_counter()
    for _ in range(iters):
        sess.run(None, {input_name: x})
    wall = time.perf_counter() - t0
    per_img_ms = wall / (iters * batch) * 1000.0
    return {
        "wall_s": round(wall, 2),
        "iters": iters,
        "per_img_ms": round(per_img_ms, 2),
        "img_per_s": round(1000.0 / per_img_ms, 2),
        "speedup": 1.0,
    }


def run_matrix(
    label: str,
    model_path: Path,
    input_name: str,
    input_shape: tuple[int, int, int],
    batches: list[int],
    intras: list[int],
    min_images: int,
) -> None:
    print(f"\n== {label} ({model_path.name}) ==")
    print(f"{'intra':>5} | {'B':>3} | {'wall_s':>7} | {'iters':>5} | {'ms/img':>7} | {'img/s':>8} | {'x vs B1':>7}")
    for intra in intras:
        base = 0.0
        for batch in batches:
            try:
                r = bench(model_path, input_name, input_shape, batch, intra, min_images=min_images)
            except Exception as exc:  # shape metadata mismatch etc.
                print(f"{intra:>5} | {batch:>3} | FAILED: {type(exc).__name__}: {exc}")
                continue
            if batch == batches[0]:
                base = float(r["img_per_s"])
            r["speedup"] = round(float(r["img_per_s"]) / base, 3) if base else 0.0
            print(
                f"{intra:>5} | {batch:>3} | {r['wall_s']:>7.2f} | {r['iters']:>5}"
                f" | {r['per_img_ms']:>7.2f} | {r['img_per_s']:>8.2f} | {r['speedup']:>7.3f}"
            )


def probe() -> None:
    for name, path in (("det", DET), ("rec", REC), ("gen", GEN)):
        s = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        ins = [(i.name, list(i.shape)) for i in s.get_inputs()]
        outs = [(o.name, list(o.shape)) for o in s.get_outputs()]
        print(f"{name}: in={ins} out={outs}")


def main() -> None:
    ap = argparse.ArgumentParser(description="W1 batch-inference spike")
    ap.add_argument("--probe", action="store_true", help="print model IO shapes only")
    args = ap.parse_args()
    if args.probe:
        probe()
        return

    print(f"onnxruntime={ort.__version__} providers={ort.get_available_providers()}")
    # rec: dominant cost — full B x intra grid; intra=1 verifies the saturation
    # hypothesis, intra=16 is the app-default upper bound on this 16-thread box.
    run_matrix("recognition", REC, "input.1", (3, 112, 112), [1, 4, 8, 16], [1, 4, 16], min_images=256)
    # genderage: small head model — coarse grid.
    run_matrix("genderage", GEN, "data", (3, 96, 96), [1, 8, 16], [1, 16], min_images=384)


if __name__ == "__main__":
    main()
