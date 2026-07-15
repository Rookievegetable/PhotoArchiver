"""Unit tests for the ReviewRecognitionService Application-layer orchestration."""

from uuid import uuid4

from photo_archiver.application.services import ReviewRecognitionService
from photo_archiver.domain import (
    MatchStatus,
    RecognitionRepository,
    RecognitionResult,
)


class _RecordingRecognitionRepository(RecognitionRepository):
    """In-memory RecognitionRepository for review service tests."""

    def __init__(self, results: dict) -> None:
        self._results = results  # id -> RecognitionResult
        self.added: list = []

    def add(self, result: RecognitionResult) -> None:
        self._results[result.id] = result
        self.added.append(result)

    def find_by_id(self, result_id):
        return self._results.get(result_id)

    def list_by_photo(self, photo_id) -> list:
        raise NotImplementedError

    def list_pending(self) -> list:
        raise NotImplementedError

    def update_status(self, result_id, status) -> None:
        raise NotImplementedError


def _make_result(photo_id=None, status: MatchStatus = MatchStatus.PENDING) -> RecognitionResult:
    """Build a RecognitionResult in a known status."""
    import uuid

    result = RecognitionResult(photo_id=photo_id or uuid.uuid4(), confidence=0.8)
    if status is MatchStatus.APPROVED:
        result.approve()
    elif status is MatchStatus.REJECTED:
        result.reject()
    return result


def test_approve_transitions_pending_to_approved() -> None:
    """approve must flip a pending result to APPROVED and persist."""
    result = _make_result()
    repo = _RecordingRecognitionRepository({result.id: result})
    service = ReviewRecognitionService(repo)
    refreshed = service.approve(result.id)
    assert refreshed is not None
    assert refreshed.status is MatchStatus.APPROVED
    assert repo.added == [refreshed]


def test_reject_transitions_pending_to_rejected() -> None:
    """reject must flip a pending result to REJECTED and persist."""
    result = _make_result()
    repo = _RecordingRecognitionRepository({result.id: result})
    service = ReviewRecognitionService(repo)
    refreshed = service.reject(result.id)
    assert refreshed is not None
    assert refreshed.status is MatchStatus.REJECTED


def test_approve_returns_none_for_missing_result() -> None:
    """approve must return None when the result id is unknown."""
    repo = _RecordingRecognitionRepository({})
    service = ReviewRecognitionService(repo)
    assert service.approve(uuid4()) is None


def test_approve_returns_none_for_finalized_result() -> None:
    """approve must skip an already-approved result without re-transitioning."""
    result = _make_result(status=MatchStatus.APPROVED)
    repo = _RecordingRecognitionRepository({result.id: result})
    service = ReviewRecognitionService(repo)
    assert service.approve(result.id) is None
    assert repo.added == []


def test_reject_returns_none_for_finalized_result() -> None:
    """reject must skip an already-rejected result without re-transitioning."""
    result = _make_result(status=MatchStatus.REJECTED)
    repo = _RecordingRecognitionRepository({result.id: result})
    service = ReviewRecognitionService(repo)
    assert service.reject(result.id) is None


def test_bulk_approve_counts_transitioned() -> None:
    """bulk_approve must return how many results actually transitioned."""
    pending1 = _make_result()
    pending2 = _make_result()
    already_approved = _make_result(status=MatchStatus.APPROVED)
    repo = _RecordingRecognitionRepository({
        pending1.id: pending1,
        pending2.id: pending2,
        already_approved.id: already_approved,
    })
    service = ReviewRecognitionService(repo)
    transitioned = service.bulk_approve((pending1.id, pending2.id, already_approved.id))
    assert transitioned == 2
    assert repo.added == [pending1, pending2]
    assert all(r.status is MatchStatus.APPROVED for r in repo.added)


def test_bulk_reject_counts_transitioned() -> None:
    """bulk_reject must return how many results actually transitioned."""
    pending1 = _make_result()
    pending2 = _make_result()
    repo = _RecordingRecognitionRepository({
        pending1.id: pending1,
        pending2.id: pending2,
    })
    service = ReviewRecognitionService(repo)
    transitioned = service.bulk_reject((pending1.id, pending2.id, uuid4()))
    assert transitioned == 2
    assert all(r.status is MatchStatus.REJECTED for r in repo.added)


def test_bulk_approve_empty_batch_returns_zero() -> None:
    """An empty bulk batch must transition zero results."""
    repo = _RecordingRecognitionRepository({})
    service = ReviewRecognitionService(repo)
    assert service.bulk_approve(()) == 0
    assert service.bulk_reject(()) == 0
