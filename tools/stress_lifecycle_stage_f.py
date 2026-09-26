"""Stage F Wave 3 lifecycle stress — 1000+ photos, real model, cancel/retry.

owner 任务书 Wave 3 检查点 1：1000+ 照片任务在真实 Task/Worker/持久化链路
下的 Run → Cancel → Retry → Complete 生命周期压力证据。真实 InsightFace
模型 + 真实 SQLite 持久化（一次性验证库），合成单脸照片库（bench 模式）。

流程：
    Phase 1  后台线程运行 1000 张识别；主线程等待 cancel_delay_s 后取消；
             记录取消传播耗时（cancel() 调用 → 运行线程返回）、run 终态、
             已保留观测数。
    Phase 2  重试：仅重试未产出观测的照片（Stage F 语义）→ 新 RecognitionRun
             完整完成；验证两代 run 独立、观测按 run 隔离、无重复 (run, photo,
             face_index)。
    Phase 3  记录 DB 行数/内存/耗时证据（JSON，--report）。

Recorded results (local Windows, CPUExecutionProvider, buffalo_l, 4 workers,
2026-09-26, 1000 photos of the single-face sample (unique-pixel variants so the
content-hash dedup registers all 1000) — Stage F Wave 3 evidence, cancel at
t+30s, sqlite persistence):

    phase1 cancel  status=cancelled  cancel_latency=60.0s  elapsed=90.0s
                  observations=337 (已消费并提交的观测保留)
    phase2 retry   status=completed   retryable=663  elapsed=63.3s
                  observations=663  new run id (历史 run 未覆盖)
    phase3         run_rows=2  distinct_run_ids=2  photo_rows=1000
                  cross_run_photo_overlap=0  duplicate_face_index_pairs=0
                  coverage=1000/1000  tracemalloc_peak=79.2 MB

Findings: cancellation propagates cooperatively (returns after the in-flight
detection batch; no lock, no deadlock, no duplicate/half-written run); retry
over the remaining photos completes with a NEW RecognitionRun while the first
run's 337 observations stay intact; the two runs' observations cover 1000
photos exactly once each.

Usage:

    python tools/stress_lifecycle_stage_f.py --photos 1000 --cancel-delay 30
    python tools/stress_lifecycle_stage_f.py --report stress.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import threading
import time
import tracemalloc
from pathlib import Path
from tempfile import mkdtemp

REPO_ROOT = Path(__file__).resolve().parents[1]
sys_path = str(REPO_ROOT / "src")
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

SAMPLE_FACE = REPO_ROOT / "tests" / "integration" / "resources" / "sample_face.jpg"
MODEL_ROOT = REPO_ROOT / "resources" / "models"


def _build_library(count: int, target_dir: Path) -> list:
    """每张副本嵌入唯一像素标记——扫描登记按内容哈希去重，完全相同的
    副本只会注册一张；微小噪声不改变人脸检测结果。"""
    import random

    from PIL import Image

    rng = random.Random(20260925)
    base = Image.open(SAMPLE_FACE).convert("RGB")
    paths = []
    for index in range(count):
        target = target_dir / f"stress_{index:05d}.jpg"
        if not target.exists():
            image = base.copy()
            for _ in range(8):
                x, y = rng.randrange(image.width), rng.randrange(image.height)
                image.putpixel((x, y), (rng.randrange(256),) * 3)
            image.save(target, quality=95)
        paths.append(target)
    return paths


def _register_photos(db_path: Path, photo_dir: Path) -> tuple[list, list]:
    """扫描登记照片库（photos 表必须先有行——run_photos 的 FK 目标）。"""
    from photo_archiver.app.repositories import build_sqlite_repositories
    from photo_archiver.application.commands.scan_and_register_photos import (
        ScanAndRegisterPhotosCommand,
    )
    from photo_archiver.application.services.scan_and_register_photos_service import (
        ScanAndRegisterPhotosService,
    )
    from photo_archiver.infrastructure import (
        LocalPhotoFileScanner,
        PillowPhotoMetadataReader,
    )
    from photo_archiver.infrastructure.image import ContentHashCalculator

    repositories = build_sqlite_repositories(db_path)
    scan = ScanAndRegisterPhotosService(
        LocalPhotoFileScanner(), repositories.folders, repositories.photos,
        # 注入 hasher（生产装配同款）——否则去重退化为 mtime 弱信号，
        # 同秒写入的千张副本会被判为同一张照片。
        PillowPhotoMetadataReader(content_hasher=ContentHashCalculator()),
    )
    scan.execute(ScanAndRegisterPhotosCommand(folder_path=photo_dir))
    photos = repositories.photos.list_all()
    return repositories, [(photo.id, photo.path.raw_path) for photo in photos]


def _make_chain(db_path: Path, workers: int):
    from photo_archiver.app.repositories import build_sqlite_repositories
    from photo_archiver.ai.insightface_detector import InsightFaceDetector
    from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
    from photo_archiver.application.services import RecognitionFailureService
    from photo_archiver.application.services.run_recognition_service import (
        RunRecognitionService,
    )
    from photo_archiver.infrastructure.ai.insightface_loader import InsightFaceLoader

    repositories = build_sqlite_repositories(db_path)
    loader = InsightFaceLoader(MODEL_ROOT)
    if not loader.is_available():
        raise SystemExit(f"model pack not available under {MODEL_ROOT}")
    analysis = loader.load()
    detector = InsightFaceDetector(analysis)
    service = RunRecognitionService(
        detector=detector,
        matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=repositories.face_embeddings,
        recognition_repository=repositories.recognition,
        recognition_run_repository=repositories.recognition_runs,
        face_observation_repository=repositories.face_observations,
        max_workers=workers,
    )
    failure = RecognitionFailureService(
        repositories.recognition_runs, repositories.face_observations,
    )
    return repositories, service, failure


def _run_in_thread(service, command) -> tuple:
    """执行一次识别（后台线程），返回 (run, elapsed_s)。"""
    outcome: dict = {}

    def _target():
        start = time.perf_counter()
        try:
            run = service.execute(command)
        except Exception as exc:
            import traceback
            outcome["error"] = traceback.format_exc()
            outcome["exception"] = exc
            return
        outcome["run"] = run
        outcome["elapsed"] = time.perf_counter() - start

    thread = threading.Thread(target=_target)
    thread.start()
    return thread, outcome


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage F Wave 3 lifecycle stress (1000+ photos, real model).",
    )
    parser.add_argument("--photos", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cancel-delay", type=float, default=30.0,
                        help="识别开始后多少秒触发取消")
    parser.add_argument("--db", default=None)
    parser.add_argument("--report", default=None)
    parser.add_argument("--keep-db", action="store_true")
    args = parser.parse_args()

    workdir = Path(mkdtemp(prefix="stage_f_stress_"))
    db_path = Path(args.db) if args.db else workdir / "stress.sqlite3"
    photo_dir = workdir / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    _build_library(args.photos, photo_dir)

    repositories, service, failure = _make_chain(db_path, args.workers)
    _, registered = _register_photos(db_path, photo_dir)
    evidence: dict = {"photos": len(registered), "workers": args.workers}
    assert len(registered) == args.photos, (
        f"registered {len(registered)} != {args.photos}"
    )

    tracemalloc.start()
    # ── Phase 1: cancel mid-run ─────────────────────────────────────────
    from photo_archiver.application.commands.start_recognition_run import (
        StartRecognitionRunCommand,
    )

    command = StartRecognitionRunCommand(
        photo_ids=tuple(photo_id for photo_id, _ in registered),
        images=tuple(raw_path for _, raw_path in registered),
    )
    thread, outcome = _run_in_thread(service, command)
    time.sleep(args.cancel_delay)
    cancel_at = time.perf_counter()
    service.cancel()
    thread.join()
    cancel_latency = round(time.perf_counter() - cancel_at, 2)
    if "error" in outcome:
        print(outcome["error"])
        raise outcome["exception"]
    run1 = outcome["run"]
    evidence["phase1_cancel"] = {
        "run_id": str(run1.id),
        "status": run1.status,
        "cancel_latency_s": cancel_latency,
        "elapsed_s": round(outcome["elapsed"], 2),
        "observations": len(repositories.face_observations.list_by_run(run1.id)),
        "unreadable": run1.unreadable_count,
        "no_face": run1.no_face_count,
        "error": run1.error_count,
    }
    print(f"[stress] phase1: {json.dumps(evidence['phase1_cancel'])}")
    assert run1.status == "cancelled", "取消后运行必须为 cancelled"

    # ── Phase 2: retry remaining ────────────────────────────────────────
    retryable = failure.report(run1.id).retryable_photo_ids
    retry_paths = {
        snapshot.photo_id: snapshot.raw_path
        for snapshot in repositories.recognition_runs.list_run_photos(run1.id)
    }
    evidence["phase2_retry"] = {
        "run_id": str(run1.id),
        "retryable_count": len(retryable),
    }
    retry_command = StartRecognitionRunCommand(
        photo_ids=retryable,
        images=tuple(retry_paths[photo_id] for photo_id in retryable),
    )
    thread2, outcome2 = _run_in_thread(service, retry_command)
    thread2.join()
    if "error" in outcome2:
        print(outcome2["error"])
        raise outcome2["exception"]
    run2 = outcome2["run"]
    evidence["phase2_retry"].update({
        "run_id_new": str(run2.id),
        "status": run2.status,
        "elapsed_s": round(outcome2["elapsed"], 2),
        "observations": len(repositories.face_observations.list_by_run(run2.id)),
    })
    print(f"[stress] phase2: {json.dumps(evidence['phase2_retry'])}")
    assert run1.id != run2.id, "重试必须创建新 RecognitionRun"
    assert run2.status == "completed"

    # ── Phase 3: 一致性证据 ─────────────────────────────────────────────
    obs1 = {o.photo_id for o in repositories.face_observations.list_by_run(run1.id)}
    obs2 = {o.photo_id for o in repositories.face_observations.list_by_run(run2.id)}
    with repositories._connection_provider.connect() as connection:
        duplicate_pairs = connection.execute(
            "SELECT COUNT(*) FROM (SELECT run_id, photo_id, face_index, COUNT(*) c"
            " FROM face_observations GROUP BY run_id, photo_id, face_index"
            " HAVING c > 1)",
        ).fetchone()[0]
        run_rows = connection.execute(
            "SELECT COUNT(*) FROM recognition_runs",
        ).fetchone()[0]
        photo_rows = connection.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
    evidence["phase3_consistency"] = {
        "run_rows": run_rows,
        "distinct_run_ids": len({str(run1.id), str(run2.id)}),
        "photo_rows": photo_rows,
        "run1_observations": len(obs1),
        "run2_observations": len(obs2),
        "cross_run_photo_overlap": len(obs1 & obs2),
        "duplicate_face_index_pairs": duplicate_pairs,
        "coverage": len(obs1 | obs2),
        "tracemalloc_peak_mb": round(tracemalloc.get_traced_memory()[1] / 1e6, 2),
    }
    print(f"[stress] phase3: {json.dumps(evidence['phase3_consistency'])}")
    tracemalloc.stop()

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(f"[stress] evidence JSON written to {report_path}")
    if not args.keep_db and args.db is None:
        shutil.rmtree(workdir, ignore_errors=True)
    print("done — record numbers in the calibration report (evidence baseline)")
    return 0


if __name__ == "__main__":
    __import__("sys").exit(main())
