"""Service implementation for detecting, extracting and matching faces.

Step 10 implements the complete recognition pipeline as an Application-layer
orchestration: for each photo, detect faces → extract embeddings → match
against known person embeddings using a 1:N Top-1 strategy → persist
:class:`RecognitionResult` aggregates in the repository. Worker/UI wiring
is deferred to Step 12 per裁决 #1.

Matching strategy is fixed per裁决 #5: 1:N Top-1. The matcher returns the
single best ``(person_id, confidence)`` pair above ``match_threshold``, or
``None`` (Unknown). Top-K, multi-candidate manual selection and reclustering
strategies are explicitly out of scope for Step 10.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from loguru import logger

from photo_archiver.application.commands import MatchPersonsCommand
from photo_archiver.application.dtos import MatchResult
from photo_archiver.application.ports import (
    FaceDetector,
    FaceRecognizer,
    PersonMatcher,
    ProgressReporter,
)
from photo_archiver.application.use_cases import MatchPersonsUseCase
from photo_archiver.domain import (
    FaceEmbedding,
    FaceEmbeddingRepository,
    RecognitionRepository,
    RecognitionResult,
)

# Report progress at most every N items to avoid flooding the event stream.
_PROGRESS_REPORT_INTERVAL = 10


class MatchPersonsService(MatchPersonsUseCase):
    """Orchestrate the face matching pipeline for a batch of photos."""

    def __init__(
        self,
        detector: FaceDetector,
        recognizer: FaceRecognizer,
        matcher: PersonMatcher,
        face_embedding_repository: FaceEmbeddingRepository,
        recognition_repository: RecognitionRepository,
        progress_reporter: ProgressReporter | None = None,
        max_workers: int = 1,
    ) -> None:
        """Initialize the service with ports and repositories.

        Args:
            detector: Face detection port (Step 9 InsightFace-backed). Issue-001
                optimized pipeline uses ``detect_with_embeddings`` so detection
                and embedding extraction happen in a single ``FaceAnalysis.get`` pass.
            recognizer: Face embedding extraction port (Step 9 InsightFace-backed).
                Retained for protocol completeness / future per-face extract path;
                Issue-001's ``detect_with_embeddings`` path makes ``_match_one`` no
                longer call ``recognizer`` directly, but the port is still wired so
                (a) the Application bootstrap keeps a single recognition-adapter
                assembly point, and (b) a future per-face or re-extract use case
                can use it without re-breaking the constructor signature. Callers
                MUST NOT drop this parameter — ``MatchPersonsService`` is constructed
                by the infrastructure bootstrap (Step 12 Worker) and by tests, all
                of which inject a recognizer today.
            matcher: Person matching port (Step 9 cosine-similarity-backed).
            face_embedding_repository: Known person embeddings lookup.
            recognition_repository: Persistence target for match results.
            progress_reporter: Optional progress stream for Worker/UI feedback.
            max_workers: Thread-pool width for the detect→match stage (phase6
                裁决 A-2). ``1`` (default) keeps the legacy sequential path
                byte-for-byte; ``>1`` fans the CPU-bound
                ``detect_with_embeddings`` work out to a
                :class:`ThreadPoolExecutor` — onnxruntime inference releases
                the GIL, so worker threads overlap model compute. Values
                below 1 are clamped to 1.
        """
        self._detector = detector
        self._recognizer = recognizer  # noqa: ARG002  retained for protocol completeness / future per-face extract path (Issue-001 made _match_one use detect_with_embeddings)
        self._matcher = matcher
        self._face_embedding_repository = face_embedding_repository
        self._recognition_repository = recognition_repository
        self._progress_reporter = progress_reporter
        self._max_workers = max(1, max_workers)

    def execute(self, command: MatchPersonsCommand) -> tuple[MatchResult, ...]:
        """Run the matching pipeline for each photo in the command.

        Args:
            command: Carries ``(photo_ids, images)`` tuples of equal length.

        Returns:
            One :class:`MatchResult` per photo, in command order. Photos with
            no detected face yield a match whose ``best`` is ``None``.
        """
        if len(command.photo_ids) != len(command.images):
            raise ValueError("MatchPersonsCommand photo_ids and images length mismatch")

        candidates = self._build_candidate_embeddings()
        # Memory note: candidates dict驻留整批次周期。Step 12 接入 Worker 时若批量大
        # (数百张), list_all() 返回每 person 512 float 的 dict 可能占数十 MB——
        # Step 12 应改为分批 lazy 加载或 snapshot 时用, 本轮 Application-only 范围可接受.
        results: list[MatchResult] = []
        total = len(command.photo_ids)

        if self._max_workers > 1 and total > 1:
            return self._execute_parallel(command, candidates, total)

        for index, (photo_id, image) in enumerate(
            zip(command.photo_ids, command.images), start=1
        ):
            result = self._match_one(photo_id, image, candidates)
            results.append(result)
            self._report(index, total, f"Matched photo {photo_id}")

        logger.info(
            "MatchPersonsService processed {} photo(s) against {} candidate(s)",
            total,
            len(candidates),
        )
        return tuple(results)

    def _build_candidate_embeddings(self) -> dict[UUID, FaceEmbedding]:
        """Return ``person_id → embedding`` for every known person.

        Candidates are queried from :class:`FaceEmbeddingRepository`, which
        replaces the earlier broken ``getattr(person, "face_embedding")``
        path that always returned empty because Person has no such field.
        """
        return self._face_embedding_repository.list_all()

    def _match_one(
        self,
        photo_id: UUID,
        image: Path,
        candidates: dict[UUID, FaceEmbedding],
    ) -> MatchResult:
        """Run detect → extract → match for one photo and persist the outcome."""
        match_result, recognition = self._analyze_one(photo_id, image, candidates)
        if recognition is not None:
            self._recognition_repository.add(recognition)
        return match_result

    def _analyze_one(
        self,
        photo_id: UUID,
        image: Path,
        candidates: dict[UUID, FaceEmbedding],
    ) -> tuple[MatchResult, RecognitionResult | None]:
        """Run detect → match for one photo WITHOUT persisting (phase6 A-2).

        Deliberately free of repository writes so it is safe to run on worker
        threads: ``candidates`` is a read-only snapshot shared by the whole
        batch and the InsightFace analysis session is thread-safe for
        inference. Returns ``(match_result, recognition_result)`` where
        ``recognition_result`` is ``None`` when no face was detected —
        mirroring the sequential path, which persists nothing in that case.

        ISSUE-001 fix retained: ``detect_with_embeddings`` does detection and
        embedding extraction in a single ``FaceAnalysis.get`` pass — the
        recognizer no longer re-detects the same image. Per裁决 #5 Top-1
        strategy still picks the face with the highest detection confidence;
        ``max()`` locks the semantic regardless of detect order.
        """
        try:
            pairs = self._detector.detect_with_embeddings(image)
            if not pairs:
                logger.debug("No faces detected in photo {}", photo_id)
                return MatchResult(photo_id=photo_id, box=None), None

            best_pair = max(pairs, key=lambda p: p.box.confidence or 0.0)
            embedding = best_pair.embedding
            match = self._matcher.match(embedding, candidates)

            person_id: UUID | None = None
            confidence = 0.0
            if match is not None:
                person_id, confidence = match

            logger.debug(
                "Photo {} matched person={} confidence={:.3f}",
                photo_id,
                person_id,
                confidence,
            )
            recognition = RecognitionResult(
                photo_id=photo_id,
                confidence=confidence,
                person_id=person_id,
            )
            return MatchResult(photo_id=photo_id, box=best_pair.box), recognition
        except Exception:
            # §4.4 失败隔离——单张分析异常（模型推理/图像解码等）不中断整批：
            # 该照片降级为「无脸」结果（box=None、无识别记录，审批 UI 中保持
            # pending），批次其余照片照常完成。契约：本方法 never raises。
            logger.exception("Face analysis failed for photo {} — isolated", photo_id)
            return MatchResult(photo_id=photo_id, box=None), None

    def _execute_parallel(
        self,
        command: MatchPersonsCommand,
        candidates: dict[UUID, FaceEmbedding],
        total: int,
    ) -> tuple[MatchResult, ...]:
        """Fan the per-photo detect→match stage out to a thread pool (A-2).

        Order contract (A-4): results are returned in command order regardless
        of completion order — futures are consumed in submission order.
        Progress contract (A-4): the sequential reporting cadence (first /
        every ``_PROGRESS_REPORT_INTERVAL`` / last, same message format) is
        emitted from the consuming loop on the calling thread, so the reporter
        never sees concurrent calls. Persistence (A-3): recognition aggregates
        are collected and flushed with ONE ``add_many`` push-down instead of
        per-photo ``add`` calls.
        """
        logger.info(
            "MatchPersonsService using {} worker thread(s) for {} photo(s)",
            self._max_workers,
            total,
        )
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = [
                pool.submit(self._analyze_one, photo_id, image, candidates)
                for photo_id, image in zip(command.photo_ids, command.images)
            ]
            results: list[MatchResult] = []
            recognitions: list[RecognitionResult] = []
            for index, future in enumerate(futures, start=1):
                match_result, recognition = future.result()
                results.append(match_result)
                if recognition is not None:
                    recognitions.append(recognition)
                photo_id = command.photo_ids[index - 1]
                self._report(index, total, f"Matched photo {photo_id}")

        self._recognition_repository.add_many(recognitions)
        logger.info(
            "MatchPersonsService processed {} photo(s) against {} candidate(s)",
            total,
            len(candidates),
        )
        return tuple(results)

    def _report(self, current: int, total: int, message: str) -> None:
        """Forward progress to the reporter when one is bound.

        Always reports the first and last items so small batches (total below
        the interval) still surface visible progress to the UI; intermediate
        items report every ``_PROGRESS_REPORT_INTERVAL`` steps to avoid flooding.
        """
        if self._progress_reporter is None:
            return
        is_boundary = current == 1 or current == total
        is_interval = current % _PROGRESS_REPORT_INTERVAL == 0
        if not (is_boundary or is_interval):
            return
        self._progress_reporter.report(current, total, message)

    @contextmanager
    def bind_progress_reporter(self, reporter: ProgressReporter) -> Iterator[None]:
        """Temporarily bind a progress reporter for the duration of a use case.

        Worker tasks use this to stream per-photo progress through their own
        ``report`` adapter without permanently mutating the service configuration.
        The previous reporter (typically ``None``) is restored on exit.
        """
        previous = self._progress_reporter
        self._progress_reporter = reporter
        try:
            yield None
        finally:
            self._progress_reporter = previous
