"""Recognition result repository interface."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from photo_archiver.domain.entities import MatchStatus, RecognitionResult


@dataclass(frozen=True, slots=True)
class WorkspaceCounts:
    """Bounded read projection; counts do not materialize library entities."""

    has_persons: bool
    has_photos: bool
    pending_match_count: int
    pending_review_count: int
    archivable_count: int


class RecognitionRepository(Protocol):
    """Define persistence operations for recognition result aggregates."""

    def read_workspace_counts(self) -> WorkspaceCounts:
        """Read library readiness in one aggregate query, without entity enumeration.

        Pending match counts photos with no recognition rows. Pending review
        counts pending result rows (including unknown persons). Archivable counts
        distinct absolute-path photos with an approved result for an existing
        person and no successful archive record (archived/skipped/renamed/
        overwritten), matching ArchivePlanner. Failed, planned and dry-run
        archive records do not block retries. Presence checks include all rows.
        """

    def add(self, result: RecognitionResult) -> None:
        """Add a recognition result or replace the existing aggregate by id."""

    def add_many(self, results: Sequence[RecognitionResult]) -> None:
        """Add a batch of recognition results in one call.

        Default implementation loops ``add`` so minimal implementations keep
        working unchanged; SQL-backed repositories SHOULD override this with a
        single-transaction push-down (see ``SQLiteRecognitionRepository.add_many``).
        """
        for result in results:
            self.add(result)

    def find_by_id(self, result_id: UUID) -> RecognitionResult | None:
        """Find a recognition result by its domain identifier."""

    def list_by_photo(self, photo_id: UUID) -> list[RecognitionResult]:
        """Return all recognition results for the given photo."""

    def list_first_by_photo_ids(
        self, photo_ids: Sequence[UUID]
    ) -> dict[UUID, RecognitionResult]:
        """Return the earliest recognition result per photo, in one round trip.

        Mirrors the "first element of ``list_by_photo``" semantics (ordered by
        ``created_at`` then ``id``) for every supplied photo id, so callers
        pairing photos with review status avoid N+1 per-photo lookups.
        Photo ids without any recognition result are absent from the mapping.
        """

    def list_by_photo_ids(
        self, photo_ids: Sequence[UUID],
    ) -> list[RecognitionResult]:
        """Return ALL recognition results for the supplied photos, in one batch.

        FILTERED-export query (FEATURE-004 contract
        ``docs/health-check/PHASE_7_SCOPE_CONTRACT_REVISION.md`` §3/F4): every
        result — any ``MatchStatus`` — whose ``photo_id`` is in ``photo_ids``.
        Unlike ``list_first_by_photo_ids`` (earliest per photo) and
        ``list_by_photo`` (single photo). Results are ordered by ``created_at``
        then ``id``; ``created_at`` is always populated by
        ``RecognitionResult.__post_init__`` so the ordering key is total.

        Default implementation loops ``list_by_photo`` (deduplicating inputs —
        duplicate photo ids must not duplicate rows, matching IN-clause
        semantics) and re-sorts globally, so minimal implementations (e.g.
        test fakes) keep working unchanged — the ``add_many`` default-
        implementation precedent. SQL-backed repositories SHOULD override with
        a single-trip IN-clause push-down (see
        ``SQLiteRecognitionRepository.list_by_photo_ids``).
        """
        collected: list[RecognitionResult] = []
        seen_photo_ids: set[UUID] = set()
        for photo_id in photo_ids:
            if photo_id in seen_photo_ids:
                continue
            seen_photo_ids.add(photo_id)
            collected.extend(self.list_by_photo(photo_id))
        collected.sort(
            key=lambda result: (
                result.created_at if result.created_at is not None else datetime.min,
                result.id,
            ),
        )
        return collected

    def list_pending(self) -> list[RecognitionResult]:
        """Return all recognition results awaiting user review."""

    def list_approved_by_person(self, person_id: UUID) -> list[RecognitionResult]:
        """Return all APPROVED recognition results for the given person.

        Used by Step 11 ArchivePlanner to gather a person's approved photos
        for归档组织。Results are ordered by ``created_at`` then ``id`` so
        the planner produces a stable archive ordering under re-invocation.
        """

    def remove_results_for_person_photos(
        self, person_id: UUID, photo_ids: Sequence[UUID],
    ) -> int:
        """Stage E（E-SG-6）：回收 (person, photo) 的 APPROVED 兼容归属.

        改派/解除映射时同步兼容层投影：仅删除 status=APPROVED 且
        person_id 匹配的行——PENDING/REJECTED 行（review 流程数据）不动。
        身份决策历史由 ``ClusterPersonAssignment`` 行承载（主事实原则），
        本方法只维护兼容层与当前指派一致。

        Returns:
            删除的行数。
        """

    def update_status(
        self,
        result_id: UUID,
        status: MatchStatus,
        person_id: UUID | None = None,
    ) -> int:
        """Transition a recognition result's review status.

        ``person_id``（Stage 4 D-1）：人工审核批准时**同时**写入身份归属。
        新识别链路的兼容行 ``person_id`` 恒为 NULL（``person_embeddings`` 无
        生产者），若只改 ``status``，批准后仍是 ``person_id IS NULL`` 的
        APPROVED 行——而归档只消费 ``person_id = ? AND status='approved'``，
        该行永远进不了归档计划，"人工批准的最终结果"与归档链路不一致。
        传 ``None`` 表示不触碰该列（拒绝路径不需要身份）。

        Returns:
            The number of rows affected (1 on hit, 0 when the result id is
            missing). Callers SHOULD treat 0 as a concurrent-deletion signal
            rather than silently assuming success.
        """
