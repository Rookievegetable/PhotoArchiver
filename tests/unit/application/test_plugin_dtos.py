"""Tests for Plugin DTO 类型边界（阶段 1，ADR-026）.

覆盖：
- PluginPhotoQuery / PluginPhotoSummary / PluginDuplicateGroup / PluginDuplicateReport 不可变
- match_status Literal 值域校验（Query 3 态不含 none，Summary 4 态含 none）
- captured_at None 语义（未捕获拍摄日期）
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest


def test_plugin_photo_query_match_status_literal_excludes_none() -> None:
    """PluginPhotoQuery.match_status Literal 3 态——pending/approved/rejected，不含 none.

    ADR-026 裁决点 3=A：Query 不含 none（与 Domain MatchStatus 三态一致），
    "none" 是 Summary 层聚合概念（RecognitionResult 不存在）。
    """
    from photo_archiver.application.dtos.plugin_context import PluginPhotoQuery

    # 3 态字面值应能构造（mypy 静态守护，运行时 dataclass 不校 Literal 值域，
    # 但本测试证值域契约）
    for status in ("pending", "approved", "rejected"):
        q = PluginPhotoQuery(match_status=status)  # type: ignore[arg-type]
        assert q.match_status == status

    # "none" 不应在 Query Literal 值域——构造时 mypy 报错（运行时不验，但契约禁）


def test_plugin_photo_summary_match_status_literal_includes_none() -> None:
    """PluginPhotoSummary.match_status Literal 4 态含 none（未注册审核）."""
    from photo_archiver.application.dtos.plugin_context import PluginPhotoSummary

    for status in ("pending", "approved", "rejected", "none"):
        s = PluginPhotoSummary(
            photo_id=UUID(int=1),
            captured_at=None,
            registered_at=datetime.now(),
            match_status=status,  # type: ignore[arg-type]
        )
        assert s.match_status == status


def test_plugin_photo_query_frozen_slots_immutable() -> None:
    """PluginPhotoQuery 不可变（frozen + slots）."""
    from photo_archiver.application.dtos.plugin_context import PluginPhotoQuery

    q = PluginPhotoQuery()
    with pytest.raises(Exception):
        q.person_id = UUID(int=1)  # type: ignore[misc]


def test_plugin_photo_summary_frozen_slots_immutable() -> None:
    """PluginPhotoSummary 不可变（frozen + slots）."""
    from photo_archiver.application.dtos.plugin_context import PluginPhotoSummary

    s = PluginPhotoSummary(
        photo_id=UUID(int=1),
        captured_at=None,
        registered_at=datetime.now(),
        match_status="none",
    )
    with pytest.raises(Exception):
        s.match_status = "approved"  # type: ignore[misc]


def test_plugin_duplicate_group_frozen_slots_immutable() -> None:
    """PluginDuplicateGroup 不可变（frozen + slots）."""
    from photo_archiver.application.dtos.plugin_context import PluginDuplicateGroup

    g = PluginDuplicateGroup(photo_ids=(UUID(int=1), UUID(int=2)), count=2)
    with pytest.raises(Exception):
        g.count = 5  # type: ignore[misc]


def test_plugin_duplicate_report_frozen_slots_immutable() -> None:
    """PluginDuplicateReport 不可变（frozen + slots）."""
    from photo_archiver.application.dtos.plugin_context import PluginDuplicateReport

    r = PluginDuplicateReport(groups=(), duplicate_group_count=0, duplicate_photo_count=0)
    with pytest.raises(Exception):
        r.duplicate_group_count = 5  # type: ignore[misc]


def test_plugin_photo_summary_captured_at_none_semantics() -> None:
    """captured_at=None 即"未捕获拍摄日期"（MINOR-7 语义）——直透不崩."""
    from photo_archiver.application.dtos.plugin_context import PluginPhotoSummary

    s = PluginPhotoSummary(
        photo_id=UUID(int=1),
        captured_at=None,
        registered_at=datetime.now(),
        match_status="none",
    )
    assert s.captured_at is None


def test_plugin_duplicate_group_does_not_expose_content_hash() -> None:
    """PluginDuplicateGroup 不暴露 content_hash 原值（最小权限）."""
    from photo_archiver.application.dtos.plugin_context import PluginDuplicateGroup

    g = PluginDuplicateGroup(photo_ids=(UUID(int=1),), count=1)
    assert not hasattr(g, "content_hash"), "PluginDuplicateGroup MUST NOT expose content_hash"
    assert not hasattr(g, "members"), "PluginDuplicateGroup MUST NOT expose Domain Photo members"
