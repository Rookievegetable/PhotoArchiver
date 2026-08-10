"""Tests for ArchivePlanner B3 photo_ids filter — 批量归档路径.

覆盖：
- photo_ids 非空时仅规划在选定集内的 APPROVED 项（跳过非选定）
- photo_ids 空元组向后兼容走原路径（全部 APPROVED）
- photo_ids 含不存在 photo_id 时不破（仅过滤 APPROVED 集合，无副作用）
"""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from photo_archiver.application.services import ArchivePlanner
from photo_archiver.domain import Person, Photo

# 复用 test_archive_planner.py 同套替身——直接 import 避免重制（非跨文件私有
# 访问，pytest 发现同模块符号）。为合规本文件重声明同套替身最小集。

from tests.unit.application.test_archive_planner import (
    _FakeArchivePathBuilder,
    _FakeArchiveRecordRepository,
    _FakePersonRepository,
    _FakePhotoRepository,
    _FakeRecognitionRepository,
    _absolute_photo,
    _make_recognition,
)


def _build_planner_with_two_photos(tmp_path: Path) -> tuple[ArchivePlanner, Photo, Photo, Person]:
    """Build planner + two APPROVED photos under one person for photo_ids tests."""
    person = Person(name="Alice")
    photo_a = _absolute_photo("a.jpg", captured_at=datetime(2024, 5, 1), tmp_path=tmp_path)
    photo_b = _absolute_photo("b.jpg", captured_at=datetime(2024, 5, 2), tmp_path=tmp_path)
    rec_a = _make_recognition(photo_a.id, person.id)
    rec_b = _make_recognition(photo_b.id, person.id)
    planner = ArchivePlanner(
        path_builder=_FakeArchivePathBuilder(),
        person_repository=_FakePersonRepository([person]),
        photo_repository=_FakePhotoRepository([photo_a, photo_b]),
        recognition_repository=_FakeRecognitionRepository({person.id: [rec_a, rec_b]}),
        archive_record_repository=_FakeArchiveRecordRepository(),
    )
    return planner, photo_a, photo_b, person


def test_plan_photo_ids_filters_to_selected_subset(tmp_path: Path) -> None:
    """photo_ids 非空时仅规划在选定集内的 APPROVED 项。"""
    planner, photo_a, photo_b, _ = _build_planner_with_two_photos(tmp_path)

    plan = planner.plan("/archive", (), photo_ids=(photo_a.id,))

    assert plan.planned_count == 1
    assert plan.items[0].photo_id == photo_a.id
    planned_ids = {item.photo_id for item in plan.items}
    assert photo_b.id not in planned_ids  # 非选定项被过滤


def test_plan_empty_photo_ids_backward_compatible(tmp_path: Path) -> None:
    """photo_ids 空元组向后兼容——走原路径规划全部 APPROVED。"""
    planner, photo_a, photo_b, _ = _build_planner_with_two_photos(tmp_path)

    plan = planner.plan("/archive", (), photo_ids=())

    assert plan.planned_count == 2
    planned_ids = {item.photo_id for item in plan.items}
    assert planned_ids == {photo_a.id, photo_b.id}


def test_plan_photo_ids_default_backward_compatible(tmp_path: Path) -> None:
    """photo_ids 未传（默认 ()）向后兼容——与原签名调用等价。"""
    planner, photo_a, photo_b, _ = _build_planner_with_two_photos(tmp_path)

    plan_default = planner.plan("/archive", ())
    plan_explicit_empty = planner.plan("/archive", (), photo_ids=())

    assert plan_default.planned_count == plan_explicit_empty.planned_count == 2
    assert {i.photo_id for i in plan_default.items} == {i.photo_id for i in plan_explicit_empty.items}


def test_plan_photo_ids_with_nonexistent_id_no_side_effect(tmp_path: Path) -> None:
    """photo_ids 含不存在 photo_id 时不破——仅过滤 APPROVED 集合，无副作用。"""
    planner, photo_a, photo_b, _ = _build_planner_with_two_photos(tmp_path)

    nonexistent = uuid4()
    plan = planner.plan("/archive", (), photo_ids=(photo_a.id, nonexistent))

    assert plan.planned_count == 1
    assert plan.items[0].photo_id == photo_a.id


def test_plan_photo_ids_empty_subset_yields_empty_plan(tmp_path: Path) -> None:
    """photo_ids 非空但与 APPROVED 集无交集时返回空 plan（非错误）。"""
    planner, _photo_a, _photo_b, _ = _build_planner_with_two_photos(tmp_path)

    unrelated_id = uuid4()
    plan = planner.plan("/archive", (), photo_ids=(unrelated_id,))

    assert plan.planned_count == 0
    assert plan.items == ()
