"""Tests for SearchPhotosService orchestration (B2 搜索/筛选).

本测试替身仓储走 InMemory。覆盖：空 criteria/日期区间/None criteria（无约束）/
排序稳定。
"""

from datetime import datetime
from pathlib import Path

from photo_archiver.application import SearchPhotosService
from photo_archiver.domain import (
    Photo,
    PhotoMetadata,
    PhotoPath,
    PhotoPathBase,
    PhotoSearchCriteria,
)
from photo_archiver.infrastructure import InMemoryPhotoRepository


def _make_photo(name: str, captured_at: datetime | None) -> Photo:
    """Build a Photo with absolute path and captured_at."""
    return Photo(
        path=PhotoPath(raw_path=Path(f"/tmp/{name}").resolve(), base=PhotoPathBase.ABSOLUTE),
        folder_id=None,
        metadata=PhotoMetadata(
            content_hash=None,
            modified_at=datetime(2026, 8, 1),
            captured_at=captured_at,
        ),
        original_name=name,
        captured_at=captured_at,
    )


def test_service_empty_criteria_returns_all_photos() -> None:
    """空 criteria 匹配所有照片——等价 list_all 路径。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", datetime(2026, 7, 1)))
    repo.add(_make_photo("b", datetime(2026, 7, 15)))
    service = SearchPhotosService(repo)

    results = service.execute(PhotoSearchCriteria())

    assert len(results) == 2
    assert {p.original_name for p in results} == {"a", "b"}


def test_service_captured_range_filters() -> None:
    """日期区间过滤经服务编排后结果正确。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("before", datetime(2026, 6, 30)))
    repo.add(_make_photo("in", datetime(2026, 7, 10)))
    repo.add(_make_photo("after", datetime(2026, 7, 20)))
    service = SearchPhotosService(repo)

    results = service.execute(
        PhotoSearchCriteria(
            captured_from=datetime(2026, 7, 1),
            captured_to=datetime(2026, 7, 15),
        ),
    )

    assert {p.original_name for p in results} == {"in"}


def test_service_empty_repository_returns_empty() -> None:
    """空仓储搜索返回空列表。"""
    repo = InMemoryPhotoRepository()
    service = SearchPhotosService(repo)

    results = service.execute(PhotoSearchCriteria())

    assert results == []


def test_service_results_ordered_stable() -> None:
    """结果按 created_at + id 排序——稳定可复现。

    显式设 created_at 区分两张——避免 Photo.__post_init__ 的 datetime.now()
    使排序预期不可控。
    """
    from dataclasses import replace

    repo = InMemoryPhotoRepository()
    b = _make_photo("b", datetime(2026, 7, 15))
    a = _make_photo("a", datetime(2026, 7, 1))
    repo.add(replace(b, created_at=datetime(2026, 7, 15)))
    repo.add(replace(a, created_at=datetime(2026, 7, 1)))
    service = SearchPhotosService(repo)

    results = service.execute(PhotoSearchCriteria())

    assert [p.original_name for p in results] == ["a", "b"]
