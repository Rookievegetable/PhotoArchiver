"""Unit tests for the MatchPersonsService Application-layer orchestration."""

from pathlib import Path
from uuid import uuid4

import pytest

from photo_archiver.application.commands import MatchPersonsCommand
from photo_archiver.application.services import MatchPersonsService
from photo_archiver.domain import (
    FaceEmbedding,
    FaceEmbeddingRepository,
    RecognitionRepository,
)
from photo_archiver.domain.value_objects import FaceBox, FaceBoxEmbedding


class _StubDetector:
    """FaceDetector stub returning preconfigured box/embedding pairs."""

    def __init__(self, pairs_per_image: dict[Path, list]) -> None:
        self._pairs = pairs_per_image

    def detect(self, image: Path) -> list:  # noqa: ARG002
        """Legacy box-only API retained for Protocol compatibility."""
        return [pair.box for pair in self._pairs.get(image, [])]

    def detect_with_embeddings(self, image: Path) -> list:
        return self._pairs.get(image, [])


class _StubRecognizer:
    """FaceRecognizer stub returning a fixed embedding."""

    def __init__(self, embedding: FaceEmbedding) -> None:
        self._embedding = embedding

    def extract(self, image: Path, box) -> FaceEmbedding:  # noqa: ARG002
        return self._embedding

    def extract_from(self, box, faces) -> FaceEmbedding:  # noqa: ARG002
        return self._embedding


class _StubMatcher:
    """PersonMatcher stub returning a preconfigured result."""

    def __init__(self, result: tuple | None) -> None:
        self._result = result
        self.calls: list = []

    def match(self, embedding: FaceEmbedding, candidates: dict) -> tuple | None:  # noqa: ARG002
        self.calls.append((embedding, candidates))
        return self._result


class _StubFaceEmbeddingRepository(FaceEmbeddingRepository):
    """Minimal FaceEmbeddingRepository for service tests."""

    def __init__(self, candidates: dict) -> None:
        self._candidates = candidates

    def save(self, person_id, embedding: FaceEmbedding) -> None:
        self._candidates[person_id] = embedding

    def find_by_person(self, person_id) -> FaceEmbedding | None:
        return self._candidates.get(person_id)

    def list_all(self, limit: int | None = None, offset: int = 0) -> dict:  # noqa: ARG002
        return self._candidates


class _StubRecognitionRepository(RecognitionRepository):
    def __init__(self) -> None:
        self.added: list = []

    def add(self, result) -> None:
        self.added.append(result)

    def find_by_id(self, result_id):
        return None

    def list_by_photo(self, photo_id) -> list:
        return []

    def list_first_by_photo_ids(self, photo_ids) -> dict:
        return {}

    def list_pending(self) -> list:
        return []

    def update_status(self, result_id, status) -> None:
        raise NotImplementedError


def _build_service(
    detector_pairs: dict[Path, list],
    embedding: FaceEmbedding,
    matcher_result: tuple | None,
    candidates: dict | None = None,
    max_workers: int = 1,
) -> tuple[MatchPersonsService, _StubMatcher, _StubRecognitionRepository]:
    """Wire a MatchPersonsService with stubbed ports."""
    detector = _StubDetector(detector_pairs)
    recognizer = _StubRecognizer(embedding)
    matcher = _StubMatcher(matcher_result)
    embedding_repo = _StubFaceEmbeddingRepository(candidates or {})
    recognition_repo = _StubRecognitionRepository()
    service = MatchPersonsService(
        detector=detector,
        recognizer=recognizer,
        matcher=matcher,
        face_embedding_repository=embedding_repo,
        recognition_repository=recognition_repo,
        max_workers=max_workers,
    )
    return service, matcher, recognition_repo


def test_match_service_rejects_length_mismatch() -> None:
    """photo_ids and images tuples must have equal length."""
    service, _, _ = _build_service({}, FaceEmbedding((0.1,)), None)
    command = MatchPersonsCommand(
        photo_ids=(uuid4(),),
        images=(Path("/a.jpg"), Path("/b.jpg")),
    )
    with pytest.raises(ValueError):
        service.execute(command)


def test_match_service_no_face_yields_unknown(tmp_path: Path) -> None:
    """A photo with no detected face must yield a MatchResult with best=None."""
    image = tmp_path / "empty.jpg"
    image.write_bytes(b"")
    service, _, recognition_repo = _build_service(
        {image: []}, FaceEmbedding((0.1,)), None
    )
    photo_id = uuid4()
    command = MatchPersonsCommand(photo_ids=(photo_id,), images=(image,))
    results = service.execute(command)
    assert len(results) == 1
    assert results[0].best is None
    assert results[0].box is None
    assert recognition_repo.added == []


def test_match_service_match_success_persists_result(tmp_path: Path) -> None:
    """A successful match must persist a RecognitionResult with person_id."""
    image = tmp_path / "face.jpg"
    image.write_bytes(b"")
    box = FaceBox(x1=0, y1=0, x2=10, y2=10, confidence=0.9)
    embedding = FaceEmbedding((0.5, 0.5))
    person_id = uuid4()
    service, _, recognition_repo = _build_service(
        {image: [FaceBoxEmbedding(box=box, embedding=embedding)]},
        embedding,
        (person_id, 0.85),
    )
    photo_id = uuid4()
    command = MatchPersonsCommand(photo_ids=(photo_id,), images=(image,))
    results = service.execute(command)
    assert len(results) == 1
    assert results[0].box == box
    assert len(recognition_repo.added) == 1
    persisted = recognition_repo.added[0]
    assert persisted.photo_id == photo_id
    assert persisted.person_id == person_id
    assert persisted.confidence == 0.85
    from photo_archiver.domain import MatchStatus

    assert persisted.status is MatchStatus.PENDING


def test_match_service_unknown_match_persists_without_person(tmp_path: Path) -> None:
    """A below-threshold match must persist a result with person_id=None."""
    image = tmp_path / "face.jpg"
    image.write_bytes(b"")
    box = FaceBox(x1=0, y1=0, x2=10, y2=10)
    embedding = FaceEmbedding((0.1,))
    service, _, recognition_repo = _build_service(
        {image: [FaceBoxEmbedding(box=box, embedding=embedding)]}, embedding, None
    )
    photo_id = uuid4()
    command = MatchPersonsCommand(photo_ids=(photo_id,), images=(image,))
    results = service.execute(command)
    assert results[0].box == box
    assert len(recognition_repo.added) == 1
    persisted = recognition_repo.added[0]
    assert persisted.person_id is None
    assert persisted.confidence == 0.0


def test_match_service_uses_top1_first_face_only(tmp_path: Path) -> None:
    """Per裁决 #5, only the first detected face is matched (Top-1)."""
    image = tmp_path / "two_faces.jpg"
    image.write_bytes(b"")
    box1 = FaceBox(x1=0, y1=0, x2=10, y2=10)
    box2 = FaceBox(x1=20, y1=20, x2=30, y2=30)
    embedding = FaceEmbedding((0.5,))
    service, _, recognition_repo = _build_service(
        {
            image: [
                FaceBoxEmbedding(box=box1, embedding=embedding),
                FaceBoxEmbedding(box=box2, embedding=embedding),
            ]
        },
        embedding,
        (uuid4(), 0.7),
    )
    command = MatchPersonsCommand(
        photo_ids=(uuid4(),), images=(image,)
    )
    service.execute(command)
    assert len(recognition_repo.added) == 1
    assert recognition_repo.added[0].confidence == 0.7


def test_match_service_processes_batch_in_order(tmp_path: Path) -> None:
    """A multi-photo command must yield results in command order."""
    box = FaceBox(x1=0, y1=0, x2=10, y2=10)
    embedding = FaceEmbedding((0.3,))
    image1 = tmp_path / "a.jpg"
    image1.write_bytes(b"")
    image2 = tmp_path / "b.jpg"
    image2.write_bytes(b"")
    id1, id2 = uuid4(), uuid4()
    service, _, _ = _build_service(
        {image1: [FaceBoxEmbedding(box=box, embedding=embedding)], image2: []},
        embedding,
        None,
    )
    command = MatchPersonsCommand(
        photo_ids=(id1, id2), images=(image1, image2)
    )
    results = service.execute(command)
    assert len(results) == 2
    assert results[0].photo_id == id1
    assert results[0].box == box
    assert results[1].photo_id == id2
    assert results[1].box is None


# ── phase6 并行路径（裁决 A-2/A-3/A-4 + §4.4 失败隔离）──────────────────────


def test_match_service_parallel_preserves_order_and_persistence(tmp_path: Path) -> None:
    """并行路径契约：结果按 command 顺序返回；识别记录经 add_many 下推全量持久化."""
    box = FaceBox(x1=0, y1=0, x2=10, y2=10)
    embedding = FaceEmbedding((0.5,))
    person_id = uuid4()
    ids: list = []
    images_list: list[Path] = []
    pairs: dict[Path, list] = {}
    for index in range(6):
        image = tmp_path / f"p{index}.jpg"
        image.write_bytes(b"")
        ids.append(uuid4())
        images_list.append(image)
        # 奇数位照片带脸、偶数位为空——混合批次覆盖两条持久化分支.
        pairs[image] = [FaceBoxEmbedding(box=box, embedding=embedding)] if index % 2 else []
    service, _, recognition_repo = _build_service(
        pairs, embedding, (person_id, 0.8), max_workers=4
    )
    command = MatchPersonsCommand(photo_ids=tuple(ids), images=tuple(images_list))
    results = service.execute(command)
    assert [r.photo_id for r in results] == ids, "A-4 顺序契约：结果必须按 command 顺序"
    assert sum(1 for r in results if r.box is not None) == 3
    assert len(recognition_repo.added) == 3, "A-3：仅匹配成功的照片产生识别记录"
    assert all(r.person_id == person_id for r in recognition_repo.added)


def test_match_service_parallel_equivalent_to_sequential(tmp_path: Path) -> None:
    """§6 等价性对照：同一命令在串行与并行路径下产出逐项等价."""
    box = FaceBox(x1=0, y1=0, x2=10, y2=10)
    embedding = FaceEmbedding((0.5,))
    person_id = uuid4()
    ids: list = []
    images_list: list[Path] = []
    pairs: dict[Path, list] = {}
    for index in range(5):
        image = tmp_path / f"eq{index}.jpg"
        image.write_bytes(b"")
        ids.append(uuid4())
        images_list.append(image)
        pairs[image] = [] if index == 2 else [FaceBoxEmbedding(box=box, embedding=embedding)]
    command = MatchPersonsCommand(photo_ids=tuple(ids), images=tuple(images_list))
    sequential, _, seq_repo = _build_service(pairs, embedding, (person_id, 0.8), max_workers=1)
    parallel, _, par_repo = _build_service(pairs, embedding, (person_id, 0.8), max_workers=4)
    seq_results = sequential.execute(command)
    par_results = parallel.execute(command)
    assert [(r.photo_id, r.box) for r in seq_results] == [(r.photo_id, r.box) for r in par_results]
    seq_keys = [(r.photo_id, r.person_id, r.confidence) for r in seq_repo.added]
    par_keys = [(r.photo_id, r.person_id, r.confidence) for r in par_repo.added]
    assert seq_keys == par_keys, "识别聚合（不含生成态 id/created_at）必须逐项等价"


def test_match_service_parallel_progress_contract(tmp_path: Path) -> None:
    """A-4 进度契约：并行路径沿用串行上报节奏（首末张 + 每 10 张）且序号单调."""
    class _RecordingReporter:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int, str]] = []

        def report(self, current: int, total: int, message: str) -> None:
            self.calls.append((current, total, message))

    embedding = FaceEmbedding((0.3,))
    ids: list = []
    images_list: list[Path] = []
    pairs: dict[Path, list] = {}
    for index in range(4):
        image = tmp_path / f"pr{index}.jpg"
        image.write_bytes(b"")
        ids.append(uuid4())
        images_list.append(image)
        pairs[image] = []
    reporter = _RecordingReporter()
    service = MatchPersonsService(
        detector=_StubDetector(pairs),
        recognizer=_StubRecognizer(embedding),
        matcher=_StubMatcher(None),
        face_embedding_repository=_StubFaceEmbeddingRepository({}),
        recognition_repository=_StubRecognitionRepository(),
        progress_reporter=reporter,  # type: ignore[arg-type]
        max_workers=3,
    )
    service.execute(MatchPersonsCommand(photo_ids=tuple(ids), images=tuple(images_list)))
    currents = [current for current, _, _ in reporter.calls]
    assert currents == sorted(currents), "进度序号必须单调（上报发生在消费线程）"
    assert currents[0] == 1 and currents[-1] == 4, "首末张必须上报"
    assert len(reporter.calls) == 2, "批小于间隔时仅首末两次上报（与串行口径一致）"


@pytest.mark.parametrize("max_workers", [1, 4])
def test_match_service_isolates_detector_failure(tmp_path: Path, max_workers: int) -> None:
    """§4.4 失败隔离：单张分析异常不中断整批（串行与并行路径同契约）."""

    class _BoomDetector(_StubDetector):
        def detect_with_embeddings(self, image: Path) -> list:
            if image.name == "boom.jpg":
                raise RuntimeError("inference failure")
            return self._pairs.get(image, [])

    box = FaceBox(x1=0, y1=0, x2=10, y2=10)
    embedding = FaceEmbedding((0.5,))
    good = tmp_path / "good.jpg"
    good.write_bytes(b"")
    boom = tmp_path / "boom.jpg"
    boom.write_bytes(b"")
    recognition_repo = _StubRecognitionRepository()
    service = MatchPersonsService(
        detector=_BoomDetector({good: [FaceBoxEmbedding(box=box, embedding=embedding)]}),
        recognizer=_StubRecognizer(embedding),
        matcher=_StubMatcher(None),
        face_embedding_repository=_StubFaceEmbeddingRepository({}),
        recognition_repository=recognition_repo,
        max_workers=max_workers,
    )
    id_good, id_boom = uuid4(), uuid4()
    command = MatchPersonsCommand(photo_ids=(id_good, id_boom), images=(good, boom))
    results = service.execute(command)
    assert [r.photo_id for r in results] == [id_good, id_boom], "批次照常完成"
    assert results[0].box == box, "未受影响照片正常产出"
    assert results[1].box is None, "失败照片降级为无脸结果"
    # 好照片（检出一脸、无候选→pending）产生唯一识别记录；失败照片零记录
    assert [r.photo_id for r in recognition_repo.added] == [id_good], "仅未受影响照片产生识别记录"
