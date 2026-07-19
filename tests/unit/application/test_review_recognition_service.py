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

    def update_status(self, result_id, status) -> int:
        result = self._results.get(result_id)
        if result is None:
            return 0
        # Bypass approve()/reject() guards — service already transitioned the entity.
        result.status = status
        self.added.append(result)
        return 1


class _RecordingUoW:
    """Captures __enter__/__exit__ pairs so tests can assert UoW wrapping."""

    def __init__(self, raise_on_exit: bool = False) -> None:
        self.enter_calls: int = 0
        self.exit_calls: list[tuple] = []
        self.commit_calls: int = 0
        self.rollback_calls: int = 0
        self._raise_on_exit = raise_on_exit

    def __enter__(self) -> "_RecordingUoW":
        self.enter_calls += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.exit_calls.append((exc_type, exc_val, exc_tb))
        if exc_type is None:
            self.commit_calls += 1
        else:
            self.rollback_calls += 1
        if self._raise_on_exit:
            raise RuntimeError("simulated commit failure")


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


def test_approve_returns_none_when_update_affects_zero_rows() -> None:
    """approve must return None when update_status signals concurrent deletion (0 rows)."""

    class _VanishingRepo(_RecordingRecognitionRepository):
        def update_status(self, result_id, status) -> int:
            return 0  # simulate concurrent deletion

    result = _make_result()
    repo = _VanishingRepo({result.id: result})
    service = ReviewRecognitionService(repo)
    assert service.approve(result.id) is None


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


# ---- ISSUE-005 fix: UnitOfWork transaction boundary tests ----


def test_approve_without_uow_runs_bare() -> None:
    """approve without a UoW must still persist (back-compat with in-memory repos)."""
    result = _make_result()
    repo = _RecordingRecognitionRepository({result.id: result})
    service = ReviewRecognitionService(repo, unit_of_work=None)
    refreshed = service.approve(result.id)
    assert refreshed is not None
    assert refreshed.status is MatchStatus.APPROVED


def test_approve_with_uow_enters_then_commits_on_success() -> None:
    """approve with a UoW must __enter__ then __exit__ with no exception (commit path)."""
    result = _make_result()
    repo = _RecordingRecognitionRepository({result.id: result})
    uow = _RecordingUoW()
    service = ReviewRecognitionService(repo, unit_of_work=uow)
    refreshed = service.approve(result.id)
    assert refreshed is not None
    assert refreshed.status is MatchStatus.APPROVED
    assert uow.enter_calls == 1
    assert uow.commit_calls == 1
    assert uow.rollback_calls == 0


def test_approve_with_uow_rolls_back_when_update_raises() -> None:
    """approve must let the UoW roll back when update_status raises.

    This is the ISSUE-005 honesty gap closing: before the UoW wrap the in-memory
    flip was committed but the DB row was left pending. With the UoW the SQLite
    transaction rolls back so no partial state lands on disk.
    """

    class _RaisingRepo(_RecordingRecognitionRepository):
        def update_status(self, result_id, status) -> int:
            raise RuntimeError("simulated DB outage")

    result = _make_result()
    repo = _RaisingRepo({result.id: result})
    uow = _RecordingUoW()
    service = ReviewRecognitionService(repo, unit_of_work=uow)
    raised = False
    caught_exc: BaseException | None = None
    try:
        service.approve(result.id)
    except RuntimeError as exc:
        raised = True
        caught_exc = exc
    assert raised
    # m-7: assert UoW __exit__ received the propagated exception so future
    # silent-swallow changes cannot quietly flip the rollback path to commit.
    assert uow.exit_calls
    assert uow.exit_calls[0][0] is RuntimeError
    assert isinstance(caught_exc, RuntimeError)
    assert uow.enter_calls == 1
    assert uow.rollback_calls == 1
    assert uow.commit_calls == 0


def test_bulk_approve_with_uow_enters_once_per_item() -> None:
    """bulk_approve must enter/exit the UoW once per transitioned item.

    Each item gets its own with-block so a mid-batch failure rolls back only
    that item's transition, not the whole batch. This mirrors the per-item
    semantics ArchiveExecutor uses for ArchiveRecord persistence.
    """
    pending1 = _make_result()
    pending2 = _make_result()
    repo = _RecordingRecognitionRepository({
        pending1.id: pending1,
        pending2.id: pending2,
    })
    uow = _RecordingUoW()
    service = ReviewRecognitionService(repo, unit_of_work=uow)
    transitioned = service.bulk_approve((pending1.id, pending2.id))
    assert transitioned == 2
    assert uow.enter_calls == 2
    assert uow.commit_calls == 2
    assert uow.rollback_calls == 0
