"""Traceable, rerunnable face recognition service."""

from collections.abc import Iterator
from concurrent.futures import CancelledError, ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from threading import Event

from loguru import logger

from photo_archiver.application.commands.start_recognition_run import StartRecognitionRunCommand
from photo_archiver.application.services.face_analysis_task import FaceAnalysisTask
from photo_archiver.application.use_cases import RunRecognitionUseCase
from photo_archiver.application.ports import PersonMatcher
from photo_archiver.domain import (
    FaceObservation, FaceObservationRepository, FaceEmbeddingRepository,
    RecognitionRepository, RecognitionResult, RecognitionRun,
    RecognitionRunRepository, RecognitionRunStats, RunPhotoSnapshot, classify_scope,
)

_OBSERVATION_FLUSH_SIZE = 50


class RunRecognitionService(RunRecognitionUseCase):
    """Run detection, observation persistence and legacy-result compatibility."""

    def __init__(self, detector, matcher: PersonMatcher,
                 face_embedding_repository: FaceEmbeddingRepository,
                 recognition_repository: RecognitionRepository,
                 recognition_run_repository: RecognitionRunRepository,
                 face_observation_repository: FaceObservationRepository, *,
                 photo_repository=None, max_workers: int = 1,
                 progress_reporter=None) -> None:
        self._detector = detector
        self._matcher = matcher
        self._face_embedding_repository = face_embedding_repository
        self._recognition_repository = recognition_repository
        self._run_repository = recognition_run_repository
        self._observation_repository = face_observation_repository
        # AUD-004 接缝修复：快照必须携带照片 captured_at，聚类 sort_key 的
        # 时间排序才能经真实链路生效（此前快照恒 None → 全簇退化为创建序）。
        self._photo_repository = photo_repository
        self._max_workers = max(1, max_workers)
        self._progress_reporter = progress_reporter
        self._cancel_event = Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def execute(self, command: StartRecognitionRunCommand) -> RecognitionRun:
        """Execute a new run; reruns always insert a new run and observations."""
        self._cancel_event.clear()
        run = RecognitionRun(parameters=deepcopy(dict(command.parameters)))
        run_id = run.id
        if run_id is None:
            raise RuntimeError("RecognitionRun did not generate an id")
        self._run_repository.add_run(run)
        self._run_repository.add_run_scopes(run_id, command.selected_ranges)
        captured_by_photo = {}
        if self._photo_repository is not None:
            for photo_id in command.photo_ids:
                photo = self._photo_repository.find_by_id(photo_id)
                if photo is not None:
                    captured_by_photo[photo_id] = photo.captured_at
        self._run_repository.add_run_photos(run_id, [
            RunPhotoSnapshot(run_id, photo_id, str(image),
                             captured_at=captured_by_photo.get(photo_id))
            for photo_id, image in zip(command.photo_ids, command.images)
        ])
        run.start()
        self._run_repository.update_run(run)
        stats = RecognitionRunStats()
        pending: list[FaceObservation] = []
        processed = 0
        total = len(command.photo_ids)
        try:
            candidates = self._face_embedding_repository.list_all()
            task = FaceAnalysisTask(self._detector)
            with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
                futures = [pool.submit(task, photo_id, image)
                           for photo_id, image in zip(command.photo_ids, command.images)]
                for photo_id, future in zip(command.photo_ids, futures):
                    if self._cancel_event.is_set():
                        future.cancel()
                    try:
                        result = future.result()
                    except CancelledError:
                        break
                    if self._cancel_event.is_set():
                        break
                    processed += 1
                    photo_stats, observations, compatibility = self._consume_result(
                        run_id, result, candidates, command.selected_ranges)
                    stats = _add_stats(stats, photo_stats)
                    pending.extend(observations)
                    if len(pending) >= _OBSERVATION_FLUSH_SIZE:
                        self._observation_repository.add_many(pending)
                        pending.clear()
                    if compatibility is not None:
                        self._recognition_repository.add(compatibility)
                    self._report(processed, total, f"Analyzed photo {photo_id}")
            if pending:
                self._observation_repository.add_many(pending)
            run.cancel(stats) if self._cancel_event.is_set() else run.complete(stats)
            self._run_repository.update_run(run)
            return run
        except Exception as exc:
            if pending:
                self._observation_repository.add_many(pending)
            if run.status == "running":
                run.fail(str(exc), stats)
                self._run_repository.update_run(run)
            raise

    def _consume_result(self, run_id, result, candidates, selected_ranges):
        """Convert one pure result into stats, observations and a legacy row."""
        if result.unreadable:
            return RecognitionRunStats(unreadable_count=1), [], None
        if result.error is not None:
            logger.error("Face analysis failed - isolated: {}", result.photo_id, result.error)
            return RecognitionRunStats(error_count=1), [], None
        count = len(result.faces)
        if count == 0:
            return RecognitionRunStats(no_face_count=1), [], None
        ordered = sorted(result.faces, key=lambda pair: (
            -(pair.box.confidence or 0.0), pair.box.x1, pair.box.y1, pair.box.x2, pair.box.y2))
        verdict = classify_scope(count, selected_ranges)
        in_scope = verdict == "in_selected_scope"
        observations = [FaceObservation(
            run_id=run_id, photo_id=result.photo_id, face_index=index,
            photo_face_count=count, det_score=pair.box.confidence or 0.0,
            box=pair.box, embedding=pair.embedding, scope_verdict=verdict,
            quality_score=pair.box.confidence,
        ) for index, pair in enumerate(ordered)]
        compatibility = None
        if in_scope and not self._recognition_repository.list_by_photo(result.photo_id):
            match = self._matcher.match(ordered[0].embedding, candidates)
            person_id, confidence = match if match is not None else (None, 0.0)
            compatibility = RecognitionResult(
                photo_id=result.photo_id, person_id=person_id, confidence=confidence)
        return RecognitionRunStats(
            face_count=count, in_scope_photo_count=int(in_scope),
            out_of_scope_photo_count=int(not in_scope),
        ), observations, compatibility

    def _report(self, current: int, total: int, message: str) -> None:
        if self._progress_reporter is not None:
            self._progress_reporter.report(current, total, message)

    @contextmanager
    def bind_progress_reporter(self, reporter) -> Iterator[None]:
        previous = self._progress_reporter
        self._progress_reporter = reporter
        try:
            yield
        finally:
            self._progress_reporter = previous


def _add_stats(left: RecognitionRunStats, right: RecognitionRunStats) -> RecognitionRunStats:
    return RecognitionRunStats(
        face_count=left.face_count + right.face_count,
        unreadable_count=left.unreadable_count + right.unreadable_count,
        no_face_count=left.no_face_count + right.no_face_count,
        error_count=left.error_count + right.error_count,
        in_scope_photo_count=left.in_scope_photo_count + right.in_scope_photo_count,
        out_of_scope_photo_count=left.out_of_scope_photo_count + right.out_of_scope_photo_count,
    )
