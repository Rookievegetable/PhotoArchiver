"""Read-only photo detail dialog (Batch 4; HD preview 2026-09-30).

Larger preview plus the archival context of one photo — original name,
path, capture time and the recognition/archival badge. Data comes from
the already-loaded Photo entity and the cached thumbnail file.

预览数据源分两档（2026-09-30 高清预览方案）：

- 打开即显示缓存缩略图（≤256px 源，自然尺寸居中于固定包围盒，不额外放大）；
- 用户点击【查看大图】后，经 QThreadPool 异步受控解码原图
  （``photo.path.raw_path``：QImageReader + setAutoTransform + setScaledSize，
  目标 = 固定包围盒 aspect-fit × devicePixelRatio，小图源 clamp 到原始
  像素尺寸），成功替换并隐藏按钮；失败保留缩略图并轻提示，绝不退回
  pending。

UI 线程除"极小缩略图文件解码"外不做任何原图 IO（Batch 4 设计维持）；
原图 IO 只发生在用户主动点击后的工作线程。JPEG 走 DCT 降采样真受控
解码；PNG 等格式由 QImageReader 全量解码后内存内缩放（瞬时内存 =
最大 PNG，工作线程内一次性）。竞态防护 = 关闭标志（done() 全路径）+
递增 request_id（过期结果直接丢弃，见 :data:`_dropped_requests` 测试/QA
钩子）。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.domain import Photo
from photo_archiver.presentation import ui_text as text

# 固定预览包围盒（logical px）：aspect-fit 显示，缩略图与高清图同一区域，
# 对话框尺寸不随照片长宽比跳变；解码目标 = 包围盒 fit × devicePixelRatio。
_PREVIEW_BOX = QSize(640, 480)


def _decode_preview(path: Path, box: QSize, dpr: float) -> QImage:
    """受控解码原图到预览物理尺寸（可注入测试边界）。

    aspect-fit 到 ``box``（逻辑）后乘 ``dpr`` 得目标物理尺寸；小图源
    clamp 到原始像素尺寸（不放大解码）。输出端经 ``setDevicePixelRatio``
    归位，保证显示逻辑尺寸恒等于 fit 尺寸（盒内、不跳变）。原图不可读
    （缺失/不支持/损坏）时返回 null QImage，调用方降级到缩略图。
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    original = reader.size()
    if original.isValid() and not original.isEmpty():
        fit = original.scaled(box, Qt.AspectRatioMode.KeepAspectRatio)
        target = QSize(round(fit.width() * dpr), round(fit.height() * dpr))
        if target.width() > original.width() or target.height() > original.height():
            target = QSize(original)
        reader.setScaledSize(target)
    image = reader.read()
    if image.isNull():
        return QImage()
    if not (original.isValid() and not original.isEmpty()):
        # 元数据不可得的罕见格式：完整解码后内存内受控缩放兜底。
        max_physical = QSize(
            round(box.width() * dpr), round(box.height() * dpr),
        )
        if (
            image.width() > max_physical.width()
            or image.height() > max_physical.height()
        ):
            image = image.scaled(
                max_physical,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return image
    fit = original.scaled(box, Qt.AspectRatioMode.KeepAspectRatio)
    image.setDevicePixelRatio(image.width() / fit.width())
    return image


class _PreviewDecodeJob(QRunnable):
    """后台受控解码原图（模级 QRunnable，复用 _ThumbnailJob 同构模式）。

    Worker 只做文件读取/解码/QImage；QWidget 与 QPixmap 只在 UI 线程触碰。
    DPR 在点击时于 UI 线程捕获后传入，不在 worker 里调用 QWidget 方法。
    """

    def __init__(
        self,
        request_id: int,
        path: Path,
        box: QSize,
        dpr: float,
        decoder: Callable[[Path, QSize, float], QImage],
        dialog: "PhotoDetailDialog",
    ) -> None:
        super().__init__()
        self._request_id = request_id
        self._path = path
        self._box = box
        self._dpr = dpr
        self._decoder = decoder
        self._dialog = dialog

    def run(self) -> None:
        try:
            image = self._decoder(self._path, self._box, self._dpr)
        except Exception:  # noqa: BLE001 - 意外异常按失败降级，线程不携带异常退出
            image = QImage()
        try:
            self._dialog.preview_decoded.emit(self._request_id, image)
        except RuntimeError:
            # 对话框 C++ 对象已销毁（关闭竞态尾部）：结果无人接收，安全丢弃。
            pass


class PhotoDetailDialog(QDialog):
    """Show one photo's read-only details; double-click entry in the library."""

    # (request_id, decoded QImage)；worker 线程 emit → 队列连接回 UI 线程。
    preview_decoded = Signal(int, QImage)

    def __init__(
        self,
        photo: Photo,
        badge: str | None = None,
        thumbnail_path: Path | None = None,
        parent: QWidget | None = None,
        decoder: Callable[[Path, QSize, float], QImage] | None = None,
    ) -> None:
        """Compose the preview and metadata rows from already-loaded data.

        ``decoder`` 仅测试注入（§8 可替换边界）；生产恒为真实
        :func:`_decode_preview`。
        """
        super().__init__(parent)
        self.setWindowTitle(text.PHOTO_DETAIL_TITLE)
        self._photo = photo
        self._decoder = decoder or _decode_preview
        self._closed = False
        self._request_id = 0
        # 测试/QA 钩子：过期/关闭后丢弃的结果计数（T9/T10 契约观测点）。
        self._dropped_requests = 0
        # Worker 结果经显式 QueuedConnection 回 UI 线程（同 PhotoListController
        # 的 thumbnail_loaded 接线）——QImage 跨线程传递、QPixmap 转换在 UI 线程。
        self.preview_decoded.connect(
            self._on_preview_decoded, Qt.QueuedConnection,  # type: ignore[attr-defined]
        )
        layout = QVBoxLayout(self)

        preview = QLabel(self)
        preview.setFixedSize(_PREVIEW_BOX)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview = preview
        pixmap = QPixmap()
        has_thumbnail = False
        if thumbnail_path is not None:
            pixmap.load(str(thumbnail_path))
        if not pixmap.isNull():
            # 占位即显：缩略图自然尺寸居中（不额外放大 256px 源）。
            preview.setPixmap(pixmap)
            has_thumbnail = True
        else:
            preview.setText(text.PHOTO_DETAIL_THUMB_PENDING)
        layout.addWidget(preview)

        self._hd_status_label = QLabel(text.PHOTO_DETAIL_HD_FAILED, self)
        self._hd_status_label.setVisible(False)
        layout.addWidget(self._hd_status_label)

        self._view_full_button = QPushButton(text.PHOTO_DETAIL_VIEW_FULL, self)
        self._view_full_button.clicked.connect(self._on_view_full_size_clicked)
        self._view_full_button.setVisible(has_thumbnail)
        layout.addWidget(self._view_full_button)

        name = photo.original_name or photo.path.raw_path
        layout.addWidget(QLabel(text.PHOTO_DETAIL_NAME.format(name=name), self))
        layout.addWidget(QLabel(
            text.PHOTO_DETAIL_PATH.format(path=photo.path.raw_path), self,
        ))
        if photo.captured_at is not None:
            captured = text.PHOTO_DETAIL_CAPTURED.format(
                time=photo.captured_at.strftime("%Y-%m-%d %H:%M"),
            )
        else:
            captured = text.PHOTO_DETAIL_CAPTURED_UNKNOWN
        layout.addWidget(QLabel(captured, self))
        status = text.PHOTO_DETAIL_STATUS.format(
            badge=badge if badge else text.FILTER_STATUS_UNMATCHED,
        )
        layout.addWidget(QLabel(status, self))
        layout.addStretch()

    @Slot()
    def _on_view_full_size_clicked(self) -> None:
        """启动一次高清预览请求（按钮置灰防重复；request_id 防过期覆盖）。"""
        if self._closed:
            return
        self._request_id += 1
        self._hd_status_label.setVisible(False)
        self._view_full_button.setText(text.PHOTO_DETAIL_HD_LOADING)
        self._view_full_button.setEnabled(False)
        QThreadPool.globalInstance().start(_PreviewDecodeJob(
            self._request_id,
            self._photo.path.raw_path,
            _PREVIEW_BOX,
            self.devicePixelRatioF(),  # UI 线程捕获 DPR 后传入 worker
            self._decoder,
            self,
        ))

    @Slot(int, QImage)
    def _on_preview_decoded(self, request_id: int, image: QImage) -> None:
        """替换预览（成功）/轻提示（失败）；过期或关闭后的结果直接丢弃。"""
        if request_id != self._request_id:
            self._dropped_requests += 1
            return
        if self._closed:
            self._dropped_requests += 1
            return
        if image.isNull():
            # 失败降级：保留缩略图 + 轻提示，可重试（新 request_id）。
            self._hd_status_label.setVisible(True)
            self._view_full_button.setText(text.PHOTO_DETAIL_VIEW_FULL)
            self._view_full_button.setEnabled(True)
            return
        self._preview.setText("")
        self._preview.setPixmap(QPixmap.fromImage(image))
        self._view_full_button.setVisible(False)
        self._hd_status_label.setVisible(False)

    def done(self, result: int) -> None:
        """任何结束路径（accept/reject/标题栏关闭）都先终止生命周期。"""
        self._closed = True
        super().done(result)
