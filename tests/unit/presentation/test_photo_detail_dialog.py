"""Photo detail HD preview tests (方案 §13 T1–T11 + EXIF 裁剪修复 T12/T13).

Two layers, mirroring the plan's injectable boundary:

- Unit level: the real ``_decode_preview`` directly (T3 分辨率/T4 宽高比/
  T5 EXIF/T8 中文路径/T12 Owner 场景回归/T13 非旋转回归) — deterministic,
  no threads.
- Dialog level: PhotoDetailDialog with an injected fake decoder
  (T1/T2/T6/T7/T9/T10/T11) — Event-gated, zero sleep (方案 §8 纪律).

The real decoder is used at dialog level only where the failure path
itself is the subject (T6 原图不存在 → 真实 reader 错误路径).
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")
pytest.importorskip("PIL")

import threading
from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtGui import QColor, QImage

from PIL import Image

from photo_archiver.domain import Photo, PhotoPath, PhotoPathBase
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.photo_detail_dialog import (
    _PREVIEW_BOX,
    PhotoDetailDialog,
    _decode_preview,
)


def _write_thumbnail(tmp_path: Path) -> Path:
    """Real small cached thumbnail (200×150) for the immediate placeholder."""
    thumb = tmp_path / "thumb" / "sample.png"
    thumb.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 150), (30, 30, 30)).save(thumb)
    return thumb


def _photo(tmp_path: Path, name: str = "LEI00874.JPG", exists: bool = True) -> Photo:
    original = tmp_path / name
    if exists:
        Image.new("RGB", (1600, 1200), (196, 42, 88)).save(original)
    return Photo(
        path=PhotoPath(original, base=PhotoPathBase.ABSOLUTE),
        original_name=name,
    )


def _solid_qimage(width: int, height: int, rgb: tuple[int, int, int]) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(*rgb))
    return image


def _fake_decoder(images: list[QImage]):
    """Decoder stub recording call threads; returns images in call order."""
    calls: list[QThread] = []

    def decoder(path, box, dpr):  # noqa: ANN001 - 测试桩签名与 _decode_preview 对齐
        calls.append(QThread.currentThread())
        return images[min(len(calls), len(images)) - 1]

    decoder.calls = calls  # type: ignore[attr-defined]
    return decoder


def _make_dialog(qtbot, photo: Photo, thumb: Path | None, decoder) -> PhotoDetailDialog:
    dialog = PhotoDetailDialog(
        photo, badge=None, thumbnail_path=thumb, decoder=decoder,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def _wait_pixmap(qtbot, dialog: PhotoDetailDialog, width: int) -> None:
    qtbot.waitUntil(
        lambda: dialog._preview.pixmap() is not None
        and not dialog._preview.pixmap().isNull()
        and dialog._preview.pixmap().width() == width,
        timeout=5000,
    )


# ---- T1/T2：默认只读缩略图，点击才读原图 ----


def test_t1_default_open_shows_thumbnail_without_original_io(qtbot, tmp_path) -> None:
    decoder = _fake_decoder([_solid_qimage(300, 200, (10, 200, 30))])
    dialog = _make_dialog(
        qtbot, _photo(tmp_path), _write_thumbnail(tmp_path), decoder,
    )
    assert decoder.calls == []  # 打开详情不产生原图 IO
    pixmap = dialog._preview.pixmap()
    assert pixmap is not None and not pixmap.isNull()
    assert pixmap.width() == 200  # 缩略图自然尺寸居中（不额外放大）
    assert dialog._view_full_button.isVisible()
    assert dialog._view_full_button.text() == text.PHOTO_DETAIL_VIEW_FULL


def test_t2_click_starts_decode_and_replaces_thumbnail(qtbot, tmp_path) -> None:
    decoder = _fake_decoder([_solid_qimage(300, 200, (10, 200, 30))])
    dialog = _make_dialog(
        qtbot, _photo(tmp_path), _write_thumbnail(tmp_path), decoder,
    )
    dialog._view_full_button.click()
    # worker 拾取任务是异步的——waitUntil 等待（不 sleep、不做即时竞态断言）
    qtbot.waitUntil(lambda: len(decoder.calls) == 1, timeout=5000)
    _wait_pixmap(qtbot, dialog, 300)  # 高清结果替换缩略图
    assert not dialog._view_full_button.isVisible()  # 成功后隐藏（钉死项）
    assert not dialog._hd_status_label.isVisible()


def test_t14_auto_load_hd_starts_decode_on_open(qtbot, tmp_path) -> None:
    """auto_load_hd=True（审核双击场景）：打开即自动解码，无需点击按钮。"""
    decoder = _fake_decoder([_solid_qimage(300, 200, (10, 200, 30))])
    dialog = PhotoDetailDialog(
        _photo(tmp_path),
        badge=None,
        thumbnail_path=_write_thumbnail(tmp_path),
        decoder=decoder,
        auto_load_hd=True,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: len(decoder.calls) == 1, timeout=5000)
    _wait_pixmap(qtbot, dialog, 300)
    assert not dialog._view_full_button.isVisible()  # 成功后隐藏


def test_t15_default_open_still_defers_original_io(qtbot, tmp_path) -> None:
    """默认 auto_load_hd=False：打开详情零原图 IO 的既有契约不回归。"""
    decoder = _fake_decoder([_solid_qimage(300, 200, (10, 200, 30))])
    dialog = PhotoDetailDialog(
        _photo(tmp_path),
        badge=None,
        thumbnail_path=_write_thumbnail(tmp_path),
        decoder=decoder,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    assert decoder.calls == []  # 构造同步完成，未提交任何解码任务
    assert dialog._view_full_button.isVisible()


# ---- T3/T4/T5/T8：真实解码器单元级契约 ----


def test_t3_hd_resolution_bounded_and_above_thumbnail(tmp_path) -> None:
    source = tmp_path / "big.jpg"
    Image.new("RGB", (1600, 1200), (5, 5, 5)).save(source)
    for dpr in (1.0, 2.0):
        image = _decode_preview(source, _PREVIEW_BOX, dpr)
        assert not image.isNull()
        max_w = round(_PREVIEW_BOX.width() * dpr)
        max_h = round(_PREVIEW_BOX.height() * dpr)
        assert image.width() <= max_w and image.height() <= max_h
        assert image.width() > 256 and image.height() > 256  # 非 256px 放大


@pytest.mark.parametrize("size", [(1600, 1200), (1200, 1600), (1500, 1000)])
def test_t4_aspect_ratio_preserved(tmp_path: Path, size: tuple[int, int]) -> None:
    source = tmp_path / f"aspect_{size[0]}x{size[1]}.jpg"
    Image.new("RGB", size, (7, 7, 7)).save(source)
    image = _decode_preview(source, _PREVIEW_BOX, 1.0)
    assert not image.isNull()
    expected = size[0] / size[1]
    actual = image.width() / image.height()
    assert abs(actual - expected) < 0.02  # 无拉伸变形


def test_t5_exif_orientation_applied(tmp_path: Path) -> None:
    """横传感数据 + Orientation=6 → 高清预览竖直显示（不与缩略图比对）。

    raw 400×200 → oriented 200×400；aspect-fit 会放大到 240×480，被
    "小图不放大解码" clamp 回 oriented 尺寸（§5.1 物理空间推导）。
    """
    source = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (400, 200), (9, 9, 9))
    exif = Image.Exif()
    exif[274] = 6  # Orientation: rotate 90° CW for display
    image.save(source, exif=exif)
    decoded = _decode_preview(source, _PREVIEW_BOX, 1.0)
    assert not decoded.isNull()
    assert (decoded.width(), decoded.height()) == (200, 400)  # 转置后（clamp）
    assert decoded.width() < decoded.height()  # 竖直向上
    # 显示逻辑尺寸 ≤ 包围盒（本轮 EXIF 裁剪 bug 的逃逸盲区，必须钉死）
    assert decoded.width() / decoded.devicePixelRatio() <= _PREVIEW_BOX.width()
    assert decoded.height() / decoded.devicePixelRatio() <= _PREVIEW_BOX.height()


def test_t12_owner_scenario_rotated_photo_fits_bounding_box(tmp_path: Path) -> None:
    """T12（LEI00670 场景回归）：raw 800×600 横传感 + Orientation=8
    （Rotate270，与真实照片同型）→ 高清预览必须竖直、完整落入包围盒。

    修复前：fit 从原始横幅尺寸推导 → 显示逻辑 640×959 超高 → 居中裁剪
    （顶部人头/底部花篮被切）。修复后：oriented 600×800 → 物理盒 800×600
    fit → 450×600 → 显示逻辑 360×480（dpr 1.25）。
    """
    source = tmp_path / "rotated_big.jpg"
    image = Image.new("RGB", (800, 600), (11, 22, 33))
    exif = Image.Exif()
    exif[274] = 8  # Orientation: rotate 270° CW for display（LEI00670 同型）
    image.save(source, exif=exif)
    decoded = _decode_preview(source, _PREVIEW_BOX, 1.25)
    assert not decoded.isNull()
    assert (decoded.width(), decoded.height()) == (450, 600)
    assert decoded.devicePixelRatio() == 1.25
    displayed_w = decoded.width() / decoded.devicePixelRatio()
    displayed_h = decoded.height() / decoded.devicePixelRatio()
    assert (displayed_w, displayed_h) == (360, 480)  # 完整显示，无裁剪
    assert displayed_w <= _PREVIEW_BOX.width() and displayed_h <= _PREVIEW_BOX.height()
    assert decoded.width() < decoded.height()  # 竖直方向正确


@pytest.mark.parametrize("size", [(1600, 1200), (1200, 1600)])
def test_t13_non_rotated_images_unaffected(tmp_path: Path, size: tuple[int, int]) -> None:
    """T13：无 EXIF 图源在修复前后零行为变化（防轴交换逻辑误伤）。"""
    source = tmp_path / f"plain_{size[0]}x{size[1]}.jpg"
    Image.new("RGB", size, (12, 12, 12)).save(source)
    decoded = _decode_preview(source, _PREVIEW_BOX, 1.25)
    assert not decoded.isNull()
    assert decoded.devicePixelRatio() == 1.25
    displayed_w = decoded.width() / decoded.devicePixelRatio()
    displayed_h = decoded.height() / decoded.devicePixelRatio()
    assert displayed_w <= _PREVIEW_BOX.width()
    assert displayed_h <= _PREVIEW_BOX.height()
    expected = size[0] / size[1]
    actual = displayed_w / displayed_h
    assert abs(actual - expected) < 0.02  # 宽高比保持


def test_t8_chinese_path_decoded(tmp_path: Path) -> None:
    source = tmp_path / "中文目录" / "照片 一号.jpg"
    source.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), (1, 2, 3)).save(source)
    decoded = _decode_preview(source, _PREVIEW_BOX, 1.0)
    assert not decoded.isNull()
    assert decoded.width() == 640 and decoded.height() == 480


# ---- T6/T7：降级链 ----


def test_t6_missing_original_keeps_thumbnail(qtbot, tmp_path) -> None:
    dialog = _make_dialog(
        qtbot, _photo(tmp_path, exists=False), _write_thumbnail(tmp_path), None,
    )
    assert not dialog._hd_status_label.isVisible()
    dialog._view_full_button.click()
    qtbot.waitUntil(lambda: dialog._hd_status_label.isVisible(), timeout=5000)
    pixmap = dialog._preview.pixmap()
    assert pixmap is not None and not pixmap.isNull()  # 缩略图未被破坏
    assert pixmap.width() == 200
    assert dialog._view_full_button.isEnabled()  # 失败后可重试
    assert dialog._view_full_button.text() == text.PHOTO_DETAIL_VIEW_FULL


def test_t7_no_thumbnail_no_original_pending(qtbot, tmp_path) -> None:
    dialog = _make_dialog(qtbot, _photo(tmp_path, exists=False), None, None)
    assert dialog._preview.text() == text.PHOTO_DETAIL_THUMB_PENDING
    assert not dialog._view_full_button.isVisible()


# ---- T9/T10/T11：竞态防护与线程纪律 ----


def test_t9_close_race_drops_result_without_crash(qtbot, tmp_path) -> None:
    gate = threading.Event()
    release = threading.Event()

    def decoder(path, box, dpr):  # noqa: ANN001
        gate.set()
        release.wait(timeout=5)
        return _solid_qimage(300, 200, (10, 200, 30))

    dialog = _make_dialog(
        qtbot, _photo(tmp_path), _write_thumbnail(tmp_path), decoder,
    )
    dialog._view_full_button.click()
    assert gate.wait(timeout=5)  # worker 已进入解码（零 sleep 同步）
    dialog.close()  # 关闭竞态：worker 尚未返回
    release.set()
    qtbot.waitUntil(lambda: dialog._dropped_requests == 1, timeout=5000)
    pixmap = dialog._preview.pixmap()
    assert pixmap is not None and pixmap.width() == 200  # 预览保持缩略图


def test_t10_stale_request_result_discarded(qtbot, tmp_path) -> None:
    gate = threading.Event()
    release = threading.Event()
    calls: list[QThread] = []

    def decoder(path, box, dpr):  # noqa: ANN001
        calls.append(QThread.currentThread())
        if len(calls) == 1:
            gate.set()
            release.wait(timeout=5)
            return _solid_qimage(100, 100, (255, 0, 0))  # 过期请求的结果
        return _solid_qimage(200, 200, (0, 200, 0))  # 新请求的结果

    dialog = _make_dialog(
        qtbot, _photo(tmp_path), _write_thumbnail(tmp_path), decoder,
    )
    dialog._on_view_full_size_clicked()  # request 1（方法级直调，钉死项 3）
    assert gate.wait(timeout=5)
    dialog._on_view_full_size_clicked()  # request 2 立即提交
    _wait_pixmap(qtbot, dialog, 200)  # 新结果先返回并显示
    release.set()  # 旧结果后到
    qtbot.waitUntil(lambda: dialog._dropped_requests == 1, timeout=5000)
    assert dialog._preview.pixmap().width() == 200  # 未被旧结果覆盖


def test_t11_decode_runs_off_gui_thread(qtbot, tmp_path) -> None:
    decoder = _fake_decoder([_solid_qimage(50, 50, (0, 0, 0))])
    dialog = _make_dialog(
        qtbot, _photo(tmp_path), _write_thumbnail(tmp_path), decoder,
    )
    dialog._view_full_button.click()
    qtbot.waitUntil(lambda: len(decoder.calls) == 1, timeout=5000)
    qtbot.waitUntil(
        lambda: dialog._preview.pixmap() is not None
        and dialog._preview.pixmap().width() == 50,
        timeout=5000,
    )
    assert decoder.calls[0] is not QThread.currentThread()  # 非 GUI 线程


# ---- P12：导航占位——replace_photo 已知缩略图先上屏，再启动高清解码 ----


def test_p12_replace_photo_shows_known_thumbnail_before_hd(qtbot, tmp_path) -> None:
    """导航宿主传入已知缩略图：先显示缩略图占位（同步），高清到达后覆盖。"""
    decoder = _fake_decoder([_solid_qimage(300, 200, (10, 200, 30))])
    dialog = _make_dialog(
        qtbot, _photo(tmp_path), _write_thumbnail(tmp_path), decoder,
    )
    next_thumb = tmp_path / "thumb" / "next.png"
    next_thumb.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (120, 90), (60, 60, 60)).save(next_thumb)

    dialog.replace_photo(_photo(tmp_path, "NEXT0001.JPG"), thumbnail_path=next_thumb)

    # replace_photo 返回时事件循环尚未运行（解码结果必经队列连接投回），
    # 此刻预览必然还是缩略图占位——时序断言不依赖 sleep。
    pixmap = dialog._preview.pixmap()
    assert pixmap is not None and not pixmap.isNull()
    assert (pixmap.width(), pixmap.height()) == (120, 90)
    assert not dialog._preview.text()  # 不再显示"加载中"文本
    qtbot.waitUntil(lambda: len(decoder.calls) == 1, timeout=5000)
    _wait_pixmap(qtbot, dialog, 300)  # 高清解码结果覆盖缩略图占位


def test_p12_replace_photo_without_thumbnail_keeps_loading_placeholder(
    qtbot, tmp_path,
) -> None:
    """未知缩略图（不传参数）：维持"加载中"占位——既有导航契约不回归。"""
    decoder = _fake_decoder([_solid_qimage(300, 200, (10, 200, 30))])
    dialog = _make_dialog(
        qtbot, _photo(tmp_path), None, decoder,
    )
    dialog.replace_photo(_photo(tmp_path, "NEXT0002.JPG"))
    assert dialog._preview.pixmap() is None or dialog._preview.pixmap().isNull()
    assert dialog._preview.text() == text.PHOTO_DETAIL_HD_LOADING
    qtbot.waitUntil(lambda: len(decoder.calls) == 1, timeout=5000)
    _wait_pixmap(qtbot, dialog, 300)
