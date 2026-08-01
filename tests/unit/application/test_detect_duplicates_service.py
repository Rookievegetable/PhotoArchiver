"""Tests for DetectDuplicatesService orchestration (B1 重复图片检测).

落 B1-c 裁决已拍板：服务编排 ``PhotoRepository.list_duplicate_groups`` 产
``DuplicateReport`` DTO 返 Presentation 层。本测试替身仓储走 InMemory。
"""

from datetime import datetime
from pathlib import Path

from photo_archiver.application import DetectDuplicatesService
from photo_archiver.application.dtos import DuplicateReport
from photo_archiver.domain import (
    Photo,
    PhotoMetadata,
    PhotoPath,
    PhotoPathBase,
)
from photo_archiver.infrastructure import InMemoryPhotoRepository


def _make_photo(name: str, content_hash: str | None) -> Photo:
    """Build a Photo with absolute path and optional content hash."""
    return Photo(
        path=PhotoPath(raw_path=Path(f"/tmp/{name}").resolve(), base=PhotoPathBase.ABSOLUTE),
        folder_id=None,
        metadata=PhotoMetadata(
            content_hash=content_hash,
            modified_at=datetime(2026, 8, 1),
            captured_at=datetime(2026, 8, 1),
        ),
        original_name=name,
        captured_at=datetime(2026, 8, 1),
    )


def test_service_empty_repository_returns_empty_report() -> None:
    """空仓储产出空报告——has_duplicates 为 False 且 group_count 为 0。"""
    repo = InMemoryPhotoRepository()
    service = DetectDuplicatesService(repo)

    report = service.execute()

    assert isinstance(report, DuplicateReport)
    assert report.has_duplicates is False
    assert report.group_count == 0
    assert report.photos_in_groups == 0
    assert report.groups == ()


def test_service_all_unique_returns_empty_report() -> None:
    """每张哈希唯一时报告为空——单独哈希不构成组。"""
    repo = InMemoryPhotoRepository()
    for name in ("a", "b", "c"):
        repo.add(_make_photo(name, f"hash_{name}"))
    service = DetectDuplicatesService(repo)

    report = service.execute()

    assert report.has_duplicates is False
    assert report.groups == ()


def test_service_one_group_two_members() -> None:
    """两张同哈希照片归一组——成员数与哈希正确展于 DTO。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", "dup"))
    repo.add(_make_photo("b", "dup"))
    service = DetectDuplicatesService(repo)

    report = service.execute()

    assert report.group_count == 1
    assert report.photos_in_groups == 2
    assert len(report.groups) == 1
    group = report.groups[0]
    assert group.content_hash == "dup"
    assert len(group.members) == 2
    assert {p.original_name for p in group.members} == {"a", "b"}


def test_service_groups_sorted_by_desc_member_count() -> None:
    """多组按成员数降序——"最重复者先列"便于 UI 展示。"""
    repo = InMemoryPhotoRepository()
    for name in ("a", "b", "c"):
        repo.add(_make_photo(name, "big"))  # 3 张
    for name in ("d", "e"):
        repo.add(_make_photo(name, "small"))  # 2 张
    service = DetectDuplicatesService(repo)

    report = service.execute()

    assert report.group_count == 2
    assert len(report.groups[0].members) == 3
    assert report.groups[0].content_hash == "big"
    assert len(report.groups[1].members) == 2
    assert report.groups[1].content_hash == "small"


def test_service_null_hash_photos_excluded() -> None:
    """NULL 哈希历史照片不进入报告——与 B1-a 回填链路衔接契约。"""
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", "dup"))
    repo.add(_make_photo("b", "dup"))
    repo.add(_make_photo("historic", None))
    service = DetectDuplicatesService(repo)

    report = service.execute()

    assert report.group_count == 1
    assert report.photos_in_groups == 2
    assert all("historic" != p.original_name for g in report.groups for p in g.members)


def test_service_frozen_dto_immutable() -> None:
    """DuplicateReport 与 DuplicateGroup 是 frozen dataclass——DTO 不可变守护。"""
    import dataclasses

    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", "dup"))
    repo.add(_make_photo("b", "dup"))
    service = DetectDuplicatesService(repo)

    report = service.execute()
    group = report.groups[0]

    assert dataclasses.is_dataclass(report) and report.__class__.__dataclass_params__.frozen  # type: ignore[attr-defined]
    assert dataclasses.is_dataclass(group) and group.__class__.__dataclass_params__.frozen  # type: ignore[attr-defined]
    try:
        group.members = ()  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("DuplicateGroup must be frozen")
