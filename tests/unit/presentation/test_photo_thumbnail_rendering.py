"""P0-2 thumbnail rendering chain tests.

Proves the full real production chain — image on disk → real
ThumbnailCache/PillowThumbnailGenerator (same classes and 256px contract as
the app/ui_assembly wiring) → real PhotoListController async load → real
PhotoListModel → real PhotoThumbnailDelegate painting actual pixels inside
the real MainWindow.

No pipeline component is mocked. The source image is program-generated
(solid-color lossless PNG) so painted pixels are exactly assertable; no
binary test assets are committed.
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")
pytest.importorskip("PIL")

from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QStyleOptionViewItem

from PIL import Image

# Import the app package first so its __init__ finishes initializing before
# MainWindow pulls app.context.ApplicationContext during its own import
# (same ordering note as test_main_window_smoke.py).
from photo_archiver.app import bootstrap_application
from photo_archiver.domain import Photo, PhotoPath, PhotoPathBase
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.infrastructure.image.pillow_thumbnail_generator import (
    PillowThumbnailGenerator,
)
from photo_archiver.infrastructure.image.thumbnail_cache import ThumbnailCache
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.presentation.views.photo_list_delegate import PhotoThumbnailDelegate
from photo_archiver.presentation.views.photo_list_model import THUMBNAIL_ROLE

# Distinct solid color; lossless PNG keeps painted pixels exactly assertable.
_SOURCE_COLOR = (196, 42, 88)
_DEFAULT_THUMBNAIL_SIZE = 256  # same contract as PhotoListController


def _write_source_image(tmp_path: Path) -> Path:
    """Create a real solid-color PNG on disk (program-generated fixture)."""
    source = tmp_path / "photos" / "sample.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 300), _SOURCE_COLOR).save(source)
    return source


def test_thumbnail_pipeline_generates_and_caches(tmp_path: Path) -> None:
    """Real generator/cache produce a valid, correctly-sized cached file."""
    source = _write_source_image(tmp_path)
    cache = ThumbnailCache(tmp_path / "thumbnails")  # same wiring as ui_assembly
    generator = PillowThumbnailGenerator(cache, max_image_pixels=89478485)

    thumbnail = generator.generate(source, _DEFAULT_THUMBNAIL_SIZE)
    assert thumbnail.exists()
    assert thumbnail.stat().st_size > 0

    with Image.open(thumbnail) as image:
        assert max(image.size) <= _DEFAULT_THUMBNAIL_SIZE
        center = (image.width // 2, image.height // 2)
        assert image.getpixel(center) == _SOURCE_COLOR

    # Cache hit: the second generate returns the same file without re-render.
    first_mtime = thumbnail.stat().st_mtime_ns
    assert generator.generate(source, _DEFAULT_THUMBNAIL_SIZE) == thumbnail
    assert thumbnail.stat().st_mtime_ns == first_mtime


def test_photo_list_renders_real_thumbnail(qtbot, tmp_path: Path) -> None:
    """The real MainWindow paints the real thumbnail for a real photo row."""
    source = _write_source_image(tmp_path)
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'thumb.db'}",
        output_root=tmp_path / "out",
    )
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)

    # Real production persistence path: the same photos.add() the scan
    # service uses, pointing at the real image on disk.
    photo = Photo(
        path=PhotoPath(source, base=PhotoPathBase.ABSOLUTE),
        original_name="sample.png",
    )
    context.repositories.photos.add(photo)

    window = MainWindow(context)
    qtbot.addWidget(window)
    window.show()

    model = window._photo_list_model
    window._refresh_photo_list()
    assert model.rowCount() == 1

    index = model.index(0, 0)
    # The real async pipeline (controller → QThreadPool job → generate →
    # queued signal → set_thumbnail) must surface a resolvable path.
    qtbot.waitUntil(lambda: isinstance(index.data(THUMBNAIL_ROLE), Path), timeout=15000)
    thumbnail_path = index.data(THUMBNAIL_ROLE)
    assert isinstance(thumbnail_path, Path)
    assert thumbnail_path.exists()
    assert not QPixmap(str(thumbnail_path)).isNull()

    # The delegate is installed on the real view.
    delegate = window._photo_list.itemDelegate()
    assert isinstance(delegate, PhotoThumbnailDelegate)

    # Rendered-pixels proof: paint the delegate and find the source color.
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 280, 320)
    image = QImage(option.rect.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    delegate.paint(painter, option, index)
    painter.end()
    assert image.pixelColor(option.rect.center()) == QColor(*_SOURCE_COLOR)

    # Whole-widget rendering proof: the real view (shown in the real window)
    # draws the thumbnail onto the screen pixmap.
    grabbed = window._photo_list.grab().toImage()
    sampled = [
        grabbed.pixelColor(x, y) == QColor(*_SOURCE_COLOR)
        for x in range(0, grabbed.width(), 5)
        for y in range(0, min(grabbed.height(), _DEFAULT_THUMBNAIL_SIZE + 20), 5)
    ]
    assert any(sampled)
    assert window.isVisible()

    # Second access hits the on-disk cache and resolves to the same file.
    cache_hits: list[Path] = []
    window._photo_list_controller.thumbnail_loaded.connect(
        lambda pid, path: cache_hits.append(path)
    )
    window._photo_list_controller.load_thumbnail(photo.id, source)
    assert cache_hits == [thumbnail_path]
