"""LocalPhotoFileScanner traversal rewrite — ADR-036 D5 (Phase F F-1).

体检 F-11：旧实现 ``folder.glob("**/*")`` 会跟随目录链接（Windows junction
的 ``is_symlink()`` 为 False，pathlib 也不识别），含环的目录树会递归失控、
重复注册。新实现为迭代式 ``os.scandir`` + visited realpath 环检测 + 深度
上限。真实文件系统 tmp_path 驱动；symlink/junction 用例在平台不允许时优雅
跳过（与 test_archive_executor_symlink 同一处置模式）。
"""

import os
import sys
from pathlib import Path

import pytest

from photo_archiver.infrastructure.filesystem.local_photo_file_scanner import (
    LocalPhotoFileScanner,
)

_EXTENSIONS = (".jpg", ".png")


def _touch(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_bytes(b"fake-image-bytes")
    return path


def test_recursive_scan_finds_files_in_nested_directories(tmp_path: Path) -> None:
    _touch(tmp_path, "root.jpg")
    sub = tmp_path / "sub"
    sub.mkdir()
    _touch(sub, "deep.png")
    subsub = sub / "deeper"
    subsub.mkdir()
    _touch(subsub, "deepest.jpg")
    _touch(sub, "notes.txt")  # 扩展名过滤

    photos = LocalPhotoFileScanner().scan(
        tmp_path, recursive=True, supported_extensions=_EXTENSIONS
    )
    names = {photo.original_name for photo in photos}
    assert names == {"root.jpg", "deep.png", "deepest.jpg"}


def test_non_recursive_scan_lists_root_files_only(tmp_path: Path) -> None:
    _touch(tmp_path, "root.jpg")
    sub = tmp_path / "sub"
    sub.mkdir()
    _touch(sub, "deep.jpg")

    photos = LocalPhotoFileScanner().scan(
        tmp_path, recursive=False, supported_extensions=_EXTENSIONS
    )
    assert [photo.original_name for photo in photos] == ["root.jpg"]


def test_scan_extension_filter_is_case_insensitive(tmp_path: Path) -> None:
    _touch(tmp_path, "upper.JPG")
    _touch(tmp_path, "lower.jpg")
    photos = LocalPhotoFileScanner().scan(
        tmp_path, recursive=False, supported_extensions=_EXTENSIONS
    )
    assert {photo.original_name for photo in photos} == {"upper.JPG", "lower.jpg"}


def test_scan_keeps_lowercase_path_sort_order(tmp_path: Path) -> None:
    _touch(tmp_path, "B.jpg")
    _touch(tmp_path, "a.jpg")
    photos = LocalPhotoFileScanner().scan(
        tmp_path, recursive=False, supported_extensions=_EXTENSIONS
    )
    assert [photo.original_name for photo in photos] == ["a.jpg", "B.jpg"]


def test_scan_raises_on_missing_folder_and_on_file(tmp_path: Path) -> None:
    scanner = LocalPhotoFileScanner()
    with pytest.raises(FileNotFoundError):
        scanner.scan(tmp_path / "missing", recursive=True, supported_extensions=_EXTENSIONS)
    a_file = _touch(tmp_path, "file.jpg")
    with pytest.raises(NotADirectoryError):
        scanner.scan(a_file, recursive=True, supported_extensions=_EXTENSIONS)


def test_scan_depth_limit_stops_descent_beyond_max_depth(tmp_path: Path) -> None:
    """深度上限（ADR-036 D5 第二道保险）：max_depth=0 即只扫根层。"""
    deep = tmp_path / "l1" / "l2" / "l3"
    deep.mkdir(parents=True)
    _touch(deep, "deep.jpg")
    _touch(tmp_path, "root.jpg")

    photos = LocalPhotoFileScanner().scan(
        tmp_path, recursive=True, supported_extensions=_EXTENSIONS, max_depth=0
    )
    assert [photo.original_name for photo in photos] == ["root.jpg"]


def test_scan_does_not_descend_into_symlinked_directory(tmp_path: Path) -> None:
    """链接目录不深入（其内容不重复出现），链接文件仍收录。"""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    _touch(real_dir, "inside.jpg")
    _touch(tmp_path, "outside.jpg")
    link_file = tmp_path / "link_file.jpg"
    link_dir = tmp_path / "link_dir"
    try:
        link_file.symlink_to(real_dir / "inside.jpg")
        link_dir.symlink_to(real_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted on this platform/account")

    photos = LocalPhotoFileScanner().scan(
        tmp_path, recursive=True, supported_extensions=_EXTENSIONS
    )
    names = {photo.original_name for photo in photos}
    # 链接文件收录；链接目录不深入 → inside.jpg 不经 link_dir 重复出现。
    assert "link_file.jpg" in names
    assert all(photo.path.parent.name != "link_dir" for photo in photos)


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are a Windows concept")
def test_scan_does_not_follow_junction_loop(tmp_path: Path) -> None:
    """junction 环（指向祖先目录）：旧 glob 实现会递归失控，新实现直接截断。"""
    inner = tmp_path / "inner"
    inner.mkdir()
    _touch(inner, "inner.jpg")
    _touch(tmp_path, "outer.jpg")
    import _winapi

    loop = inner / "loop"  # inner/loop -> tmp_path（祖先）
    _winapi.CreateJunction(str(tmp_path), str(loop))

    photos = LocalPhotoFileScanner().scan(
        inner, recursive=True, supported_extensions=_EXTENSIONS
    )
    names = [photo.original_name for photo in photos]
    assert names == ["inner.jpg"]  # 无失控、无经 junction 的重复项


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are a Windows concept")
def test_scan_junction_contents_not_duplicated(tmp_path: Path) -> None:
    """junction 指向另一棵真实子树：不深入 → 该子树内容只出现一次。"""
    real = tmp_path / "real"
    real.mkdir()
    _touch(real, "real.jpg")
    other = tmp_path / "other"
    other.mkdir()
    _touch(other, "other.jpg")
    import _winapi

    junction = other / "real_link"
    _winapi.CreateJunction(str(real), str(junction))

    photos = LocalPhotoFileScanner().scan(
        tmp_path, recursive=True, supported_extensions=_EXTENSIONS
    )
    names = [photo.original_name for photo in photos]
    assert sorted(names) == ["other.jpg", "real.jpg"]  # real.jpg 不经 junction 重复


def test_scan_os_errors(tmp_path: Path) -> None:
    """子目录不可读时静默跳过（与旧 glob 行为一致），根目录不可读仍报错。"""
    sub = tmp_path / "locked"
    sub.mkdir()
    _touch(tmp_path, "ok.jpg")
    real_mode = sub.stat().st_mode
    os.chmod(sub, 0o000)
    try:
        photos = LocalPhotoFileScanner().scan(
            tmp_path, recursive=True, supported_extensions=_EXTENSIONS
        )
        assert [photo.original_name for photo in photos] == ["ok.jpg"]
    finally:
        os.chmod(sub, real_mode)
