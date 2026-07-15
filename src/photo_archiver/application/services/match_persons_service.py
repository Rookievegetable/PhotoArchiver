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
    Person,
    PersonRepository,
    PhotoRepository,
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
        person_repository: PersonRepository,
        photo_repository: PhotoRepository,
        recognition_repository: RecognitionRepository,
        match_threshold: float,
        progress_reporter: ProgressReporter | None = None,
    ) -> None:
        """Initialize the service with ports, repositories and the configured threshold.

        Args:
            detector: Face detection port (Step 9 InsightFace-backed).
            recognizer: Face embedding extraction port (Step 9 InsightFace-backed).
            matcher: Person matching port (Step 9 cosine-similarity-backed).
            person_repository: Known persons lookup for candidate embeddings.
            photo_repository: Photo lookup for batch resolution.
            recognition_repository: Persistence target for match results.
            match_threshold: Minimum cosine similarity for a successful match,
                in ``[0.0, 1.0]``.
            progress_reporter: Optional progress stream for Worker/UI feedback.
        """
        self._detector = detector
        self._recognizer = recognizer
        self._matcher = matcher
        self._person_repository = person_repository
        self._photo_repository = photo_repository
        self._recognition_repository = recognition_repository
        self._match_threshold = match_threshold
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

        Step 10 assumes each person has at most one canonical embedding stored
        on the person aggregate. When Step 10 wiring later adds a
        ``FaceEmbeddingRepository``, this method will switch to query it; for
        now candidates are built from persons that carry an embedding field
        (empty by default since Person does not yet hold embeddings).
        """
        persons: list[Person] = self._person_repository.list_all()
        candidates: dict[UUID, FaceEmbedding] = {}
        for person in persons:
            embedding = getattr(person, "face_embedding", None)
            if embedding is not None and person.id is not None:
                candidates[person.id] = embedding
        return candidates

    def _match_one(
        self,
        photo_id: UUID,
        image: Path,
        candidates: dict[UUID, FaceEmbedding],
    ) -> MatchResult:
        """Run detect → extract → match for one photo and persist the outcome."""
        boxes = self._detector.detect(image)
        if not boxes:
            logger.debug("No faces detected in photo {}", photo_id)
            return MatchResult(photo_id=photo_id, box=None)  # type: ignore[arg-type]

        box = boxes[0]  # Top-1: first detected face only per裁决 #5
        embedding = self._recognizer.extract(image, box)
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
        return MatchResult(photo_id=photo_id, box=box)  # type: ignore[arg-type]

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
