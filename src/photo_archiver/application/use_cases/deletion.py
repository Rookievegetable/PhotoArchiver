"""Use case boundaries for deletion management (Phase E E-3, ADR-034).

删除管理四个用例的 Protocol 契约——Presentation 层（E-4）依赖本边界而非
具体服务类（DEP-010，review M-3 先例）。实现见
``application/services/delete_photos_service.py`` 等四个服务。

通用语义（ADR-034）：
- ``preview()`` 产级联计数预览（确认对话框数据源），无副作用；
- ``execute()`` 仅删除库内登记（D3：磁盘文件一律不动）、幂等（不存在的
  id 计 0 行成功）、在注入的 UnitOfWork 内原子提交；
- 全部动作落 loguru 审计行（谁/何时/id 列表）。
"""

from collections.abc import Sequence
from uuid import UUID

from photo_archiver.application.commands.deletion import (
    DeletePersonCommand,
    DeletePhotosCommand,
    DisposeDuplicatesCommand,
    PruneMissingCommand,
)
from photo_archiver.application.dtos.deletion import (
    DuplicateDisposalPreview,
    DuplicateDisposalResult,
    PersonDeletionPreview,
    PersonDeletionResult,
    PhotoDeletionPreview,
    PhotoDeletionResult,
    PruneMissingPreview,
    PruneMissingResult,
)


class DeletePhotosUseCase:
    """Contract for removing photo registrations (D1)."""

    def preview(self, photo_ids: Sequence[UUID]) -> PhotoDeletionPreview:  # type: ignore[empty-body]
        """Return the cascade-count preview for the requested photo ids."""
        raise NotImplementedError

    def execute(self, command: DeletePhotosCommand) -> PhotoDeletionResult:  # type: ignore[empty-body]
        """Delete the confirmed photo registrations inside one transaction."""
        raise NotImplementedError


class DeletePersonUseCase:
    """Contract for removing people (D2: 照片全部保留，识别归属置空)."""

    def preview(self, person_ids: Sequence[UUID]) -> PersonDeletionPreview:  # type: ignore[empty-body]
        """Return the embedding/orphan-recognition preview for the ids."""
        raise NotImplementedError

    def execute(self, command: DeletePersonCommand) -> PersonDeletionResult:  # type: ignore[empty-body]
        """Delete the confirmed people inside one transaction."""
        raise NotImplementedError


class PruneMissingPhotosUseCase:
    """Contract for pruning registry entries whose files are missing (D5)."""

    def preview(self) -> PruneMissingPreview:  # type: ignore[empty-body]
        """List registry entries whose disk file is gone (no side effects)."""
        raise NotImplementedError

    def execute(self, command: PruneMissingCommand) -> PruneMissingResult:  # type: ignore[empty-body]
        """Prune the confirmed missing registrations inside one transaction."""
        raise NotImplementedError


class DisposeDuplicatesUseCase:
    """Contract for duplicate disposal — keep earliest, remove the rest (D6)."""

    def preview(self) -> DuplicateDisposalPreview:  # type: ignore[empty-body]
        """Return per-group keep/remove proposals over all duplicate groups."""
        raise NotImplementedError

    def execute(self, command: DisposeDuplicatesCommand) -> DuplicateDisposalResult:  # type: ignore[empty-body]
        """Remove the confirmed duplicate registrations, guarding mis-picks."""
        raise NotImplementedError
