"""Command for scanning a folder and registering discovered photos."""

from dataclasses import dataclass
from pathlib import Path

from photo_archiver.application.commands.scan_photo_folder import DEFAULT_SUPPORTED_PHOTO_EXTENSIONS
from photo_archiver.application.dtos import PhotoScanItem


@dataclass(frozen=True, slots=True)
class ScanAndRegisterPhotosCommand:
    """Request scanning a folder and persisting discovered photos."""

    folder_path: Path
    recursive: bool = True
    supported_extensions: tuple[str, ...] = DEFAULT_SUPPORTED_PHOTO_EXTENSIONS
    folder_display_name: str | None = None
    # ADR-041：主线程预枚举结果（LIMIT-006 规避）。携带时服务**跳过**目录
    # 枚举与全部路径 resolve（调用方保证 folder_path 已 resolve、条目路径
    # 已是真实绝对路径）；None = 旧路径（服务自行枚举，CLI 语义不变）。
    pre_enumerated_items: tuple[PhotoScanItem, ...] | None = None
