"""Read-only photo detail dialog (Batch 4; HD preview 2026-09-30).

Larger preview plus the archival context of one photo — original name,
path, capture time and the recognition/archival badge. Data comes from
the already-loaded Photo entity and the cached thumbnail file.

预览数据源分两档（2026-09-30 高清预览方案）：

- 打开即显示缓存缩略图（≤256px 源，自然尺寸居中于固定包围盒，不额外放大）；
- 用户点击【查看大图】后，经 QThreadPool 异步受控解码原图
  （``photo.path.raw_path``：QImageReader + setAutoTransform + setScaledSize，
  尺寸推导基于 EXIF 转置后尺寸、全程物理像素空间，小图源 clamp 到原始
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
from PySide6.QtGui import QImage, QImageIOHandler, QImageReader, QPixmap
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
# 对话框尺寸不随照片长宽比跳变；解码目标 = 包围盒 × devicePixelRatio（物理空间）。
_PREVIEW_BOX = QSize(640, 480)

# 含 90° 旋转分量的变换需要交换宽高（Owner 方案 §4.2：分量掩码判定，禁止
# 固定枚举值清单）。PySide6 6.11 的 Transformation 位标志仅三个基础位——
# Mirror=1 / Flip=2 / Rotate90=4；Rotate180(3)、FlipAndRotate90(6)、
# MirrorAndRotate90(5)、Rotate270(7) 均为含 Rotate90 位的组合别名，掩码
# 判定天然覆盖 EXIF Orientation 5/6/7/8 全部转置场景（全 8 值探针实证）。
_ROTATE_90_FLAG = QImageIOHandler.Transformation.TransformationRotate90


def _decode_preview(path: Path, box: QSize, dpr: float) -> QImage:
    """受控解码原图到预览物理尺寸（可注入测试边界）。

    尺寸推导全程在物理像素空间完成（§5.1）：
    ① raw = reader.size() —— 原始存储尺寸，**不含** EXIF 转置（探针实证）；
    ② transformation 含 Rotate90 位 → oriented 交换宽高（EXIF 转置后尺寸）；
    ③ target = oriented aspect-fit (box × dpr)，clamp 到 oriented（小图不放大解码）；
    ④ setScaledSize 使用**原始存储坐标空间**（探针实证）→ 转置场景把 target
       轴交换回去；
    ⑤ read() 返回转置后图 → ``setDevicePixelRatio(dpr)`` 归位，显示逻辑尺寸
       = target/dpr ≤ 包围盒。
    原图不可读（缺失/不支持/损坏）时返回 null QImage，调用方降级到缩略图。
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    raw = reader.size()
    if raw.isValid() and not raw.isEmpty():
        transposed = bool(reader.transformation() & _ROTATE_90_FLAG)
        oriented = QSize(raw.height(), raw.width()) if transposed else QSize(raw)
        physical_box = QSize(round(box.width() * dpr), round(box.height() * dpr))
        target = oriented.scaled(physical_box, Qt.AspectRatioMode.KeepAspectRatio)
        if target.width() > oriented.width() or target.height() > oriented.height():
            target = QSize(oriented)
        reader.setScaledSize(
            QSize(target.height(), target.width()) if transposed else QSize(target)
        )
    image = reader.read()
    if image.isNull():
        return QImage()
    if not (raw.isValid() and not raw.isEmpty()):
        # 元数据不可得的罕见格式：完整解码后内存内受控缩放兜底——同样 DPR 归位，
        # 否则 DPR>1 屏幕上按物理像素显示会超出逻辑包围盒（同类溢出，审查 H3）。
        physical_box = QSize(round(box.width() * dpr), round(box.height() * dpr))
        if (
            image.width() > physical_box.width()
            or image.height() > physical_box.height()
        ):
            image = image.scaled(
                physical_box,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    image.setDevicePixelRatio(dpr)
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
        auto_load_hd: bool = False,
    ) -> None:
        """Compose the preview and metadata rows from already-loaded data.

        ``decoder`` 仅测试注入（§8 可替换边界）；生产恒为真实
        :func:`_decode_preview`。``auto_load_hd``：打开即自动启动高清解码
        （审核中心双击场景——审片人需要直出高清，无需再点【查看大图】）；
        默认 False 保持"打开详情零原图 IO"契约。
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
        if auto_load_hd:
            self._on_view_full_size_clicked()

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
