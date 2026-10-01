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

from PySide6.QtCore import (
    QObject,
    QSize,
    Qt,
    QRunnable,
    QThreadPool,
    Signal,
    Slot,
)
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


class _DecodeDispatcher(QObject):
    """解码结果分发器（应用级生命周期单例）。

    Worker 线程只触碰分发器（永不触碰对话框——对话框可能正被 GUI 线程
    销毁，跨线程 emit 会构成原生崩溃竞态）；分发器把结果连同对话框 key
    以队列连接投回 GUI 线程。对话框作为接收者销毁时 Qt 自动断连，队列
    中残留事件被安全丢弃。
    """

    decoded = Signal(int, int, QImage)  # (dialog_key, request_id, image)


_decode_dispatcher: _DecodeDispatcher | None = None


def _dispatcher() -> _DecodeDispatcher:
    """Lazy singleton——首次解码时 QApplication 已存在。"""
    global _decode_dispatcher
    if _decode_dispatcher is None:
        _decode_dispatcher = _DecodeDispatcher()
    return _decode_dispatcher


# 对话框 key：Qt Signal(int) 是 C++ 32 位 int——不能用 id(self)（64 位地址会
# OverflowError），用模块内单调计数器（仅在 GUI 线程分配，无需加锁）。
_decode_key_counter = 0


def _next_decode_key() -> int:
    global _decode_key_counter
    _decode_key_counter += 1
    return _decode_key_counter


class _PreviewDecodeJob(QRunnable):
    """后台受控解码原图（模级 QRunnable，复用 _ThumbnailJob 同构模式）。

    Worker 只做文件读取/解码/QImage，完成后经分发器投递（worker 不持有
    对话框引用——见 _DecodeDispatcher 的竞态说明）。DPR 在点击时于 UI
    线程捕获后传入，不在 worker 里调用 QWidget 方法。
    """

    def __init__(
        self,
        dialog_key: int,
        request_id: int,
        path: Path,
        box: QSize,
        dpr: float,
        decoder: Callable[[Path, QSize, float], QImage],
    ) -> None:
        super().__init__()
        self._dialog_key = dialog_key
        self._request_id = request_id
        self._path = path
        self._box = box
        self._dpr = dpr
        self._decoder = decoder

    def run(self) -> None:
        try:
            image = self._decoder(self._path, self._box, self._dpr)
        except Exception:  # noqa: BLE001 - 意外异常按失败降级，线程不携带异常退出
            image = QImage()
        # 分发器为应用级单例：从 worker 线程 emit 安全（跨线程队列投递）。
        _dispatcher().decoded.emit(self._dialog_key, self._request_id, image)


class PhotoDetailDialog(QDialog):
    """Show one photo's read-only details; double-click entry in the library."""

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
        # Worker 只触碰分发器（应用级单例，worker 上 emit 永不触碰对话框——
        # 消除对话框销毁跨线程竞态）；结果带 dialog_key 投回 GUI 线程，本
        # 对话框作为接收者销毁时 Qt 自动断连，残留队列事件被安全丢弃。
        self._decode_key = _next_decode_key()
        _dispatcher().decoded.connect(self._on_dispatcher_decode)
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

        # 元数据标签持有引用：replace_photo（审核预览上一张/下一张）可重绑。
        self._name_label = QLabel(self)
        self._path_label = QLabel(self)
        self._captured_label = QLabel(self)
        self._badge_label = QLabel(self)
        for label in (self._name_label, self._path_label,
                      self._captured_label, self._badge_label):
            layout.addWidget(label)
        layout.addStretch()
        self._apply_photo_details(photo, badge)
        if auto_load_hd:
            self._on_view_full_size_clicked()

    def _apply_photo_details(self, photo: Photo, badge: str | None) -> None:
        """(Re)fill the metadata labels for one photo (shared by navigation)."""
        name = photo.original_name or photo.path.raw_path
        self._name_label.setText(text.PHOTO_DETAIL_NAME.format(name=name))
        self._path_label.setText(text.PHOTO_DETAIL_PATH.format(path=photo.path.raw_path))
        if photo.captured_at is not None:
            captured = text.PHOTO_DETAIL_CAPTURED.format(
                time=photo.captured_at.strftime("%Y-%m-%d %H:%M"),
            )
        else:
            captured = text.PHOTO_DETAIL_CAPTURED_UNKNOWN
        self._captured_label.setText(captured)
        self._badge_label.setText(text.PHOTO_DETAIL_STATUS.format(
            badge=badge if badge else text.FILTER_STATUS_UNMATCHED,
        ))

    def replace_photo(self, photo: Photo, badge: str | None = None) -> None:
        """导航宿主 API（审核预览上一张/下一张）：重绑照片并重启受控解码。

        预览复位为"加载中"占位；在途的旧解码结果由 request_id 机制自动
        丢弃。【查看大图】按钮隐藏（导航模式下解码自动进行）。
        """
        self._photo = photo
        self._apply_photo_details(photo, badge)
        self._hd_status_label.setVisible(False)
        self._view_full_button.setVisible(False)
        self._preview.setText(text.PHOTO_DETAIL_HD_LOADING)
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
            self._decode_key,
            self._request_id,
            self._photo.path.raw_path,
            _PREVIEW_BOX,
            self.devicePixelRatioF(),  # UI 线程捕获 DPR 后传入 worker
            self._decoder,
        ))

    @Slot(int, int, QImage)
    def _on_dispatcher_decode(self, dialog_key: int, request_id: int, image: QImage) -> None:
        """分发器入口：过滤其他对话框的投递，其余语义同单队列契约。"""
        if dialog_key != self._decode_key:
            return
        self._on_preview_decoded(request_id, image)

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
