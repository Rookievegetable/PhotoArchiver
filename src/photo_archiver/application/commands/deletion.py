"""Commands for the deletion management workflow (Phase E E-3, ADR-034).

命令对象只携带"用户已确认"的 id 集合——确认流（级联计数预览）在 Presentation
层由 ``preview()`` 驱动，Application 层不重复弹确认。所有命令空 id 集合 =
显式 no-op（防 UI 状态过期时的误触发）。
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DeletePhotosCommand:
    """Request removal of the given photo registrations (D1: 磁盘文件不动)."""

    photo_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class DeletePersonCommand:
    """Request removal of the given people (D2: 照片全部保留)."""

    person_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class PruneMissingCommand:
    """Request pruning of confirmed missing-on-disk registrations (D5).

    photo_ids: The ids the user confirmed after inspecting the prune preview.
    An id that is no longer in the missing set at execute time (e.g. the file
    reappeared) is rejected and counted, never deleted.
    """

    photo_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class DisposeDuplicatesCommand:
    """Request removal of the given duplicate registrations (D6).

    photo_ids: Ids to remove — either the preview's per-group suggestions or
    the user's manual keep-selection remainder. Ids that are not a removable
    member of a duplicate group at execute time (keepers, unique photos) are
    rejected and counted, never deleted.
    """

    photo_ids: tuple[UUID, ...] = ()
