"""Local filesystem implementation of the photo file scanner port.

LIMIT-006 D-3（2026-09-12）：macOS CI 的段错误栈定位到 ``os.scandir`` 的 C 层
枚举（QThreadPool worker 线程 + 主线程 Qt 事件循环并发时；旧 pathlib.glob
实现内部同样走 scandir——共同因子是 scandir 本身，故 D-5 的重写无效）。
本实现改用 ``os.listdir + os.lstat`` 完全绕开 scandir/DirEntry C 通道，
作为缓解实验。
"""

import os
import stat as stat_module
from pathlib import Path

from photo_archiver.application.dtos import PhotoScanItem
from photo_archiver.application.ports import DEFAULT_SCAN_MAX_DEPTH, PhotoFileScanner

# IO_REPARSE_TAG_MOUNT_POINT（ntioapi.h，稳定文档值）。`stat` 模块仅在
# Windows 上导出该常量——硬编码以保持模块在 Linux/macOS 可导入、可静态检查
# （CI 的 mypy 在三平台原生运行；本地 Windows 开发曾掩盖此差异）。
_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003


def _is_junction_path(path: Path) -> bool:
    """Return True when ``path`` is a Windows junction (mount-point reparse).

    junction 的 ``lstat`` 仍带目录位（``Path.is_dir()`` 为 True 且
    ``is_symlink()`` 为 False），必须显式查 reparse tag（Python 3.11 无
    ``Path.is_junction``，3.12 才加入）。非 Windows 平台 ``st_reparse_tag``
    属性不存在，getattr 回退 0 恒为 False。
    """
    return (
        getattr(os.lstat(path), "st_reparse_tag", 0)
        == _IO_REPARSE_TAG_MOUNT_POINT
    )


class LocalPhotoFileScanner(PhotoFileScanner):
    """Discover photo files under a local directory.

    ADR-036 D5：迭代式遍历 + 已访问 realpath 环检测 + 深度上限——**不跟随
    目录链接**。枚举用 ``os.listdir``（LIMIT-006 缓解，见模块 docstring），
    条目类型判定用 ``os.lstat``：symlink 目录的 lstat 为 S_ISLNK 非目录、
    Windows junction 需显式 reparse-tag 检查排除。visited realpath 集合与
    深度上限作为第二道保险。链接指向的文件仍作为候选收录，只是不深入
    链接目录。
    """

    def scan(
        self,
        folder_path: Path,
        *,
        recursive: bool,
        supported_extensions: tuple[str, ...],
        max_depth: int = DEFAULT_SCAN_MAX_DEPTH,
    ) -> list[PhotoScanItem]:
        """Return photo candidates matching the supported extensions.

        Args:
            folder_path: Root directory to scan (must exist and be a directory).
            recursive: Descend into subdirectories when True.
            supported_extensions: Case-insensitive extension allow-list.
            max_depth: Maximum descent depth below the root (0 = root only;
                never follows directory links regardless of the value).
        """
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Photo folder does not exist: {folder}")
        if not folder.is_dir():
            raise NotADirectoryError(f"Photo folder is not a directory: {folder}")

        normalized_extensions = self._normalize_extensions(supported_extensions)
        photos: list[PhotoScanItem] = []
        visited: set[str] = {os.path.realpath(folder)}
        # (directory, depth) stack — depth counts levels below the root.
        stack: list[tuple[Path, int]] = [(folder, 0)]
        while stack:
            current, depth = stack.pop()
            try:
                names = os.listdir(current)
            except OSError:
                # Unreadable directory: silently skipped, matching the old
                # glob("**/*") behaviour of ignoring permission errors.
                if current == folder:
                    raise
                continue
            names.sort()
            for name in names:
                path = current / name
                try:
                    entry_stat = os.lstat(path)
                except OSError:
                    continue  # 竞态消失的条目按跳过处理（与旧 is_file 容错一致）
                if stat_module.S_ISDIR(entry_stat.st_mode) and not _is_junction_path(path):
                    # 真实目录：递归时入栈。链接目录（symlink 的 lstat 为
                    # S_ISLNK 非 S_ISDIR、junction 被显式 reparse-tag 检查
                    # 排除）不会走到这里。
                    if not recursive or depth >= max_depth:
                        continue
                    real = os.path.realpath(path)
                    if real in visited:
                        continue
                    visited.add(real)
                    stack.append((path, depth + 1))
                    continue
                # 文件或链接文件：链接文件按候选收录（与旧实现 is_file() 语义一致）。
                if path.suffix.lower() in normalized_extensions:
                    photos.append(PhotoScanItem(path=path, original_name=path.name))
        return sorted(photos, key=lambda item: str(item.path).lower())

    @staticmethod
    def _normalize_extensions(extensions: tuple[str, ...]) -> set[str]:
        """Normalize extensions to lowercase values prefixed with a dot."""
        normalized = set()
        for extension in extensions:
            value = extension.strip().lower()
            if not value:
                continue
            normalized.add(value if value.startswith(".") else f".{value}")
        return normalized