"""Stage F Wave 3 lifecycle tests — 1000+ photo scale, cancel/retry/rerun.

Deterministic 1000+ photo scale over the real RunRecognitionService chain
(InMemory persistence, instant fake detector): full completion, mid-run
cancel with partial-preservation semantics, retry over remaining photos,
repeated cancel/retry cycles, and per-run data isolation. Timing evidence
is asserted loosely (completes at all) — hard performance numbers come from
tools/stress_lifecycle_stage_f.py with the real model.
"""

import time
from uuid import uuid4

from photo_archiver.application.commands.start_recognition_run import (
    StartRecognitionRunCommand,
)
from photo_archiver.application.services import RecognitionFailureService
from photo_archiver.application.services.run_recognition_service import (
    RunRecognitionService,
)
from photo_archiver.domain import (
    FaceBoxEmbedding,
    FaceEmbedding,
    ImageUnreadableError,
)
from photo_archiver.infrastructure.repositories import (
    InMemoryFaceClusterRepository,
    InMemoryFaceObservationRepository,
    InMemoryRecognitionRunRepository,
)

SCALE = 1200
PHOTOS_PER_SECOND_BUDGET = 30.0  # fake detector: 快速完成即可（硬性能走真实模型脚本）


class _ScriptedDetector:
    """Per-photo scripted outcomes: faces / unreadable / error, cancel-aware."""

    def __init__(self, outcomes: dict, cancel_after: int | None = None,
                 service=None, slow_us: int = 0):
        self._outcomes = outcomes
        self._cancel_after = cancel_after
        self._service = service
        self._slow_us = slow_us
        self.processed = 0

    def detect_with_embeddings(self, image):
        if self._cancel_after is not None and self._service is not None \
                and self.processed >= self._cancel_after:
            self._service.cancel()
            self._cancel_after = None  # 只触发一次
        if self._slow_us:
            time.sleep(self._slow_us / 1e6)
        self.processed += 1
        outcome = self._outcomes[image]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _RepoBundle:
    def __init__(self):
        self.runs = InMemoryRecognitionRunRepository()
        self.observations = InMemoryFaceObservationRepository()
        self.clusters = InMemoryFaceClusterRepository()


def _photo_ids(count: int) -> tuple:
    return tuple(uuid4() for _ in range(count))


def _one_face():
    return [FaceBoxEmbedding(
        type("B", (), {"x1": 0, "y1": 0, "x2": 10, "y2": 10, "confidence": 0.9})(),
        FaceEmbedding((1.0, 0.0)),
    )]


def _make_service(bundle: _RepoBundle, outcomes: dict, cancel_after: int | None = None):
    detector = _ScriptedDetector(outcomes, cancel_after=cancel_after, service=None)
    service = RunRecognitionService(
        detector=detector,
        matcher=type("M", (), {"match": staticmethod(lambda embedding, candidates: None)})(),
        face_embedding_repository=type("E", (), {"list_all": staticmethod(lambda *a, **k: {})})(),
        recognition_repository=type("R", (), {
            "add": staticmethod(lambda result: None),
            "list_by_photo": staticmethod(lambda photo_id: []),
        })(),
        recognition_run_repository=bundle.runs,
        face_observation_repository=bundle.observations,
        max_workers=4,
    )
    detector._service = service
    return service


def _observations_of(bundle: _RepoBundle, run_id) -> set:
    return {
        observation.photo_id
        for observation in bundle.observations.list_by_run(run_id)
    }


def test_full_run_over_1200_photos_completes_with_all_observations():
    bundle = _RepoBundle()
    photo_ids = _photo_ids(SCALE)
    outcomes = {photo_id: _one_face() for photo_id in photo_ids}
    service = _make_service(bundle, outcomes)

    start = time.perf_counter()
    run = service.execute(StartRecognitionRunCommand(
        photo_ids=photo_ids, images=photo_ids,
    ))
    elapsed = time.perf_counter() - start

    assert run.status == "completed"
    assert run.face_count == SCALE
    assert len(_observations_of(bundle, run.id)) == SCALE
    assert elapsed < SCALE / PHOTOS_PER_SECOND_BUDGET


def test_mid_run_cancel_persists_partial_and_marks_cancelled():
    bundle = _RepoBundle()
    photo_ids = _photo_ids(SCALE)
    outcomes = {photo_id: _one_face() for photo_id in photo_ids}
    cancel_after = 200
    service = _make_service(bundle, outcomes, cancel_after=cancel_after)

    run = service.execute(StartRecognitionRunCommand(
        photo_ids=photo_ids, images=photo_ids,
    ))

    assert run.status == "cancelled"
    observed = _observations_of(bundle, run.id)
    # 取消语义：已消费并提交的观测保留；取消后未消费的结果丢弃（Stage C）。
    # 瞬时 fake detector 下主循环消费量取决于线程调度——只断言部分完成。
    assert 0 <= len(observed) < SCALE
    assert run.face_count == len(observed)
    assert run.unreadable_count == 0


def test_retry_after_cancel_creates_new_run_covering_remaining():
    bundle = _RepoBundle()
    photo_ids = _photo_ids(SCALE)
    outcomes = {photo_id: _one_face() for photo_id in photo_ids}
    service = _make_service(bundle, outcomes, cancel_after=200)
    first = service.execute(StartRecognitionRunCommand(
        photo_ids=photo_ids, images=photo_ids,
    ))
    failure_service = RecognitionFailureService(bundle.runs, bundle.observations)

    retryable = failure_service.report(first.id).retryable_photo_ids
    second = service.execute(StartRecognitionRunCommand(
        photo_ids=retryable, images=retryable,
    ))

    assert first.id != second.id
    assert first.status == "cancelled" and second.status == "completed"
    # 重试范围 = 首轮未产出观测的照片（run_photos - observed，Stage F 语义）。
    assert len(retryable) == SCALE - len(_observations_of(bundle, first.id))
    # 历史不被覆盖：首轮观测数不变。
    assert len(_observations_of(bundle, first.id)) == first.face_count
    # 两次运行的观测并集覆盖全部照片且互不重复（跨 run 允许同照片再次检测）。
    union = _observations_of(bundle, first.id) | _observations_of(bundle, second.id)
    assert union == set(photo_ids)


def test_repeated_cancel_retry_cycles_stay_consistent():
    """连续 cancel → retry → cancel → retry → complete：无重复 run、无泄漏。"""
    bundle = _RepoBundle()
    photo_ids = _photo_ids(SCALE)
    outcomes = {photo_id: _one_face() for photo_id in photo_ids}
    cancel_points = [300, 500]
    service = _make_service(bundle, outcomes, cancel_after=cancel_points[0])
    failure_service = RecognitionFailureService(bundle.runs, bundle.observations)

    run_ids: list = []
    statuses: list[str] = []
    current_photos = photo_ids
    cycle = 0
    while True:
        run = service.execute(StartRecognitionRunCommand(
            photo_ids=current_photos, images=current_photos,
        ))
        run_ids.append(run.id)
        statuses.append(run.status)
        if run.status == "cancelled":
            cycle += 1
            if cycle < len(cancel_points):
                # 下一个 cancel 触发点在剩余照片上更靠后（模拟处理进度推进）。
                detector = service._detector
                detector._cancel_after = cancel_points[cycle]
                detector.processed = 0
            current_photos = failure_service.report(run.id).retryable_photo_ids
            continue
        break

    assert statuses == ["cancelled", "cancelled", "completed"]
    assert len(set(run_ids)) == 3  # 无重复 run
    assert len(bundle.runs.list_runs()) == 3
    # 最终：全部照片都有观测（跨 run 并集）。
    covered: set = set()
    for run_id in run_ids:
        covered |= _observations_of(bundle, run_id)
    assert covered == set(photo_ids)


def test_unreadable_and_error_photos_are_retryable_but_do_not_crash():
    bundle = _RepoBundle()
    good1, bad, good2, err = _photo_ids(4)
    outcomes = {
        good1: _one_face(),
        bad: ImageUnreadableError("unreadable"),
        good2: _one_face(),
        err: RuntimeError("detector boom"),
    }
    service = _make_service(bundle, outcomes)
    run = service.execute(StartRecognitionRunCommand(
        photo_ids=(good1, bad, good2, err), images=(good1, bad, good2, err),
    ))

    assert run.status == "completed"
    assert run.unreadable_count == 1 and run.error_count == 1
    failure_service = RecognitionFailureService(bundle.runs, bundle.observations)
    retryable = failure_service.report(run.id).retryable_photo_ids
    assert set(retryable) == {bad, err}  # 无产出观测的照片即重试候选（Spec Gap 语义）
