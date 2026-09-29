"""Single-photo AI work item for the traceable recognition pipeline.

This task is deliberately free of repository writes.  It is submitted to a
ThreadPoolExecutor by :class:`RunRecognitionService`; all database writes are
performed by the consuming/main thread.
"""

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from photo_archiver.domain import FaceBoxEmbedding
from photo_archiver.domain.exceptions import ImageUnreadableError


class FaceAnalysisDetector(Protocol):
    def detect_with_embeddings(self, image: Path) -> list[FaceBoxEmbedding]: ...


@dataclass(frozen=True, slots=True)
class FaceAnalysisResult:
    """Pure result of analyzing one photo, including item-level failure.

    ``cancelled``（AUD-023）＝该照片在开始实际分析前即被取消（worker 已拾取
    但取消已请求）——不产生任何统计计数；消费端在取消流程中本就丢弃其后
    续结果，该标记仅供诊断。
    """

    photo_id: UUID
    faces: tuple[FaceBoxEmbedding, ...] = ()
    unreadable: bool = False
    error: str | None = None
    cancelled: bool = False


class FaceAnalysisTask:
    """Callable adapter that isolates detector failures to one photo.

    ``cancel_event``（AUD-023）：worker 拾取与消费端批量取消之间存在竞争
    窗口——在入口检查取消，使被拾取但未开始的项瞬时退出（安全点语义：
    已进入检测的项照常完成）。
    """

    def __init__(
        self,
        detector: FaceAnalysisDetector,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self._detector = detector
        self._cancel_event = cancel_event

    def __call__(self, photo_id: UUID, image: Path) -> FaceAnalysisResult:
        if self._cancel_event is not None and self._cancel_event.is_set():
            return FaceAnalysisResult(photo_id=photo_id, cancelled=True)
        try:
            faces = tuple(self._detector.detect_with_embeddings(image))
        except ImageUnreadableError as exc:
            return FaceAnalysisResult(photo_id, unreadable=True, error=str(exc))
        except Exception as exc:  # single-photo failure isolation
            return FaceAnalysisResult(photo_id, error=str(exc))
        return FaceAnalysisResult(photo_id=photo_id, faces=faces)
