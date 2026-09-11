"""Local filesystem implementation of the photo file scanner port."""

import os
import stat
from pathlib import Path

from photo_archiver.application.dtos import PhotoScanItem
from photo_archiver.application.ports import DEFAULT_SCAN_MAX_DEPTH, PhotoFileScanner


def _is_junction(entry: os.DirEntry) -> bool:
    """Return True when the entry is a Windows junction (mount-point reparse).

    junction 的 ``lstat`` 仍带目录位（``is_dir(follow_symlinks=False)`` 为
    True 且 ``is_symlink()`` 为 False），因此必须显式查 reparse tag 才能识别
    （Python 3.11 无 ``DirEntry.is_junction``，3.12 才加入）。
    """
    return (
        getattr(entry.stat(follow_symlinks=False), "st_reparse_tag", 0)
        == stat.IO_REPARSE_TAG_MOUNT_POINT
    )


class LocalPhotoFileScanner(PhotoFileScanner):
    """Discover photo files under a local directory.

    ADR-036 D5：遍历采用迭代式 ``os.scandir``（C 层实现）+ 已访问 realpath
    环检测 + 深度上限——**不跟随目录链接**。symlink 目录被
    ``is_dir(follow_symlinks=False)`` 排除；Windows junction 的 lstat 仍带
    目录位，需显式 reparse-tag 检查排除（见 ``_is_junction``）。visited
    realpath 集合与深度上限作为第二道保险。链接指向的文件仍作为候选收录，
    只是不深入链接目录。
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
                entries = list(os.scandir(current))
            except OSError:
                # Unreadable directory: silently skipped, matching the old
                # glob("**/*") behaviour of ignoring permission errors.
                if current == folder:
                    raise
                continue
            for entry in entries:
                path = Path(entry.path)
                if entry.is_dir(follow_symlinks=False) and not _is_junction(entry):
                    # 真实目录：递归时入栈。链接目录（symlink 被 lstat 排除、
                    # junction 被显式 reparse-tag 检查排除）不会走到这里。
                    if not recursive or depth >= max_depth:
                        continue
                    real = os.path.realpath(entry.path)
                    if real in visited:
                        continue
                    visited.add(real)
                    stack.append((path, depth + 1))
                    continue
                # 文件或链接文件：链接文件按候选收录（is_file() 语义与旧实现一致）。
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