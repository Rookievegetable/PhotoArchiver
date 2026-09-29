"""Filesystem implementation of the archive file store port（AUD-010）.

从 ArchiveExecutor 逐字迁移的文件系统边界逻辑（P2-005/M-3/M-4 containment、
AUD-015 原子复制、确定性 dup 兄弟协商）——行为与迁移前完全一致，归属
Infrastructure 层（DEP §17）。
"""

from pathlib import Path

from photo_archiver.application.ports import ArchiveFileStore


class FilesystemArchiveFileStore(ArchiveFileStore):
    """Real-filesystem archive file store."""

    def path_exists(self, path: Path) -> bool:
        return path.exists()

    def ensure_parent_directory(self, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)

    def verify_target_containment(self, archive_root: Path, target: Path) -> str | None:
        """Return an error string when ``target`` would escape ``archive_root``.

        P2-005 fix — defence in depth at the filesystem boundary:

        1. Lexical containment (review M-3, kept): segment validation already
           blocks ``..``/separator names; this re-checks the composed target
           against the configured root.
        2. Filesystem-level containment: ``Path.resolve(strict=False)`` follows
           symlinks and junctions, so a pre-existing symlinked directory
           *inside* archive_root (local-attacker model) can no longer let
           mkdir/copy2 write through it to a location outside the root.
           ``ArchivePath.resolve`` is intentionally PurePath-lexical (Domain
           stays filesystem-free), so this re-check belongs to the store.
        3. Explicit leaf-symlink rejection: never overwrite or write through a
           symlinked target — including broken symlinks — even when the link
           happens to point back inside the root.
        """
        archive_root_path = Path(archive_root).resolve(strict=False)
        try:
            target.relative_to(archive_root_path)
        except ValueError:
            return f"target escapes archive_root: {target} not under {archive_root_path}"
        resolved_target = target.resolve(strict=False)
        if not resolved_target.is_relative_to(archive_root_path):
            return (
                f"target escapes archive_root via filesystem links: {target} resolves "
                f"to {resolved_target} outside {archive_root_path}"
            )
        if target.is_symlink():
            return f"target is a symlink: {target} — refusing to write through it"
        return None

    def copy_atomically(self, source: Path, target: Path) -> None:
        """Copy preserving metadata, via same-directory ``.part`` + ``os.replace``.

        review M-4 fix: copy2 (not copyfile) so target mtime tracks the
        source — re-scanning archive_root later can fall back to mtime for
        captured_at without seeing every archived file stamped "now". EXIF
        lives in the byte stream so it survives either helper; copy2 also
        preserves access mode bits which copyfile drops.

        AUD-015（Stage 12D）：mid-copy 崩溃只遗留 ``.part`` 兄弟（无害残留，
        同名重试会复用同名临时路径），不会在目标位置留下半写文件（skip 策略
        会把"目标存在"收敛为 SKIPPED 成功态，半写文件将永久锁定损坏归档）。
        ``os.replace`` 不穿越符号链接；符号链接目标已被 containment 检查
        先行拒绝，本方法不会见到。失败时清理临时副本。
        """
        import os
        import shutil

        temp = target.with_name(target.name + ".part")
        try:
            shutil.copy2(source, temp)
            os.replace(temp, target)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

    def find_available_sibling(self, target: Path, conflict_suffix: str) -> Path:
        """First non-existing ``{stem}.{suffix}-{n}{ext}`` sibling（确定性 dup 计数）.

        Stops at the first non-existing sibling so the rename counter is
        deterministic under concurrent runs of the same plan.
        """
        stem = target.stem
        suffix = target.suffix
        parent = target.parent
        counter = 1
        while True:
            candidate = parent / f"{stem}.{conflict_suffix}-{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1
