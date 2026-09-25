"""Stage F full-chain validation & calibration evidence tool.

Stage F（校准、性能与生产验证）的证据工具：对**真实照片目录**（默认
E:\\BaiduNetdiskDownload\\测试Photo，473 张中文路径照片）执行完整生产链：

    扫描登记（中文路径）→ 真实 InsightFace 识别（全脸 → FaceObservation）
    → Stage D 聚类（numpy kernel，(person, photo) 之前的原始簇）
    → 二次聚类（generation 幂等证据）→ Stage E 建议生成
    → 确认（样本沉淀 + D3 兼容 APPROVED）→ ArchivePlanner (person, photo)

全部数据写入一次性验证库（``--db``，默认临时目录）——**绝不触碰生产库**。
输出校准证据：det/quality 分位数、脸数分布、簇规模分布、各阶段耗时、
聚类峰值内存、多 Person attribution 计数。**只采集证据，不改任何阈值**
（阈值变化必须走 Owner/规格裁决，见校准报告文档）。

用法（repo 根，项目 venv）：

    python tools/validate_stage_f.py                 # 全量 473 张
    python tools/validate_stage_f.py --limit 50      # 快速冒烟
    python tools/validate_stage_f.py --report out.json --keep-db

聚类规模/内存专项基准见 ``tools/bench_clustering_scale.py``。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import tracemalloc
from collections import Counter
from pathlib import Path
from tempfile import mkdtemp

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

MODEL_ROOT = REPO_ROOT / "resources" / "models"
DEFAULT_PHOTO_DIR = r"E:\BaiduNetdiskDownload\测试Photo"
CONFIRM_BUDGET = 6  # 确认前 N 条建议（覆盖多簇/多照片归属证据）

PERCENTILE_TICKS = (10, 25, 50, 75, 90)


def percentile(values: list[float], tick: int) -> float | None:
    """最近秩分位数（确定性；空集合返回 None）。"""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * tick / 100)))
    return round(float(ordered[rank]), 6)


def percentile_table(values: list[float]) -> dict[str, float | None]:
    """P10/P25/P50/P75/P90 一览。"""
    return {
        f"p{tick}": percentile(values, tick) for tick in PERCENTILE_TICKS
    }


def distribution(values: list[int]) -> dict[str, int]:
    """整数值计数分布，键为字符串（JSON 友好）、按值升序。"""
    return {str(value): count for value, count in sorted(Counter(values).items())}


def cluster_size_buckets(sizes: list[int]) -> dict[str, int]:
    """簇规模分桶，供簇结构证据阅读（分带仅聚合展示，非阈值裁决）。"""
    buckets = {"1": 0, "2-5": 0, "6-10": 0, "11-20": 0, "21-50": 0, "51+": 0}
    for size in sizes:
        if size <= 1:
            buckets["1"] += 1
        elif size <= 5:
            buckets["2-5"] += 1
        elif size <= 10:
            buckets["6-10"] += 1
        elif size <= 20:
            buckets["11-20"] += 1
        elif size <= 50:
            buckets["21-50"] += 1
        else:
            buckets["51+"] += 1
    return buckets


def quality_bands(values: list[float]) -> dict[str, int]:
    """质量分证据分带（不做任何阈值裁决，仅计数供 Owner 参考）。"""
    bands = {"<0.30": 0, "0.30-0.50": 0, "0.50-0.70": 0, "0.70-0.90": 0, ">=0.90": 0}
    for value in values:
        if value < 0.30:
            bands["<0.30"] += 1
        elif value < 0.50:
            bands["0.30-0.50"] += 1
        elif value < 0.70:
            bands["0.50-0.70"] += 1
        elif value < 0.90:
            bands["0.70-0.90"] += 1
        else:
            bands[">=0.90"] += 1
    return bands


def _load_step(step: str, payload: dict) -> None:
    print(f"[stage-f] {step}: {json.dumps(payload, ensure_ascii=False)}")


def run_validation(photo_dir: Path, db_path: Path, limit: int, workers: int) -> dict:
    """Execute the full chain; returns the evidence report dict."""
    report: dict = {"photo_dir": str(photo_dir), "db": str(db_path), "limit": limit}

    # ── 1. 扫描登记（真实中文路径） ─────────────────────────────────────
    from photo_archiver.app.repositories import build_sqlite_repositories

    repositories = build_sqlite_repositories(db_path)
    from photo_archiver.application.commands.scan_and_register_photos import (
        ScanAndRegisterPhotosCommand,
    )
    from photo_archiver.application.services.scan_and_register_photos_service import (
        ScanAndRegisterPhotosService,
    )
    from photo_archiver.infrastructure import LocalPhotoFileScanner

    scan_service = ScanAndRegisterPhotosService(
        LocalPhotoFileScanner(), repositories.folders, repositories.photos,
    )
    start = time.perf_counter()
    scan_result = scan_service.execute(
        ScanAndRegisterPhotosCommand(folder_path=photo_dir),
    )
    _load_step("scan", {
        "discovered": scan_result.discovered_count,
        "registered": scan_result.registered_count,
        "skipped": scan_result.skipped_count,
        "failed": scan_result.failed_count,
        "wall_s": round(time.perf_counter() - start, 2),
    })
    photos = repositories.photos.list_all()
    if limit > 0:
        photos = photos[:limit]
    photo_ids = tuple(photo.id for photo in photos if photo.id is not None)
    images = tuple(photo.path.raw_path for photo in photos if photo.id is not None)
    report["photos"] = len(photo_ids)

    # ── 2. 真实 InsightFace 识别（全脸 → FaceObservation） ─────────────
    from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
    from photo_archiver.infrastructure.ai.insightface_loader import InsightFaceLoader

    loader = InsightFaceLoader(MODEL_ROOT)
    if not loader.is_available():
        raise SystemExit(f"model pack not available under {MODEL_ROOT}")
    analysis = loader.load()
    from photo_archiver.ai.insightface_detector import InsightFaceDetector

    detector = InsightFaceDetector(analysis)
    matcher = CosinePersonMatcher(threshold=0.40)
    from photo_archiver.application.commands.start_recognition_run import (
        StartRecognitionRunCommand,
    )
    from photo_archiver.application.services.run_recognition_service import (
        RunRecognitionService,
    )

    recognition_service = RunRecognitionService(
        detector=detector,
        matcher=matcher,
        face_embedding_repository=repositories.face_embeddings,
        recognition_repository=repositories.recognition,
        recognition_run_repository=repositories.recognition_runs,
        face_observation_repository=repositories.face_observations,
        max_workers=workers,
    )
    start = time.perf_counter()
    recognition_run = recognition_service.execute(StartRecognitionRunCommand(
        photo_ids=photo_ids, images=images,
    ))
    recognition_wall = round(time.perf_counter() - start, 2)
    report["recognition"] = {
        "wall_s": recognition_wall,
        "photos_per_s": round(len(photo_ids) / recognition_wall, 2),
        "workers": workers,
        "status": recognition_run.status,
        "face_count": recognition_run.face_count,
        "unreadable_count": recognition_run.unreadable_count,
        "no_face_count": recognition_run.no_face_count,
        "error_count": recognition_run.error_count,
        "in_scope_photo_count": recognition_run.in_scope_photo_count,
        "out_of_scope_photo_count": recognition_run.out_of_scope_photo_count,
    }
    _load_step("recognition", report["recognition"])

    # ── 3. Stage D 聚类（首次） ─────────────────────────────────────────
    from photo_archiver.application.commands.cluster_faces import (
        StartClusteringRunCommand,
    )
    from photo_archiver.application.services.cluster_faces_service import (
        ClusterFacesService,
    )

    clustering_service = ClusterFacesService(
        repositories.recognition_runs,
        repositories.face_observations,
        repositories.face_clusters,
        __import__("photo_archiver.infrastructure", fromlist=[
            "NumpyCosineSimilarityFactory",
        ]).NumpyCosineSimilarityFactory(),
    )
    tracemalloc.start()
    start = time.perf_counter()
    first_generation = clustering_service.execute(
        StartClusteringRunCommand(recognition_run.id),
    )
    clustering_wall = round(time.perf_counter() - start, 2)
    clustering_peak_mb = round(tracemalloc.get_traced_memory()[1] / 1e6, 2)
    tracemalloc.stop()
    clusters = repositories.face_clusters.list_clusters(first_generation.id)
    cluster_sizes = [cluster.member_count for cluster in clusters]
    report["clustering_first"] = {
        "wall_s": clustering_wall,
        "tracemalloc_peak_mb": clustering_peak_mb,
        "status": first_generation.status,
        "cluster_count": first_generation.cluster_count,
        "member_count": first_generation.member_count,
        "excluded_count": first_generation.excluded_count,
        "singleton_clusters": sum(1 for size in cluster_sizes if size == 1),
        "size_buckets": cluster_size_buckets(cluster_sizes),
    }
    _load_step("clustering", report["clustering_first"])

    # ── 4. 二次聚类（generation 幂等证据） ─────────────────────────────
    second_generation = clustering_service.execute(
        StartClusteringRunCommand(recognition_run.id),
    )
    second_clusters = repositories.face_clusters.list_clusters(second_generation.id)
    report["clustering_rerun"] = {
        "generation_count": len(repositories.face_clusters.list_cluster_runs(
            recognition_run.id,
        )),
        "first_cluster_count": first_generation.cluster_count,
        "second_cluster_count": len(second_clusters),
        "history_preserved": (
            len(repositories.face_clusters.list_clusters(first_generation.id))
            == first_generation.cluster_count
        ),
    }
    _load_step("clustering_rerun", report["clustering_rerun"])

    # ── 5. 校准证据：检测分/质量分/脸数分布 ────────────────────────────
    observations = repositories.face_observations.list_by_run(recognition_run.id)
    det_scores = [observation.det_score for observation in observations]
    quality_scores = [
        observation.quality_score for observation in observations
        if observation.quality_score is not None
    ]
    faces_per_photo = distribution([
        len(repositories.face_observations.list_by_run_photo(
            recognition_run.id, photo_id,
        ))
        for photo_id in photo_ids
    ])
    report["calibration"] = {
        "det_score": {**percentile_table(det_scores), "bands": quality_bands(det_scores)},
        "quality_score": {
            **percentile_table(quality_scores), "bands": quality_bands(quality_scores),
        },
        "faces_per_photo": faces_per_photo,
        "observations": len(observations),
    }
    _load_step("calibration", report["calibration"])

    # ── 6. Stage E：建议 → 确认 → 兼容 → ArchivePlanner ────────────────
    roster_size = min(max(first_generation.cluster_count, 1), 10)
    for index in range(roster_size):
        repositories.people.add(__import__(
            "photo_archiver.domain", fromlist=["Person"],
        ).Person(name=f"校准人员{index + 1:02d}", roster_order=index + 1))
    from photo_archiver.application.commands.pairing import (
        ConfirmAssignmentCommand,
        StartSuggestPairingsCommand,
    )
    from photo_archiver.application.services.pairing_workbench_service import (
        PairingWorkbenchService,
    )
    from photo_archiver.application.services.suggest_pairings_service import (
        SuggestPairingsService,
    )

    suggest_service = SuggestPairingsService(
        repositories.face_clusters, repositories.face_observations,
        repositories.people, repositories.cluster_assignments,
        repositories.person_face_samples,
        __import__("photo_archiver.infrastructure", fromlist=[
            "NumpyCosineSimilarityFactory",
        ]).NumpyCosineSimilarityFactory(),
    )
    summary = suggest_service.execute(
        StartSuggestPairingsCommand(first_generation.id),
    )
    report["stage_e_suggestions"] = {
        "suggestions": summary.suggestions,
        "ordered": summary.ordered,
        "sample_matched": summary.sample_matched,
        "unmatched_clusters": summary.unmatched_clusters,
        "roster_size": roster_size,
    }
    _load_step("stage_e_suggestions", report["stage_e_suggestions"])

    active = repositories.cluster_assignments.list_active_by_cluster_run(
        first_generation.id,
    )
    workbench = PairingWorkbenchService(
        repositories.cluster_assignments, repositories.face_clusters,
        repositories.face_observations, repositories.people,
        repositories.recognition, repositories.person_face_samples,
    )
    confirmed = 0
    compat_rows = 0
    for assignment in active[:CONFIRM_BUDGET]:
        result = workbench.confirm(ConfirmAssignmentCommand(assignment.id))
        confirmed += 1
        compat_rows += result.compat_results_written
    report["stage_e_confirmation"] = {
        "confirmed": confirmed,
        "compat_approved_rows": compat_rows,
        "samples_total": len(repositories.person_face_samples.list_enabled()),
    }
    _load_step("stage_e_confirmation", report["stage_e_confirmation"])

    from photo_archiver.application.services.archive_planner import ArchivePlanner
    from photo_archiver.infrastructure.database.sqlite_archive_record_repository import (
        SQLiteArchiveRecordRepository,
    )

    planner = ArchivePlanner(
        __import__("photo_archiver.application.services", fromlist=[
            "ArchivePathBuilderService",
        ]).ArchivePathBuilderService(),
        repositories.people, repositories.photos, repositories.recognition,
        SQLiteArchiveRecordRepository(
            repositories._connection_provider,
        ),
    )
    confirmed_person_ids = tuple(
        repositories.cluster_assignments.list_confirmed_person_ids(
            first_generation.id,
        ),
    )
    plan = planner.plan(str(db_path.parent / "archive-root"), confirmed_person_ids)
    report["archive_planner"] = {
        "confirmed_persons": len(confirmed_person_ids),
        "planned_count": plan.planned_count,
        "skipped_count": plan.skipped_count,
    }
    _load_step("archive_planner", report["archive_planner"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage F full-chain real-data validation & calibration evidence.",
    )
    parser.add_argument("--photo-dir", default=DEFAULT_PHOTO_DIR)
    parser.add_argument(
        "--db", default=None, help="validation DB path (default: temp dir)",
    )
    parser.add_argument("--limit", type=int, default=0, help="0 = all photos")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--report", default=None, help="evidence JSON output path")
    parser.add_argument("--keep-db", action="store_true")
    args = parser.parse_args()

    workdir = Path(mkdtemp(prefix="stage_f_validation_"))
    db_path = Path(args.db) if args.db else workdir / "stage_f_validation.sqlite3"
    report = run_validation(Path(args.photo_dir), db_path, args.limit, args.workers)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(f"[stage-f] evidence JSON written to {report_path}")
    if not args.keep_db and args.db is None:
        shutil.rmtree(workdir, ignore_errors=True)
    print("done — record numbers in the calibration report doc (evidence baseline)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
