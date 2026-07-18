"""UI controller assembly for PhotoArchiver presentation layer.

Wires ReviewController and PhotoListController from already-assembled services
and repositories + Step 7 ThumbnailCache / PillowThumbnailGenerator. Kept in
its own module so app/services.py stays free of PySide6 imports (controllers
depend on Qt).
"""

from dataclasses import dataclass
from pathlib import Path

from photo_archiver.app.repositories import ApplicationRepositories
from photo_archiver.app.services import ApplicationServices
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.infrastructure.image import PillowThumbnailGenerator, ThumbnailCache
from photo_archiver.presentation.controllers import PhotoListController, ReviewController


@dataclass(frozen=True, slots=True)
class UIControllers:
    """UI-facing controllers assembled for runtime."""

    review: ReviewController
    photo_list: PhotoListController


def build_ui_controllers(
    services: ApplicationServices,
    repositories: ApplicationRepositories,
    settings: AppSettings,
) -> UIControllers:
    """Build ReviewController and PhotoListController from runtime parts.

    ThumbnailCache root is settings.output_root / "thumbnails" — falls back
    to a system temp dir when output_root is None so the UI still works in
    minimal test contexts without a configured output root.
    """
    thumbnail_root = (
        settings.output_root / "thumbnails"
        if settings.output_root is not None
        else Path.home() / ".photo_archiver" / "thumbnails"
    )
    thumbnail_cache = ThumbnailCache(thumbnail_root)
    thumbnail_generator = PillowThumbnailGenerator(thumbnail_cache)

    return UIControllers(
        review=ReviewController(
            services.review_recognition,  # type: ignore[arg-type]
            repositories.recognition,
        ),
        photo_list=PhotoListController(
            repositories.photos,
            thumbnail_cache,
            thumbnail_generator,
        ),
    )
