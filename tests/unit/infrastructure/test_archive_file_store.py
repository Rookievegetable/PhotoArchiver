"""Port contract tests for the AUD-010 infrastructure adapters.

覆盖两个新端口的**关键成功/失败语义**（真实文件系统，无 mock）：

- ``FilesystemArchiveFileStore``：containment 三形态（词法越界 / 符号链接逃逸 /
  叶级符号链接拒绝）、原子复制（.part 落位 + mtime 保留 + 失败无残留 +
  目标"存在即完整"）、确定性兄弟协商。
- ``CsvFailureListWriter``：确定性重复写入（逐字节一致）、UTF-8-BOM。
"""

import os
from pathlib import Path

import pytest

from photo_archiver.infrastructure.exporters.failure_list_writer import CsvFailureListWriter
from photo_archiver.infrastructure.filesystem.archive_file_store import (
    FilesystemArchiveFileStore,
)


@pytest.fixture
def store() -> FilesystemArchiveFileStore:
    return FilesystemArchiveFileStore()


def test_containment_accepts_target_inside_root(store, tmp_path: Path) -> None:
    target = tmp_path / "Alice" / "2026-01-01" / "x.jpg"
    assert store.verify_target_containment(tmp_path, target) is None


def test_containment_rejects_lexical_escape(store, tmp_path: Path) -> None:
    outside = tmp_path.parent / "evil.jpg"
    error = store.verify_target_containment(tmp_path, outside)
    assert error is not None and "escapes archive_root" in error


def test_containment_rejects_symlinked_directory_escape(store, tmp_path: Path) -> None:
    outside_dir = tmp_path.parent / f"outside-{tmp_path.name}"
    outside_dir.mkdir(exist_ok=True)
    link_root = tmp_path / "linked"
    try:
        link_root.symlink_to(outside_dir, target_is_directory=True)
    except OSError:  # pragma: no cover - Windows 需开发者模式
        pytest.skip("symlink creation unavailable")
    target = link_root / "evil.jpg"
    error = store.verify_target_containment(tmp_path, target)
    assert error is not None and "filesystem links" in error


def test_containment_rejects_leaf_symlink(store, tmp_path: Path) -> None:
    target = tmp_path / "x.jpg"
    try:
        target.symlink_to(tmp_path / "real.jpg")
    except OSError:  # pragma: no cover
        pytest.skip("symlink creation unavailable")
    error = store.verify_target_containment(tmp_path, target)
    assert error is not None and "is a symlink" in error


def test_copy_atomically_preserves_mtime_and_leaves_no_part(store, tmp_path: Path) -> None:
    source = tmp_path / "src.jpg"
    source.write_bytes(b"content")
    stamp = 1_700_000_000
    os.utime(source, (stamp, stamp))
    target = tmp_path / "out" / "dst.jpg"
    store.ensure_parent_directory(target)

    store.copy_atomically(source, target)

    assert target.read_bytes() == b"content"
    assert int(target.stat().st_mtime) == int(source.stat().st_mtime)  # M-4 语义
    assert list(target.parent.iterdir()) == [target]                  # 无 .part 残留


def test_copy_atomically_failure_leaves_no_target_and_no_part(store, tmp_path: Path) -> None:
    source = tmp_path / "src.jpg"
    source.write_bytes(b"x")
    target = tmp_path / "dst.jpg"
    real_replace = os.replace

    def _boom(src, dst):
        raise OSError("simulated crash before replace")

    os.replace = _boom
    try:
        with pytest.raises(OSError):
            store.copy_atomically(source, target)
    finally:
        os.replace = real_replace

    assert not target.exists()
    assert not (tmp_path / "dst.jpg.part").exists()


def test_find_available_sibling_is_deterministic(store, tmp_path: Path) -> None:
    target = tmp_path / "x.jpg"
    assert store.find_available_sibling(target, "dup") == tmp_path / "x.dup-1.jpg"
    (tmp_path / "x.dup-1.jpg").write_bytes(b"a")
    (tmp_path / "x.dup-2.jpg").write_bytes(b"a")
    assert store.find_available_sibling(target, "dup") == tmp_path / "x.dup-3.jpg"
    assert store.find_available_sibling(target, "dup") == tmp_path / "x.dup-3.jpg"


def test_csv_failure_list_writer_is_deterministic_and_bom(tmp_path: Path) -> None:
    writer = CsvFailureListWriter()
    target = tmp_path / "failures.csv"
    header = ["photo_id", "raw_path"]
    rows = [["a", "照片A.jpg"], ["b", "照片B.jpg"]]

    writer.write_failure_list(target, header, rows)
    first = target.read_bytes()
    writer.write_failure_list(target, header, rows)

    assert target.read_bytes() == first                    # 重复导出一致
    assert first.startswith(b"\xef\xbb\xbf")                # UTF-8 BOM
    text = target.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == "photo_id,raw_path"
    assert "照片A.jpg" in text
