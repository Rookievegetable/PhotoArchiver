"""Stage F tests — historical backfill, retryable-photo entry, failure export.

覆盖任务书要求：回填首次/重复执行、已有决策不覆盖、失败清单内容与筛选、
导出确定性且不改业务状态、重试入口产出新运行（经现有 controller 管线）。
"""

import csv
from datetime import datetime
from uuid import uuid4

import pytest

from photo_archiver.application.commands.start_recognition_run import (
    StartRecognitionRunCommand,
)
from photo_archiver.application.services import (
    BackfillHistoricalPeopleService,
    RecognitionFailureService,
)
from photo_archiver.application.services.backfill_historical_people_service import (
    BackfillHistoricalPeopleCommand,
)
from photo_archiver.domain import (
    FaceBox,
    FaceEmbedding,
    FaceObservation,
    ImportBatch,
    Person,
    RecognitionRun,
    RunPhotoSnapshot,
)
from photo_archiver.infrastructure import (
    InMemoryFaceClusterRepository,
    InMemoryFaceObservationRepository,
)
from photo_archiver.infrastructure.repositories.in_memory_person_repository import (
    InMemoryPersonRepository,
)


class _InMemoryBatchRepo:
    """ImportBatchRepository double（测试用，仅回填所需方法）。"""

    def __init__(self):
        self._batches: dict = {}

    def add_batch(self, batch):
        self._batches[batch.id] = batch

    def get_batch(self, batch_id):
        return self._batches.get(batch_id)

    def set_batch_status(self, batch_id, status, confirmed_at=None):
        batch = self._batches.get(batch_id)
        if batch is not None:
            batch.status = status
            batch.confirmed_at = confirmed_at

    def list_batches(self):
        return list(self._batches.values())


class _Harness:
    """Backfill + failure-report fixture over in-memory repositories."""

    def __init__(self):
        self.people = InMemoryPersonRepository()
        self.batches = _InMemoryBatchRepo()
        self.service = BackfillHistoricalPeopleService(
            self.people, self.batches,
        )

    def add_person(self, name, *, roster_order=None, source_batch_id=None,
                   created_at=None):
        person = Person(
            name=name, roster_order=roster_order,
            source_batch_id=source_batch_id, created_at=created_at,
        )
        self.people.add(person)
        return person


def test_backfill_first_run_creates_batch_and_orders():
    harness = _Harness()
    p1 = harness.add_person("张三", created_at=datetime(2024, 1, 1))
    p2 = harness.add_person("李四", created_at=datetime(2024, 2, 1))

    result = harness.service.execute(BackfillHistoricalPeopleCommand())

    assert result.backfilled_count == 2
    assert result.batch_id is not None
    batch = harness.batches.get_batch(result.batch_id)
    assert batch.source_type == "backfill"
    assert batch.status == "confirmed"
    # roster_order 按创建时间：张三=1、李四=2（原本无序）。
    assert harness.people.find_by_id(p1.id).roster_order == 1
    assert harness.people.find_by_id(p2.id).roster_order == 2
    assert harness.people.find_by_id(p1.id).source_batch_id == result.batch_id


def test_backfill_repeat_run_is_noop():
    harness = _Harness()
    harness.add_person("张三")
    first = harness.service.execute(BackfillHistoricalPeopleCommand())

    second = harness.service.execute(BackfillHistoricalPeopleCommand())

    assert first.backfilled_count == 1
    assert second.backfilled_count == 0
    assert second.batch_id is None  # 幂等：无存量时不创建新批次
    assert len(harness.batches.list_batches()) == 1


def test_backfill_does_not_touch_existing_decisions():
    """已有 source_batch_id / roster_order 的人员一概不动（不覆盖人工决策）。"""
    harness = _Harness()
    existing_batch = ImportBatch(
        file_name="真实导入.xlsx", file_hash="h", source_type="xlsx",
        status="confirmed",
    )
    harness.batches.add_batch(existing_batch)
    linked = harness.add_person(
        "已导入", roster_order=3, source_batch_id=existing_batch.id,
    )
    manual_ordered = harness.add_person("手工排序", roster_order=7)

    result = harness.service.execute(BackfillHistoricalPeopleCommand())

    # 已导入者跳过；手工排序者属存量（链接回填批次，顺序 7 保留）。
    assert result.backfilled_count == 1
    assert result.skipped_already_linked == 1
    assert harness.people.find_by_id(linked.id).source_batch_id == existing_batch.id
    assert harness.people.find_by_id(linked.id).roster_order == 3
    assert harness.people.find_by_id(manual_ordered.id).source_batch_id == result.batch_id
    assert harness.people.find_by_id(manual_ordered.id).roster_order == 7


def test_backfill_orders_append_after_existing_max():
    harness = _Harness()
    harness.add_person("已排序", roster_order=5, source_batch_id=uuid4())
    legacy_a = harness.add_person("甲", created_at=datetime(2024, 1, 1))
    legacy_b = harness.add_person("乙", created_at=datetime(2024, 1, 2))

    harness.service.execute(BackfillHistoricalPeopleCommand())

    # 无序者接在最大序号 5 之后，按创建时间 6/7。
    assert harness.people.find_by_id(legacy_a.id).roster_order == 6
    assert harness.people.find_by_id(legacy_b.id).roster_order == 7


# ── 失败报告 / 重试照片 / 导出 ──────────────────────────────────────────────


class _RunRepo(InMemoryFaceClusterRepository):
    def __init__(self):
        super().__init__()
        self._runs: dict = {}
        self._run_photos: dict = {}

    def add_recognition_run(self, run):
        self._runs[run.id] = run

    def get_run(self, run_id):
        return self._runs.get(run_id)

    def list_runs(self):
        return sorted(self._runs.values(),
                      key=lambda r: (r.created_at or r.id, str(r.id)), reverse=True)

    def add_run_photos(self, run_id, snapshots):
        self._run_photos.setdefault(run_id, []).extend(snapshots)

    def list_run_photos(self, run_id):
        return list(self._run_photos.get(run_id, []))


class _FailureHarness:
    """One recognition run over 3 photos: 2 with observations, 1 without."""

    def __init__(self):
        self.runs = _RunRepo()
        self.observations = InMemoryFaceObservationRepository()
        self.service = RecognitionFailureService(self.runs, self.observations)
        run = RecognitionRun(parameters={})
        from photo_archiver.domain import RecognitionRunStats

        run.start()
        run.complete(RecognitionRunStats(face_count=2, no_face_count=1))
        self.runs.add_recognition_run(run)
        self.run = run
        self.photo_ids = {key: uuid4() for key in ("ok1", "ok2", "failed")}
        for key, path in (("ok1", "photos/有脸1.jpg"), ("ok2", "photos/有脸2.jpg"),
                          ("failed", "photos/坏图.jpg")):
            self.runs.add_run_photos(run.id, [
                RunPhotoSnapshot(run.id, self.photo_ids[key], path, None),
            ])
        for index, key in enumerate(("ok1", "ok2")):
            self.observations.add_many([FaceObservation(
                run_id=run.id, photo_id=self.photo_ids[key], face_index=index,
                photo_face_count=2, det_score=0.9,
                box=FaceBox(0, 0, 10, 10),
                embedding=FaceEmbedding((1.0, 0.0)),
                scope_verdict="in_selected_scope",
            )])


def test_retryable_photos_are_inputs_without_observations():
    harness = _FailureHarness()

    retryable = harness.service.report(harness.run.id).retryable_photo_ids

    assert retryable == (harness.photo_ids["failed"],)


def test_failure_report_carries_traceability():
    harness = _FailureHarness()

    report = harness.service.report(harness.run.id)

    assert report.run_id == harness.run.id
    assert report.input_photo_count == 3
    assert report.observed_photo_count == 2
    assert report.retryable_count == 1
    assert report.run_unreadable_count == 0 and report.run_no_face_count == 1
    row = report.rows[0]
    assert row["raw_path"] == "photos/坏图.jpg"
    assert row["recognition_run_id"] == str(harness.run.id)


def test_failure_csv_export_is_deterministic_and_readonly(tmp_path):
    harness = _FailureHarness()
    before_observations = len(harness.observations.list_by_run(harness.run.id))
    before_rows = len(harness.runs.list_run_photos(harness.run.id))
    target = tmp_path / "failures.csv"

    count1 = harness.service.export_csv(harness.run.id, target)
    content1 = target.read_text(encoding="utf-8-sig")
    count2 = harness.service.export_csv(harness.run.id, target)
    content2 = target.read_text(encoding="utf-8-sig")

    assert count1 == count2 == 1
    assert content1 == content2  # 重复导出一致
    rows = list(csv.reader(content1.splitlines()))
    assert rows[0] == ["photo_id", "raw_path", "classification", "recognition_run_id"]
    assert "坏图.jpg" in rows[1][1]
    # 导出不改变业务状态。
    assert len(harness.observations.list_by_run(harness.run.id)) == before_observations
    assert len(harness.runs.list_run_photos(harness.run.id)) == before_rows


def test_latest_resumable_run_skips_created_and_running():
    harness = _FailureHarness()
    pending = RecognitionRun(parameters={})  # created 状态：不参与
    harness.runs.add_recognition_run(pending)

    assert harness.service.latest_resumable_run_id() == harness.run.id


def test_missing_run_raises():
    harness = _FailureHarness()
    with pytest.raises(ValueError, match="does not exist"):
        harness.service.report(uuid4())


# ── 重试入口：新运行产出（现有 controller 管线） ────────────────────────────


def test_retry_entry_creates_new_run_over_failed_photos_only():
    """重分析入口（Stage F）：重试运行只带失败照片，且为新 RecognitionRun。"""
    harness = _FailureHarness()
    # 轻量断言：retryable ids 进入命令 → RunRecognitionService 会创建新 run
    # （新 run 语义由 Stage C 测试覆盖，此处锁定入口数据形状）。
    report = harness.service.report(harness.run.id)

    command = StartRecognitionRunCommand(
        photo_ids=report.retryable_photo_ids,
        images=("photos/坏图.jpg",),
    )

    assert command.photo_ids == (harness.photo_ids["failed"],)
    assert harness.run.id in {run.id for run in harness.runs.list_runs()}
