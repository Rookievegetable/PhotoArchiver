"""Tests for ReviewController — list_pending + approve/reject forwarding."""

import pytest

pytest.importorskip("PySide6")

from uuid import uuid4

from photo_archiver.domain import RecognitionResult
from photo_archiver.presentation.controllers import ReviewController


class _FakeRecognitionRepo:
    """In-memory recognition repo stub for read-side list_pending."""

    def __init__(self, pending: list[RecognitionResult]) -> None:
        self._pending = pending

    def list_pending(self) -> list[RecognitionResult]:
        return list(self._pending)


class _FakeReviewUseCase:
    """Captures approve/reject calls for assertion."""

    def __init__(self) -> None:
        self.approve_calls: list = []
        self.reject_calls: list = []
        self.bulk_approve_calls: list = []
        self.bulk_reject_calls: list = []

    def approve(self, result_id):
        self.approve_calls.append(result_id)
        return None

    def reject(self, result_id):
        self.reject_calls.append(result_id)
        return None

    def bulk_approve(self, result_ids):
        self.bulk_approve_calls.append(result_ids)
        return len(result_ids)

    def bulk_reject(self, result_ids):
        self.bulk_reject_calls.append(result_ids)
        return len(result_ids)


def test_list_pending_delegates_to_recognition_repository() -> None:
    """list_pending() reads from the recognition repository, not the use case."""
    pending = [RecognitionResult(photo_id=uuid4(), confidence=0.9)]  # type: ignore[arg-type]
    controller = ReviewController(
        _FakeReviewUseCase(),  # type: ignore[arg-type]
        _FakeRecognitionRepo(pending),  # type: ignore[arg-type]
    )
    assert controller.list_pending() == pending


def test_approve_forwards_to_use_case() -> None:
    """approve() forwards the result_id to the use case."""
    use_case = _FakeReviewUseCase()
    controller = ReviewController(
        use_case,  # type: ignore[arg-type]
        _FakeRecognitionRepo([]),  # type: ignore[arg-type]
    )
    pid = uuid4()
    controller.approve(pid)
    assert use_case.approve_calls == [pid]


def test_reject_forwards_to_use_case() -> None:
    """reject() forwards the result_id to the use case."""
    use_case = _FakeReviewUseCase()
    controller = ReviewController(
        use_case,  # type: ignore[arg-type]
        _FakeRecognitionRepo([]),  # type: ignore[arg-type]
    )
    pid = uuid4()
    controller.reject(pid)
    assert use_case.reject_calls == [pid]


def test_bulk_approve_returns_count_transitioned() -> None:
    """bulk_approve() returns the count forwarded from the use case."""
    use_case = _FakeReviewUseCase()
    controller = ReviewController(
        use_case,  # type: ignore[arg-type]
        _FakeRecognitionRepo([]),  # type: ignore[arg-type]
    )
    ids = (uuid4(), uuid4(), uuid4())
    assert controller.bulk_approve(ids) == 3
    assert use_case.bulk_approve_calls == [ids]
