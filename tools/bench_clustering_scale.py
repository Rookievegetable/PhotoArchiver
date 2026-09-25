"""Clustering scale/memory benchmark — Stage F 相似度矩阵风险量化（证据工具）.

量化 Stage D 聚类在目标规模下的三大成本（owner 任务书 checkpoint 3）：

1. 相似度全矩阵内存（``NumpyCosineSimilarityLookup``：n²×8B float64）；
2. 候选阶段（贪心，O(n·k) 次簇心余弦）；
3. 完全链接合并（增量 cross-min 维护）。

合成向量按"人物中心 + 噪声"生成（seeded RNG，确定性），与真实观测的
簇结构同构。**只采集证据，不做优化**——若数据证明当前规模（~1500 观测）
内存/耗时可接受，则"全矩阵优化"继续作为 F 阶段后续项记录。

Recorded results (local Windows, CPU, numpy float64, 2026-09-25 — Stage F
evidence baseline, deterministic seed 20260925, 6 person centers, noise
±0.30, thresholds 0.5/0.4/0.0):

    scale  matrix_MB  matrix_build_s  cluster_total_s  tracemalloc_peak_MB  clusters
      250        0.50            0.004            0.248                 1.05        22
      500        2.00            0.004            0.593                 4.09        28
     1000        8.00            0.008            1.698                16.19        35
     2000       32.00            0.037            4.666                64.37        37
     4000      128.00            0.132           15.983               256.74        40

Finding: memory scales n² (128 MB @4000; 512 MB @8000 by linear probe);
clustering wall time is dominated by the candidate phase (O(n·k) centroid
fancy-indexing). At the current known scale (~1500 observations from the
real 473-photo library) both are acceptable (<5 s, <20 MB); chunked/streamed
similarity remains a recorded follow-up for 10k+ observation libraries,
NOT a current blocker.

Usage:

    python tools/bench_clustering_scale.py                       # default grid
    python tools/bench_clustering_scale.py --scales 250,1000
"""

from __future__ import annotations

import argparse
import random
import sys
import time
import tracemalloc
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from photo_archiver.domain import (  # noqa: E402
    ClusteringItem,
    FaceEmbedding,
    cluster_items,
)
from photo_archiver.infrastructure import NumpyCosineSimilarityLookup  # noqa: E402


def synthetic_vectors(scale: int, person_centers: int = 6, noise: float = 0.30,
                      dimension: int = 8, seed: int = 20260925) -> list[tuple[float, ...]]:
    """Deterministic person-center + noise vectors（与真实观测同构）。"""
    rng = random.Random(seed)
    centers = [tuple(rng.uniform(-1, 1) for _ in range(dimension))
               for _ in range(person_centers)]
    return [
        tuple(rng.choice(centers)[axis] + rng.uniform(-noise, noise)
              for axis in range(dimension))
        for _ in range(scale)
    ]


def measure(scale: int) -> dict:
    """Measure matrix build + clustering for one scale (deterministic)."""
    vectors = synthetic_vectors(scale)
    items = [ClusteringItem(observation_id=uuid4(), quality_score=1.0)
             for _ in vectors]

    tracemalloc.start()
    start = time.perf_counter()
    lookup = NumpyCosineSimilarityLookup([FaceEmbedding(v) for v in vectors])
    matrix_build_s = time.perf_counter() - start

    start = time.perf_counter()
    assignments = cluster_items(items, lookup)
    total_s = time.perf_counter() - start
    peak_mb = tracemalloc.get_traced_memory()[1] / 1e6
    tracemalloc.stop()

    return {
        "scale": scale,
        "matrix_mb": round(scale * scale * 8 / 1e6, 2),
        "matrix_build_s": round(matrix_build_s, 3),
        "candidate_merge_total_s": round(total_s, 3),
        "tracemalloc_peak_mb": round(peak_mb, 2),
        "clusters": len(assignments),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage D clustering scale/memory benchmark (Stage F evidence).",
    )
    parser.add_argument("--scales", default="250,500,1000,2000,4000")
    args = parser.parse_args()
    scales = [int(value) for value in args.scales.split(",") if value.strip()]

    header = (f"{'scale':>6} {'matrix_MB':>10} {'matrix_s':>9} "
              f"{'cluster_s':>10} {'peak_MB':>8} {'clusters':>9}")
    print(header)
    print("-" * len(header))
    for scale in scales:
        row = measure(scale)
        print(f"{row['scale']:>6} {row['matrix_mb']:>10} {row['matrix_build_s']:>9} "
              f"{row['candidate_merge_total_s']:>10} {row['tracemalloc_peak_mb']:>8} "
              f"{row['clusters']:>9}")
    print("done — record numbers in this file's docstring (evidence baseline)")
    return 0


if __name__ == "__main__":
    __import__("sys").exit(main())
