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
    ) -> None:
        """Initialize the service with ports and repositories.

        Args:
            detector: Face detection port (Step 9 InsightFace-backed).
            recognizer: Face embedding extraction port (Step 9 InsightFace-backed).
            matcher: Person matching port (Step 9 cosine-similarity-backed).
            face_embedding_repository: Known person embeddings lookup.
            recognition_repository: Persistence target for match results.
            progress_reporter: Optional progress stream for Worker/UI feedback.
        """
        self._detector = detector
        self._recognizer = recognizer
        self._matcher = matcher
        self._face_embedding_repository = face_embedding_repository
        self._recognition_repository = recognition_repository
        self._progress_reporter = progress_reporter

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
        """Run detect → extract → match for one photo and persist the outcome.

        ISSUE-001 fix: uses ``detect_with_embeddings`` so detection and embedding
        extraction happen in a single ``FaceAnalysis.get`` pass — the recognizer
        no longer re-detects the same image. Per裁决 #5 Top-1 strategy still
        picks the face with the highest detection confidence.
        """
        pairs = self._detector.detect_with_embeddings(image)
        if not pairs:
            logger.debug("No faces detected in photo {}", photo_id)
            return MatchResult(photo_id=photo_id, box=None)

        # Top-1 per裁决 #5: pick the face with the highest detection confidence.
        # InsightFace's detect order is observed to be descending by det_score,
        # but that is an implementation detail — max() locks the semantic.
        best_pair = max(pairs, key=lambda p: p.box.confidence or 0.0)
        embedding = best_pair.embedding
        match = self._matcher.match(embedding, candidates)

        person_id: UUID | None = None
        confidence = 0.0
        if match is not None:
            person_id, confidence = match

        result = RecognitionResult(
            photo_id=photo_id,
            confidence=confidence,
            person_id=person_id,
        )
        self._recognition_repository.add(result)
        logger.debug(
            "Photo {} matched person={} confidence={:.3f}",
            photo_id,
            person_id,
            confidence,
        )
        return MatchResult(photo_id=photo_id, box=best_pair.box)

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
