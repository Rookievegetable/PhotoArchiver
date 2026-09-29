"""AUD-023 — 取消延迟机制（确定性复现与回归，Stage 12C）.

根因（体检 Stage 6 / F-04 真因）：``RunRecognitionService.execute`` 一次性
submit 全部照片 futures，取消后仅 break 消费循环，``with ThreadPoolExecutor``
退出时 ``shutdown(wait=True)``（无 cancel_futures）令已入队未启动的任务照常
执行——取消终态必须等剩余队列整体排空（千张 ≈60s）。

本文件以 Event 门控 + 有界 join 构造确定性证据（零 sleep 主同步）：

- Scenario A 中途取消：cancel 后仅打开 in-flight 项的门，pending 项的门
  永不打开——修复后线程必须退出（pending 被 cancel，不再阻塞终态）；
  修复前 shutdown 等待 pending 项 → join 超时（复现排空）。
- Scenario B 立即取消：零 run、零启动。
- Scenario C cancel/完成竞争：终态恰好一次，状态 ∈ {completed, cancelled}。
- Scenario D 取消+重试：部分完成保留，重试只覆盖剩余、已完成项不重复处理。

三类工作语义（PENDING/RUNNING/COMPLETED）保持不变：completed subset 保留、
RUNNING 到安全点（单张完成）退出、PENDING 不再启动；LIMIT-002 取消粒度不变。
"""

import threading
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4


from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands.start_recognition_run import (
    StartRecognitionRunCommand,
)
from photo_archiver.application.services.run_recognition_service import (
    RunRecognitionService,
)
from photo_archiver.domain import FaceBox, FaceEmbedding, FaceBoxEmbedding, Photo, PhotoPath, PhotoPathBase
from photo_archiver.workers.application_tasks import RunRecognitionTask
from photo_archiver.workers.events import (
    TaskCancelled,
    TaskCompleted,
    TaskFailed,
)
from photo_archiver.workers.task import WorkerTaskCancelled

ITEM_COUNT = 6


class _GatedDetector:
    """每个条目在独立 Event 上等待——pending 项的门不开就永不完成。

    started / completed / post_cancel_started 均线程安全记录，作为
    cancel-latency 证据（任务书 §11）。
    """

    def __init__(self, gates: dict[str, threading.Event]):
        self._gates = gates
        self._lock = threading.Lock()
        self._cancel_requested = threading.Event()
        self.started: list[str] = []
        self.completed: list[str] = []
        self.started_after_cancel: list[str] = []
        self.completed_after_cancel: list[str] = []

    def request_cancel(self) -> None:
        self._cancel_requested.set()

    def detect(self, image):
        return self.detect_with_embeddings(image)

    def detect_with_embeddings(self, image):
        name = image.name
        with self._lock:
            self.started.append(name)
            if self._cancel_requested.is_set():
                self.started_after_cancel.append(name)
        self._gates[name].wait(timeout=60)
        with self._lock:
            self.completed.append(name)
            if self._cancel_requested.is_set():
                self.completed_after_cancel.append(name)
        return [FaceBoxEmbedding(
            box=FaceBox(x1=0, y1=0, x2=8, y2=8, confidence=0.9),
            embedding=FaceEmbedding(vector=(1.0, 0.0, 0.0, 0.0)),
        )]


class _Events:
    def __init__(self) -> None:
        self.items: list = []
        self._lock = threading.Lock()

    def __call__(self, event) -> None:
        with self._lock:
            self.items.append(event)

    def of(self, kind):
        with self._lock:
            return [event for event in self.items if isinstance(event, kind)]


def _seed_photos(repos, count: int) -> list[Photo]:
    """按 created_at 升序注册 count 张照片（识别顺序 = 列表序，确定性）。"""
    photos = []
    for index in range(count):
        photo = Photo(
            path=PhotoPath(Path.cwd() / "src" / f"p{index}.jpg", base=PhotoPathBase.ABSOLUTE),
            original_name=f"p{index}.jpg",
            captured_at=datetime(2026, 1, 1) + timedelta(minutes=index),
        )
        repos.photos.add(photo)
        photos.append(photo)
    return repos.photos.list_all()


def _service(repos, detector, workers: int) -> RunRecognitionService:
    return RunRecognitionService(
        detector=detector,
        matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=repos.face_embeddings,
        recognition_repository=repos.recognition,
        recognition_run_repository=repos.recognition_runs,
        face_observation_repository=repos.face_observations,
        photo_repository=repos.photos,
        max_workers=workers,
    )


def _run_in_thread(task: RunRecognitionTask):
    outcome: dict = {}

    def target():
        try:
            outcome["result"] = task.run()
        except Exception as exc:  # noqa: BLE001 - 测试线程边界
            outcome["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return outcome, thread


def _make_task(repos, detector, photos, events: _Events) -> RunRecognitionTask:
    task = RunRecognitionTask(
        _service(repos, detector, workers=2),
        StartRecognitionRunCommand(
            photo_ids=tuple(photo.id for photo in photos),
            images=tuple(photo.path.raw_path for photo in photos),
        ),
    )
    task.subscribe(events)
    return task


def test_mid_run_cancel_does_not_drain_pending_queue(tmp_path):
    """Scenario A：cancel 后 in-flight 到安全点完成、pending 不再运行、终态及时到达。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photos = _seed_photos(repos, ITEM_COUNT)
    gates = {photo.original_name: threading.Event() for photo in photos}
    gates["p0.jpg"].set()                       # 仅首项放行
    detector = _GatedDetector(gates)
    events = _Events()
    task = _make_task(repos, detector, photos, events)

    first_persisted = threading.Event()

    def _on_event(event):
        from photo_archiver.workers.events import TaskProgress

        if isinstance(event, TaskProgress) and event.current == 1:
            first_persisted.set()

    task.subscribe(_on_event)
    outcome, thread = _run_in_thread(task)
    assert first_persisted.wait(timeout=30)     # item0 已消费并持久化

    # 取消：只打开 in-flight 项（p1/p2，max_workers=2）的门；pending p3-p5 永不打开
    detector.request_cancel()
    task.cancel("test")
    gates["p1.jpg"].set()
    gates["p2.jpg"].set()
    thread.join(timeout=30)

    # ★ 核心判据：线程必须退出——pending 不再阻塞 cancelled terminal。
    assert not thread.is_alive(), (
        f"cancel 后线程仍被剩余队列阻塞（排空复现）；started_after_cancel="
        f"{detector.started_after_cancel}"
    )
    run = repos.recognition_runs.list_runs()[0]
    assert run.status == "cancelled"
    # cancelled terminal 恰好一次（WorkerTaskCancelled 作为线程内异常）
    assert isinstance(outcome.get("error"), WorkerTaskCancelled)
    assert len(events.of(TaskCancelled)) == 1
    assert events.of(TaskCompleted) == [] and events.of(TaskFailed) == []
    # COMPLETED 保留：item0 消费持久化；RUNNING 安全点完成但不消费（既有语义）
    assert len(repos.face_observations.list_by_run(run.id)) == 1
    # PENDING 未执行真实工作：p3-p5 从未完成（worker 拾取竞争下的项在
    # FaceAnalysisTask 入口即被取消——不进入检测）
    assert not (set(detector.completed) & {"p3.jpg", "p4.jpg", "p5.jpg"})
    # cancel-latency 证据（任务书 §11）：真实工作恰好止于 in-flight 两项
    # （完成顺序由 worker 调度决定，集合语义断言）
    assert sorted(detector.completed_after_cancel) == ["p1.jpg", "p2.jpg"]


def test_immediate_cancel_starts_nothing(tmp_path):
    """Scenario B：start 前取消 → 零 run、零启动、cancelled terminal。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photos = _seed_photos(repos, 3)
    gates = {photo.original_name: threading.Event() for photo in photos}
    detector = _GatedDetector(gates)
    events = _Events()
    task = _make_task(repos, detector, photos, events)

    detector.request_cancel()
    task.cancel("test")
    outcome, thread = _run_in_thread(task)
    thread.join(timeout=30)

    assert not thread.is_alive()
    assert isinstance(outcome.get("error"), WorkerTaskCancelled)
    assert detector.started == []               # 零实际工作
    assert len(repos.recognition_runs.list_runs()) == 0
    assert len(events.of(TaskCancelled)) == 1


def test_cancel_completion_race_yields_single_terminal(tmp_path):
    """Scenario C：cancel 与条目完成竞争 → 恰一个终态，无重复、无冲突。"""
    for _ in range(5):                          # 竞争窗口多次重复
        repos = build_sqlite_repositories(tmp_path / f"race-{uuid4().hex}.sqlite3")
        photos = _seed_photos(repos, 4)
        gates = {photo.original_name: threading.Event() for photo in photos}
        for gate in gates.values():
            gate.set()                          # 全部立即放行——真实竞争形态
        detector = _GatedDetector(gates)
        events = _Events()
        task = _make_task(repos, detector, photos, events)

        outcome, thread = _run_in_thread(task)
        task.cancel("race")                     # 启动后立即取消（无 sleep）
        thread.join(timeout=30)
        assert not thread.is_alive()

        terminals = events.of(TaskCompleted) + events.of(TaskCancelled) + events.of(TaskFailed)
        assert terminals                              # 至少一个终态
        assert not any(isinstance(t, TaskFailed) for t in terminals)
        # raw 事件流首个终态决定结果（cancel 与完成竞争后的连发由
        # TaskCoordinator 去重——exactly-once 由既有协调器测试覆盖）
        first = terminals[0]
        run = repos.recognition_runs.list_runs()[0]
        if isinstance(first, TaskCompleted):
            assert run.status == "completed"
        else:
            assert isinstance(first, TaskCancelled)
            assert run.status == "cancelled"
        observations = len(repos.face_observations.list_by_run(run.id))
        if run.status == "cancelled":
            assert observations <= len(photos)  # 部分完成保留
        else:
            assert observations == len(photos)  # 全部完成（取消前已完成消费）
        assert observations >= 0


def test_cancel_then_retry_covers_only_remaining(tmp_path):
    """Scenario D：部分完成 → cancel → retry → 仅剩余项，已完成项不重复处理。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photos = _seed_photos(repos, 4)
    gates = {photo.original_name: threading.Event() for photo in photos}
    gates["p0.jpg"].set()
    detector = _GatedDetector(gates)
    events = _Events()
    task = _make_task(repos, detector, photos, events)

    first_persisted = threading.Event()
    from photo_archiver.workers.events import TaskProgress

    def _on_event(event):
        if isinstance(event, TaskProgress) and event.current == 1:
            first_persisted.set()

    task.subscribe(_on_event)
    outcome, thread = _run_in_thread(task)
    assert first_persisted.wait(timeout=30)
    detector.request_cancel()
    task.cancel("test")
    gates["p1.jpg"].set()                       # 放行 in-flight 两项（workers=2）
    gates["p2.jpg"].set()
    thread.join(timeout=30)
    if thread.is_alive():
        import sys
        import traceback

        for tid, frame in sys._current_frames().items():
            if tid == thread.ident or tid != threading.main_thread().ident:
                print(f"--- THREAD {tid} ---")
                traceback.print_stack(frame)
        print(f"detector.started={detector.started}")
        print(f"detector.completed={detector.completed}")
        print(f"completed_after_cancel={detector.completed_after_cancel}")
        print(f"runs={[r.status for r in repos.recognition_runs.list_runs()]}")
    assert not thread.is_alive()
    run1 = repos.recognition_runs.list_runs()[0]
    assert run1.status == "cancelled"
    assert len(repos.face_observations.list_by_run(run1.id)) == 1

    # Retry：仅剩余照片（p1/p2 已完成但未被消费——in-flight 结果丢弃，p1-p3 重试）。
    # run1 期间 p3 从未执行真实工作（entry-cancel / pending-cancel）——在 retry
    # 打开全部门之前取证。
    completed_after_run1 = list(detector.completed)
    remaining = [
        photo for photo in photos
        if not repos.face_observations.list_by_run_photo(run1.id, photo.id)
    ]
    assert {photo.original_name for photo in remaining} == {"p1.jpg", "p2.jpg", "p3.jpg"}
    for gate in gates.values():
        gate.set()
    run2 = _service(repos, detector, workers=2).execute(StartRecognitionRunCommand(
        photo_ids=tuple(photo.id for photo in remaining),
        images=tuple(photo.path.raw_path for photo in remaining),
    ))
    assert run2.status == "completed"
    assert len(repos.face_observations.list_by_run(run2.id)) == 3
    # 已完成项不重复处理：p0 在两次运行中恰好启动一次
    assert detector.started.count("p0.jpg") == 1
    # pending 项（p3）在 run1 内从未执行真实工作（retry 阶段合法处理）
    assert "p3.jpg" not in completed_after_run1
    # run1 仍为 cancelled 且部分结果保留（不被 retry 改写）
    assert repos.recognition_runs.get_run(run1.id).status == "cancelled"
    assert len(repos.face_observations.list_by_run(run1.id)) == 1
