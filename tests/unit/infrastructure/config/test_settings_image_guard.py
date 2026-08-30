"""Settings tests for the image pixel guard (P2-002 fix).

The decompression-bomb guard must be configurable but never disableable:
non-positive values are rejected, the default matches Pillow's built-in
limit, and environment overrides propagate to ``AppSettings``.
"""

import pytest
from pydantic import ValidationError

from photo_archiver.infrastructure.config.settings import (
    DEFAULT_MAX_IMAGE_PIXELS,
    AppSettings,
)

# Pillow 11.x built-in default (0.25 * 2**28). The project constant must stay
# aligned with it so a fresh install keeps the historical guard strength.
PILLOW_DEFAULT_MAX_IMAGE_PIXELS = 89_478_485


def test_default_max_image_pixels_matches_pillow_guard() -> None:
    settings = AppSettings(_env_file=None)
    assert DEFAULT_MAX_IMAGE_PIXELS == PILLOW_DEFAULT_MAX_IMAGE_PIXELS
    assert settings.max_image_pixels == DEFAULT_MAX_IMAGE_PIXELS


def test_max_image_pixels_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_IMAGE_PIXELS", "1000000")
    settings = AppSettings(_env_file=None)
    assert settings.max_image_pixels == 1_000_000


@pytest.mark.parametrize("bad_value", ["0", "-1"])
def test_max_image_pixels_rejects_non_positive_values(
    monkeypatch: pytest.MonkeyPatch, bad_value: str
) -> None:
    """The guard can be tuned but never disabled through configuration."""
    monkeypatch.setenv("MAX_IMAGE_PIXELS", bad_value)
    with pytest.raises(ValidationError, match="never be disabled"):
        AppSettings(_env_file=None)
