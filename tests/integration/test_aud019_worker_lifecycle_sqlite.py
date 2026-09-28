"""AUD-019 — Worker 生命周期错误路径（真实 SQLite，Stage 12B）.

沿真实 worker 生命周期（创建 → running → success/failed/cancelled → terminal）
补齐体检覆盖缺口（application_tasks.py 74.1%）：

- ConfirmImportTask（此前完全未覆盖）：真实草稿确认 happy path +
  真实失败（批次不存在）→ failed terminal → 重试成功（失败尝试零副作用）。
- Run/Cluster 任务的无 binder 兜底分支：真实服务链（ClusterFacesService
  天然无 binder；Run/Scan 经真实 execute 的 binder 剥离代理——真实代码运行，
  仅能力探测看到无 binder 形态）。
- 取消边界：cancel → WorkerTaskCancelled → cancelled terminal。
- 终态 exactly-once：多订阅者各收一次 TaskFailed，错误信息不丢失。

禁止假成功：所有断言基于真实数据库行数与真实事件序列。
"""

import types
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands.cluster_faces import StartClusteringRunCommand
from photo_archiver.application.commands.import_draft import (
    ConfirmImportCommand,
    ParseImportDraftCommand,
)
from photo_archiver.application.commands.scan_and_register_photos import (
    ScanAndRegisterPhotosCommand,
)
from photo_archiver.application.commands.start_recognition_run import (
    StartRecognitionRunCommand,
)
from photo_archiver.application.services.cluster_faces_service import ClusterFacesService
from photo_archiver.application.services.confirm_import_service import ConfirmImportService
from photo_archiver.application.services.parse_import_draft_service import (
    ParseImportDraftService,
)
from photo_archiver.application.services.run_recognition_service import (
    RunRecognitionService,
)
from photo_archiver.application.services.scan_and_register_photos_service import (
    ScanAndRegisterPhotosService,
)
from photo_archiver.domain import FaceBox, FaceEmbedding, FaceBoxEmbedding
from photo_archiver.infrastructure import LocalPhotoFileScanner
from photo_archiver.infrastructure.cosine_kernel import NumpyCosineSimilarityFactory
from photo_archiver.infrastructure.database.sqlite_unit_of_work import SQLiteUnitOfWork
from photo_archiver.infrastructure.importers.roster_table_reader import (
    FileRosterTableReader,
)
from photo_archiver.workers.application_tasks import (
    ClusterFacesTask,
    ConfirmImportTask,
    RunRecognitionTask,
    ScanAndRegisterPhotosTask,
)
from photo_archiver.workers.events import (
    TaskCancelled,
    TaskCompleted,
    TaskFailed,
    TaskProgress,
    TaskStarted,
)
from photo_archiver.workers.task import WorkerTaskCancelled


class _Events:
    """Collect task lifecycle events in order."""

    def __init__(self) -> None:
        self.items: list = []

    def __call__(self, event) -> None:
        self.items.append(event)

    def of(self, kind):
        return [event for event in self.items if isinstance(event, kind)]


def _make_image(directory: Path, name: str) -> Path:
    path = directory / name
    Image.new("RGB", (8, 8), (90, 130, 60)).save(path)
    return path


def _seed_draft(repos, tmp_path: Path, rows: list[tuple[str, str, str]]):
    """Real two-stage import up to (but not including) confirmation."""
    csv_path = tmp_path / "roster.csv"
    lines = ["姓名,工号,部门"]
    lines.extend(f"{name},{identity},{department}" for name, identity, department in rows)
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    parse = ParseImportDraftService(
        FileRosterTableReader(), repos.import_batches, repos.people,
    )
    return parse.execute(ParseImportDraftCommand(source_path=csv_path))


def _confirm_service(repos) -> ConfirmImportService:
    return ConfirmImportService(
        repos.import_batches, repos.people,
        unit_of_work=SQLiteUnitOfWork(repos._connection_provider),
    )


def test_confirm_import_task_completes_and_persists_people(tmp_path):
    """ConfirmImportTask 主路径（此前完全未覆盖）：事件序列 + 真实落库。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    draft = _seed_draft(repos, tmp_path, [("张三", "E001", "研发部"), ("李四", "E002", "")])
    task = ConfirmImportTask(
        _confirm_service(repos), ConfirmImportCommand(batch_id=draft.batch.id),
    )
    events = _Events()
    task.subscribe(events)

    result = task.run()

    assert result.imported_count == 2
    assert [type(event) for event in events.items] == [
        TaskStarted, TaskProgress, TaskProgress, TaskCompleted,
    ]
    finish = events.of(TaskProgress)[-1]
    assert finish.message == "Import confirmation finished"
    assert finish.current == 2 and finish.total == 2
    people = repos.people.list_all()
    assert sorted(person.name for person in people) == ["张三", "李四"]


def test_confirm_import_task_failure_is_terminal_then_retry_succeeds(tmp_path):
    """失败路径：真实服务异常 → failed terminal（错误信息保留）→ 重试成功且零重复副作用。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    draft = _seed_draft(repos, tmp_path, [("张三", "E001", "")])

    failing = ConfirmImportTask(
        _confirm_service(repos), ConfirmImportCommand(batch_id=uuid4()),
    )
    events = _Events()
    failing.subscribe(events)
    with pytest.raises(ValueError, match="import batch not found"):
        failing.run()

    failed_events = events.of(TaskFailed)
    assert len(failed_events) == 1                          # 终态恰好一次
    assert "import batch not found" in str(failed_events[0].error)
    assert len(events.of(TaskCompleted)) == 0               # 无假成功
    assert len(repos.people.list_all()) == 0                # 失败尝试零副作用

    # 重试：新任务对象 + 真实批次 → 成功，且人员恰好写入一次
    retry = ConfirmImportTask(
        _confirm_service(repos), ConfirmImportCommand(batch_id=draft.batch.id),
    )
    retry_events = _Events()
    retry.subscribe(retry_events)
    result = retry.run()
    assert result.imported_count == 1
    assert len(retry_events.of(TaskFailed)) == 0
    assert len(repos.people.list_all()) == 1


def test_cluster_faces_task_runs_real_chain_without_binder(tmp_path):
    """ClusterFacesService 天然无 binder → 兜底分支走真实聚类链。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    vectors = {"a.jpg": (1.0, 0.0, 0.0, 0.0), "b.jpg": (0.0, 1.0, 0.0, 0.0)}
    for name in vectors:
        Image.new("RGB", (8, 8), (70, 110, 150)).save(photos_dir / name)

    class _Detector:
        def detect(self, image):
            return self.detect_with_embeddings(image)

        def detect_with_embeddings(self, image):
            return [FaceBoxEmbedding(
                box=FaceBox(x1=0, y1=0, x2=8, y2=8, confidence=0.9),
                embedding=FaceEmbedding(vector=tuple(vectors[image.name])),
            )]

    scan = ScanAndRegisterPhotosService(LocalPhotoFileScanner(), repos.folders, repos.photos)
    scan.execute(ScanAndRegisterPhotosCommand(folder_path=photos_dir))
    photos = repos.photos.list_all()
    run = RunRecognitionService(
        detector=_Detector(), matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=repos.face_embeddings,
        recognition_repository=repos.recognition,
        recognition_run_repository=repos.recognition_runs,
        face_observation_repository=repos.face_observations,
    ).execute(StartRecognitionRunCommand(
        photo_ids=tuple(photo.id for photo in photos),
        images=tuple(photo.path.raw_path for photo in photos),
    ))

    task = ClusterFacesTask(
        ClusterFacesService(
            repos.recognition_runs, repos.face_observations,
            repos.face_clusters, NumpyCosineSimilarityFactory(),
        ),
        StartClusteringRunCommand(run.id),
    )
    events = _Events()
    task.subscribe(events)
    cluster_run = task.run()

    assert cluster_run.status == "completed"
    assert cluster_run.cluster_count == 2
    assert len(repos.face_clusters.list_clusters(cluster_run.id)) == 2
    assert [type(event) for event in events.items] == [
        TaskStarted, TaskProgress, TaskCompleted,
    ]                                                       # 无 binder → 无完成进度标记


def test_scan_and_run_tasks_fallback_without_binder(tmp_path):
    """Scan/Run 任务的无 binder 兜底：真实 execute 绑定方法剥离能力属性（AUD-019 缺口分支）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    for index, name in enumerate(("x.jpg", "y.jpg")):
        Image.new("RGB", (8, 8), (100 + index, 80, 60)).save(photos_dir / name)

    real_scan = ScanAndRegisterPhotosService(
        LocalPhotoFileScanner(), repos.folders, repos.photos,
    )
    binderless_scan = types.SimpleNamespace(execute=real_scan.execute)
    scan_task = ScanAndRegisterPhotosTask(
        binderless_scan, ScanAndRegisterPhotosCommand(folder_path=photos_dir),
    )
    scan_events = _Events()
    scan_task.subscribe(scan_events)
    scan_result = scan_task.run()
    assert scan_result.registered_count == 2                # 真实扫描照常完成
    assert scan_events.of(TaskFailed) == []

    photos = repos.photos.list_all()
    real_run = RunRecognitionService(
        detector=_RecognitionDetector(vectors={
            "x.jpg": (1.0, 0.0, 0.0, 0.0), "y.jpg": (0.0, 1.0, 0.0, 0.0),
        }),
        matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=repos.face_embeddings,
        recognition_repository=repos.recognition,
        recognition_run_repository=repos.recognition_runs,
        face_observation_repository=repos.face_observations,
    )
    binderless_run = types.SimpleNamespace(execute=real_run.execute)
    run_task = RunRecognitionTask(
        binderless_run, StartRecognitionRunCommand(
            photo_ids=tuple(photo.id for photo in photos),
            images=tuple(photo.path.raw_path for photo in photos),
        ),
    )
    run_events = _Events()
    run_task.subscribe(run_events)
    recognition_run = run_task.run()
    assert recognition_run.status == "completed"
    assert len(repos.face_observations.list_by_run(recognition_run.id)) == 2
    assert run_events.of(TaskFailed) == []


def test_recognition_task_cancel_before_start_yields_cancelled_terminal(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    real_run = RunRecognitionService(
        detector=_RecognitionDetector(vectors={}),
        matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=repos.face_embeddings,
        recognition_repository=repos.recognition,
        recognition_run_repository=repos.recognition_runs,
        face_observation_repository=repos.face_observations,
    )
    task = RunRecognitionTask(
        real_run, StartRecognitionRunCommand(photo_ids=(), images=()),
    )
    events = _Events()
    task.subscribe(events)

    task.cancel("user requested")
    assert task.is_cancel_requested
    with pytest.raises(WorkerTaskCancelled):
        task.run()

    assert len(events.of(TaskCancelled)) == 1
    assert events.of(TaskCompleted) == [] and events.of(TaskFailed) == []
    assert len(repos.recognition_runs.list_runs()) == 0     # 未产生任何 run


def test_failed_terminal_exactly_once_across_subscribers(tmp_path):
    """多订阅者 + 失败：每个订阅者恰好一次 TaskFailed，错误信息完整保留。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    task = ConfirmImportTask(
        _confirm_service(repos), ConfirmImportCommand(batch_id=uuid4()),
    )
    first, second = _Events(), _Events()
    task.subscribe(first)
    task.subscribe(second)

    with pytest.raises(ValueError):
        task.run()

    assert len(first.of(TaskFailed)) == 1
    assert len(second.of(TaskFailed)) == 1
    assert first.of(TaskFailed)[0].task_id == second.of(TaskFailed)[0].task_id
    assert "import batch not found" in str(first.of(TaskFailed)[0].error)


class _RecognitionDetector:
    """按文件名返回预定人脸（与 Stage 12A 全链测试相同的可控假件口径）。"""

    def __init__(self, vectors: dict[str, tuple[float, ...]]):
        self._vectors = vectors

    def detect(self, image):
        return self.detect_with_embeddings(image)

    def detect_with_embeddings(self, image):
        vector = self._vectors.get(image.name)
        if vector is None:
            return []
        return [FaceBoxEmbedding(
            box=FaceBox(x1=0, y1=0, x2=8, y2=8, confidence=0.9),
            embedding=FaceEmbedding(vector=tuple(vector)),
        )]
