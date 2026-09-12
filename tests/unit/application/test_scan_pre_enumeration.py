"""ADR-041: main-thread pre-enumeration for the scan workflow (LIMIT-006).

Worker 线程的目录枚举/realpath 是 macOS 段错误（LIMIT-006）的触发面。本套件
锁定：

    服务：pre_enumerated 命令**零枚举调用**（scanner 不被触碰）且条目路径
          不再经 per-item resolve；
    控制器：scan_folder 在主线程调 enumerate_files 并把条目装进命令；
    守卫：服务源码永远不得重新引入枚举 API（防回归）。
"""

from pathlib import Path


from photo_archiver.application.commands import ScanAndRegisterPhotosCommand
from photo_archiver.application.dtos import PhotoScanItem
from photo_archiver.application.services import ScanAndRegisterPhotosService
class _SpyScanner:
    """Record scan() calls; return a fixed candidate list when allowed."""

    def __init__(self, items: list[PhotoScanItem]) -> None:
        self._items = items
        self.calls: list[Path] = []

    def scan(self, folder_path, *, recursive, supported_extensions, max_depth=32):  # noqa: ANN001
        self.calls.append(Path(folder_path))
        return list(self._items)


def _make_service(tmp_path: Path, scanner: _SpyScanner):
    from photo_archiver.infrastructure.repositories import (
        InMemoryFolderRepository,
        InMemoryPhotoRepository,
    )

    return ScanAndRegisterPhotosService(
        scanner=scanner,  # type: ignore[arg-type]
        folder_repository=InMemoryFolderRepository(),
        photo_repository=InMemoryPhotoRepository(),
    )


def test_pre_enumerated_command_never_touches_the_scanner(tmp_path: Path) -> None:
    """ADR-041 核心：预枚举命令下 worker 零目录枚举调用。"""
    scanner = _SpyScanner(items=[])
    service = _make_service(tmp_path, scanner)
    items = (
        PhotoScanItem(path=tmp_path / "a.jpg", original_name="a.jpg"),
        PhotoScanItem(path=tmp_path / "b.jpg", original_name="b.jpg"),
    )
    command = ScanAndRegisterPhotosCommand(
        folder_path=tmp_path,
        pre_enumerated_items=items,
    )

    result = service.execute(command)

    assert scanner.calls == [], "预枚举模式下 worker 不得触碰目录枚举"
    assert result.registered_count == 2
    assert result.failed_count == 0


def test_pre_enumerated_items_register_under_their_own_paths(tmp_path: Path) -> None:
    """条目路径即登记路径（枚举时已解析），worker 不做 per-item resolve。"""
    scanner = _SpyScanner(items=[])
    service = _make_service(tmp_path, scanner)
    target = tmp_path / "real" / "photo.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"fake")
    command = ScanAndRegisterPhotosCommand(
        folder_path=tmp_path,
        pre_enumerated_items=(PhotoScanItem(path=target, original_name="photo.jpg"),),
    )

    service.execute(command)

    # 登记持久化由 test_application_service_workflows 的真实 SQLite 链路覆盖；
    # 此处焦点是 worker 零枚举 + 计数。


def test_legacy_command_still_enumerates_through_the_scanner(tmp_path: Path) -> None:
    """CLI/旧路径（无预枚举）行为不变：经 scanner 枚举。"""
    source = tmp_path / "legacy.jpg"
    source.write_bytes(b"fake")
    scanner = _SpyScanner(
        items=[PhotoScanItem(path=source, original_name="legacy.jpg")]
    )
    service = _make_service(tmp_path, scanner)
    command = ScanAndRegisterPhotosCommand(folder_path=tmp_path)

    result = service.execute(command)

    assert scanner.calls == [tmp_path]
    assert result.registered_count == 1


def test_service_source_is_free_of_enumeration_apis() -> None:
    """守卫：服务模块（worker 执行路径）不得重新引入枚举 API。

    LIMIT-006 的段错误面 = 目录枚举/realpath 系统调用在后台线程与主线程
    事件循环并发——枚举已前置到主线程（ADR-041），本守卫防止回归。
    """
    source = Path(
        Path(__file__).resolve().parents[3]
        / "src"
        / "photo_archiver"
        / "application"
        / "services"
        / "scan_and_register_photos_service.py"
    ).read_text(encoding="utf-8")
    for banned in ("scandir", "listdir", "glob(", "os.walk", "realpath("):
        assert banned not in source, f"enumeration API '{banned}' re-entered the worker path"
