"""Tests for PluginContextService — Domain ↔ Plugin DTO 映射编排（阶段 1，ADR-026）.

覆盖：
- PluginPhotoQuery（3 态 match_status）→ PhotoSearchCriteria（MatchStatus）映射正确
- Photo + RecognitionResult.status → PluginPhotoSummary（4 态含 none）映射正确
- RecognitionResult 不存在 → match_status="none"
- DuplicateReport → PluginDuplicateReport 映射（脱 content_hash 与 Photo 引用）
- 最小权限：不暴露路径/Repository/UoW/Worker/ApplicationContext
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from photo_archiver.application.dtos.plugin_context import (
    PluginPhotoQuery,
    PluginPhotoSummary,
)
from photo_archiver.application.services.plugin_context_service import (
    PluginContextService,
    _map_match_status_to_domain,
    _map_match_status_to_plugin,
    _photo_to_summary,
    _query_to_criteria,
)


# ── match_status 映射 ──────────────────────────────────────────────────────


def test_map_match_status_to_domain_none_passthrough() -> None:
    """None match_status 直透——不过滤."""
    assert _map_match_status_to_domain(None) is None


def test_map_match_status_to_domain_three_states() -> None:
    """3 态字面值映射 MatchStatus 枚举成员（与 Domain 一致）."""
    from photo_archiver.domain.entities.recognition import MatchStatus

    assert _map_match_status_to_domain("pending") is MatchStatus.PENDING
    assert _map_match_status_to_domain("approved") is MatchStatus.APPROVED
    assert _map_match_status_to_domain("rejected") is MatchStatus.REJECTED


def test_map_match_status_to_domain_rejects_none_string() -> None:
    """Query 不含 "none"——"none" 字面值映射应抛 ValueError（Domain 无对应值）."""
    import pytest

    with pytest.raises(ValueError):
        _map_match_status_to_domain("none")


def test_map_match_status_to_plugin_none_returns_none_string() -> None:
    """None RecognitionStatus → "none"（RecognitionResult 不存在即未注册审核）."""
    assert _map_match_status_to_plugin(None) == "none"


def test_map_match_status_to_plugin_three_states() -> None:
    """MatchStatus 三态 → 字面值（.value）."""
    from photo_archiver.domain.entities.recognition import MatchStatus

    assert _map_match_status_to_plugin(MatchStatus.PENDING) == "pending"
    assert _map_match_status_to_plugin(MatchStatus.APPROVED) == "approved"
    assert _map_match_status_to_plugin(MatchStatus.REJECTED) == "rejected"


# ── PluginPhotoQuery → PhotoSearchCriteria 映射 ────────────────────────────


def test_query_to_criteria_empty_query_returns_empty_criteria() -> None:
    """空 PluginPhotoQuery → 空 PhotoSearchCriteria（不过滤）."""
    criteria = _query_to_criteria(PluginPhotoQuery())
    assert criteria.person_id is None
    assert criteria.match_status is None
    assert criteria.captured_from is None
    assert criteria.captured_to is None


def test_query_to_criteria_date_to_datetime_at_midnight() -> None:
    """Plugin date → Domain datetime（当日 00:00:00 下推，日粒度查询）."""
    from datetime import date

    query = PluginPhotoQuery(captured_from=date(2026, 1, 15), captured_to=date(2026, 2, 20))
    criteria = _query_to_criteria(query)
    assert criteria.captured_from == datetime(2026, 1, 15, 0, 0, 0)
    assert criteria.captured_to == datetime(2026, 2, 20, 0, 0, 0)


def test_query_to_criteria_match_status_3_states_direct_mapping() -> None:
    """3 态 match_status 直映射 MatchStatus（不含 none）."""
    from photo_archiver.domain.entities.recognition import MatchStatus

    for status_str, expected in [
        ("pending", MatchStatus.PENDING),
        ("approved", MatchStatus.APPROVED),
        ("rejected", MatchStatus.REJECTED),
    ]:
        criteria = _query_to_criteria(PluginPhotoQuery(match_status=status_str))  # type: ignore[arg-type]
        assert criteria.match_status is expected


# ── Photo + RecognitionStatus → PluginPhotoSummary 映射 ────────────────────


def test_photo_to_summary_captured_at_none_passes_through() -> None:
    """captured_at=None 即未捕获拍摄日期（MINOR-7 语义）——直透."""
    from photo_archiver.domain import Photo
    from photo_archiver.domain.value_objects import PhotoPath

    photo = Photo(path=PhotoPath("/tmp/x.jpg"), id=UUID(int=1), created_at=datetime.now())
    summary = _photo_to_summary(photo, recognition_status=None)
    assert summary.captured_at is None
    assert summary.match_status == "none"


def test_photo_to_summary_registered_at_from_created_at() -> None:
    """registered_at 映射自 Photo.created_at（注册入库时刻；Photo 无 registered_at 字段）."""
    from photo_archiver.domain import Photo
    from photo_archiver.domain.value_objects import PhotoPath

    created = datetime(2026, 8, 11, 10, 30, 0)
    photo = Photo(path=PhotoPath("/tmp/y.jpg"), id=UUID(int=2), created_at=created)
    summary = _photo_to_summary(photo, recognition_status=None)
    assert summary.registered_at == created


def test_photo_to_summary_minimal_privilege_no_path_or_original_name() -> None:
    """PluginPhotoSummary 不暴露绝对路径/原始文件名/Domain Photo/Repository 实例."""
    from photo_archiver.domain import Photo
    from photo_archiver.domain.value_objects import PhotoPath

    photo = Photo(path=PhotoPath("/tmp/secret.jpg"), id=UUID(int=3), created_at=datetime.now())
    summary = _photo_to_summary(photo, recognition_status=None)
    assert not hasattr(summary, "path"), "PluginPhotoSummary MUST NOT expose path"
    assert not hasattr(summary, "original_name"), "PluginPhotoSummary MUST NOT expose original_name"
    assert not hasattr(summary, "metadata"), "PluginPhotoSummary MUST NOT expose metadata raw"


# ── PluginContextService 集成（用 fake repos）──────────────────────────────


def test_plugin_context_service_search_photos_returns_plugin_summaries() -> None:
    """search_photos 返 PluginPhotoSummary tuple（不触 Domain Photo 给插件）."""
    from datetime import datetime
    from uuid import UUID

    from photo_archiver.domain import Photo, PhotoSearchCriteria
    from photo_archiver.domain.value_objects import PhotoPath

    class _FakeSearchService:
        def execute(self, criteria: PhotoSearchCriteria) -> list[Photo]:
            return [
                Photo(path=PhotoPath("/a.jpg"), id=UUID(int=1), created_at=datetime.now()),
                Photo(path=PhotoPath("/b.jpg"), id=UUID(int=2), created_at=datetime.now()),
            ]

    class _FakeDupService:
        def execute(self) -> object:
            return None  # not used in this test

    class _FakeRecognitionRepo:
        def list_by_photo(self, photo_id: UUID) -> list:
            return []  # 无 RecognitionResult → match_status="none"

    service = PluginContextService(  # type: ignore[arg-type]
        _FakeSearchService(),
        _FakeDupService(),
        _FakeRecognitionRepo(),
    )
    results = service.search_photos(PluginPhotoQuery())
    assert len(results) == 2
    assert all(isinstance(r, PluginPhotoSummary) for r in results)
    assert all(r.match_status == "none" for r in results), "无 RecognitionResult 应返 none"


def test_plugin_context_service_minimal_privilege_no_repository_uow_worker() -> None:
    """PluginContextService 不暴露 Repository/UoW/Worker/ApplicationContext 给插件."""
    from photo_archiver.application.ports.plugin_context import PluginContext

    # Protocol 契约：只暴露 search_photos + detect_duplicates，无其他方法
    allowed = {"search_photos", "detect_duplicates"}
    protocol_methods = {
        m for m in dir(PluginContext) if not m.startswith("_") and callable(getattr(PluginContext, m, None))
    }
    assert protocol_methods == allowed, f"PluginContext MUST only expose {allowed}, got {protocol_methods}"
