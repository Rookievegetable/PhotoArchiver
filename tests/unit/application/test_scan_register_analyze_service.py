"""ScanRegisterAnalyzeService tests — 扫描即识别组合服务（任务书 §3 A1）.

覆盖增量判定四来源（新注册 / 内容更新 / 从未分析 / 最近一次未成功自动
重试）、模型缺失降级、空增量跳过、登记整体失败短路、每次扫描一个识别
运行（[1] 兼容范围 + scan 参数快照）、取消在分析段启动前拦截。
"""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from photo_archiver.application.commands import ScanAndRegisterPhotosCommand
from photo_archiver.application.dtos import (
    ScanAndRegisterPhotosResult,
    ScanRegisterAnalyzeResult,
)
from photo_archiver.application.services.scan_register_analyze_service import (
    ScanRegisterAnalyzeService,
)
from photo_archiver.domain import FaceCountRange, Photo, PhotoPath


@dataclass
class _FakeSnapshot:
    photo_id: UUID
    photo_outcome: str | None = None


class _FakeRunRepository:
    """运行仓储替身：list_runs 按插入逆序（newest first）。"""

    def __init__(self):
        self._runs: list = []
        self._photos: dict = {}

    def add_run(self, run):
        self._runs.insert(0, run)

    def list_runs(self):
        return list(self._runs)

    def add_run_photos(self, run_id, snapshots):
        self._photos.setdefault(run_id, []).extend(snapshots)

    def list_run_photos(self, run_id):
        return list(self._photos.get(run_id, []))


class _FakePhotoRepository:
    def __init__(self):
        self._photos: list = []

    def add(self, photo):
        self._photos.append(photo)
        return photo

    def list_all(self):
        return list(self._photos)

    def find_by_id(self, photo_id):
        return next((p for p in self._photos if p.id == photo_id), None)


class _FakeScanService:
    """登记服务替身：execute 返回预置结果，记录收到的命令。"""

    def __init__(self, result: ScanAndRegisterPhotosResult):
        self.result = result
        self.commands: list = []

    def execute(self, command):
        self.commands.append(command)
        return self.result

    def enumerate_files(self, command):
        return []

    def bind_progress_reporter(self, reporter):
        class _Null:
            def __enter__(self):
                return None

            def __exit__(self, *exc):
                return False
        return _Null()


class _RecognitionRunStub:
    def __init__(self):
        self.id = uuid4()
        self.in_scope_photo_count = 2
        self.out_of_scope_photo_count = 1
        self.no_face_count = 0
        self.unreadable_count = 0
        self.error_count = 0


class _FakeRecognition:
    """识别用例替身：记录命令并返回带统计的运行实体。"""

    def __init__(self):
        self.commands: list = []
        self.cancelled = False

    def execute(self, command):
        self.commands.append(command)
        return _RecognitionRunStub()

    def cancel(self):
        self.cancelled = True

    def bind_progress_reporter(self, reporter):
        class _Null:
            def __enter__(self):
                return None

            def __exit__(self, *exc):
                return False
        return _Null()


class _LegacyRunStub:
    """带 id 的历史运行替身（delta 判定只读 id + run_photos）。"""

    def __init__(self):
        self.id = uuid4()


def _photo(repo: _FakePhotoRepository, name: str) -> Photo:
    photo = Photo(path=PhotoPath(f"photos/{name}"), original_name=name)
    repo.add(photo)
    return photo


def _service(scan_result, recognition=None, *, photos=None, runs=None):
    photos = photos if photos is not None else _FakePhotoRepository()
    runs = runs if runs is not None else _FakeRunRepository()
    service = ScanRegisterAnalyzeService(
        scan_service=_FakeScanService(scan_result),
        recognition_use_case=recognition if recognition is not None else _FakeRecognition(),
        photo_repository=photos,
        recognition_run_repository=runs,
    )
    return service, photos, runs


def _command():
    return ScanAndRegisterPhotosCommand(folder_path=Path("photos/"))


def test_new_and_updated_photos_form_the_delta() -> None:
    photos = _FakePhotoRepository()
    registered = _photo(photos, "a.jpg")
    updated = _photo(photos, "b.jpg")
    result = ScanAndRegisterPhotosResult(
        folder_id=uuid4(),
        registered_photo_ids=(registered.id,),
        updated_photo_ids=(updated.id,),
    )
    service, _, _ = _service(result, photos=photos)
    recognition = service._recognition

    outcome = service.execute(_command())

    assert outcome.analysis_attempted is True
    assert outcome.analysis_skipped_reason is None
    assert set(recognition.commands[0].photo_ids) == {registered.id, updated.id}
    # D6：扫描期兼容审核行口径 = [1]（单脸）；参数快照记 scan 与来源文件夹。
    assert recognition.commands[0].selected_ranges == (FaceCountRange(1, 1),)
    assert recognition.commands[0].parameters["photo_scope"] == "scan"
    assert recognition.commands[0].parameters["folder_display_name"] == "photos"


def test_never_analyzed_and_failed_photos_retry_on_any_scan() -> None:
    photos = _FakePhotoRepository()
    never = _photo(photos, "never.jpg")
    failed = _photo(photos, "failed.jpg")
    done = _photo(photos, "done.jpg")
    runs = _FakeRunRepository()
    legacy = _LegacyRunStub()
    runs.add_run(legacy)
    runs.add_run_photos(legacy.id, [
        _FakeSnapshot(photo_id=done.id, photo_outcome="faces"),
        _FakeSnapshot(photo_id=failed.id, photo_outcome="unreadable"),
    ])
    result = ScanAndRegisterPhotosResult(folder_id=uuid4())
    service, _, _ = _service(result, photos=photos, runs=runs)

    service.execute(_command())

    delta = service._recognition.commands[0].photo_ids
    assert set(delta) == {never.id, failed.id}
    assert done.id not in delta


def test_not_processed_outcome_is_retried() -> None:
    photos = _FakePhotoRepository()
    cancelled = _photo(photos, "cancelled.jpg")
    runs = _FakeRunRepository()
    legacy = _LegacyRunStub()
    runs.add_run(legacy)
    runs.add_run_photos(legacy.id, [
        _FakeSnapshot(photo_id=cancelled.id, photo_outcome="not_processed"),
    ])
    result = ScanAndRegisterPhotosResult(folder_id=uuid4())
    service, _, _ = _service(result, photos=photos, runs=runs)

    service.execute(_command())

    assert service._recognition.commands[0].photo_ids == (cancelled.id,)


def test_empty_delta_skips_analysis() -> None:
    photos = _FakePhotoRepository()
    done = _photo(photos, "done.jpg")
    runs = _FakeRunRepository()
    legacy = _LegacyRunStub()
    runs.add_run(legacy)
    runs.add_run_photos(legacy.id, [
        _FakeSnapshot(photo_id=done.id, photo_outcome="no_face"),
    ])
    result = ScanAndRegisterPhotosResult(folder_id=uuid4())
    service, _, _ = _service(result, photos=photos, runs=runs)

    outcome = service.execute(_command())

    assert outcome.analysis_attempted is False
    assert outcome.analysis_skipped_reason == "no_pending_photos"
    assert outcome.recognition_run is None
    assert service._recognition.commands == []


def test_model_unavailable_registers_only() -> None:
    photos = _FakePhotoRepository()
    _photo(photos, "a.jpg")
    result = ScanAndRegisterPhotosResult(folder_id=uuid4())
    service = ScanRegisterAnalyzeService(
        scan_service=_FakeScanService(result),
        recognition_use_case=None,
        photo_repository=photos,
        recognition_run_repository=_FakeRunRepository(),
    )

    outcome = service.execute(_command())

    assert outcome.analysis_attempted is False
    assert outcome.analysis_skipped_reason == "model_unavailable"
    assert outcome.scan is result
    assert service.analysis_available is False


def test_scan_failure_short_circuits_before_retry_sweep() -> None:
    photos = _FakePhotoRepository()
    _photo(photos, "a.jpg")
    result = ScanAndRegisterPhotosResult(failed_count=1, errors=("枚举失败",))
    service, _, _ = _service(result, photos=photos)

    outcome = service.execute(_command())

    assert outcome.analysis_skipped_reason == "scan_failed"
    assert service._recognition.commands == []


def test_cancel_before_analysis_skips_phase() -> None:
    photos = _FakePhotoRepository()
    registered = _photo(photos, "a.jpg")
    result = ScanAndRegisterPhotosResult(
        folder_id=uuid4(), registered_photo_ids=(registered.id,),
    )
    service, _, _ = _service(result, photos=photos)
    service.cancel()

    outcome = service.execute(_command())

    assert outcome.analysis_skipped_reason == "cancelled"
    assert service._recognition.commands == []


def test_analyzed_photo_count_sums_photo_level_counters() -> None:
    scan_result = ScanAndRegisterPhotosResult(folder_id=uuid4())
    combined = ScanRegisterAnalyzeResult(
        scan=scan_result, analysis_attempted=True, recognition_run=_RecognitionRunStub(),
    )
    assert combined.analyzed_photo_count == 3
    assert ScanRegisterAnalyzeResult(scan=scan_result).analyzed_photo_count == 0
