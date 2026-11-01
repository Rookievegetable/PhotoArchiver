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
class DeletePeopleByBatchCommand:
    """Request removal of one import batch's current members（界面优化 §4.3）.

    batch_id: The import batch whose *current* ``source_batch_id`` members are
    resolved at execution time (merge may have re-attributed people to other
    batches — the preview snapshot is never trusted at execute time).
    delete_batch_record: When True, also delete the ``import_batches`` row and
    its draft rows (raw_values import trace) in the same transaction. Default
    False — batch/draft records are kept.
    """

    batch_id: UUID
    delete_batch_record: bool = False


@dataclass(frozen=True, slots=True)
class ClearAllPeopleCommand:
    """Request removal of every person in the registry（界面优化 §4.3）."""


@dataclass(frozen=True, slots=True)
class DeleteRunRecordCommand:
    """Request removal of one recognition run's residual record（功能 C）.

    运行记录清理 = 残留聚类代际（决策行随簇级联）+ 残留观测 + 输入快照
    残留 + ``recognition_runs`` 行本身。照片仍在登记时被硬阻断——照片有
    专门的披露级联入口（D4-B），不走本命令。
    """

    run_id: UUID


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


# ── 识别运行级删除（批次删除功能 D1/D2/D4） ────────────────────────────────
#
# "批次"锚点 = 识别运行（``recognition_runs``）——照片只挂在运行下；名单导入
# 批次（``import_batches``）与运行之间没有任何关联字段。

RUN_PEOPLE_MODE_DELETE = "delete_people"
"""A3：删除该运行指向的人员实体及其级联记录（默认）。"""

RUN_PEOPLE_MODE_UNASSIGN = "unassign_only"
"""A1：只解除该运行的匹配关系，保留人员与其余记录。

以**状态迁移**实现（有效行 → unassigned），不物理删除决策行——守住
"决策行只增改不删"不变量。
"""


@dataclass(frozen=True, slots=True)
class DeleteRunPeopleCommand:
    """删除某识别运行指向的人员及其记录（D2 语义可选）。

    run_id: 目标识别运行。其"名单"= 该运行各聚类代际的决策行中出现过的
    人员（执行时点重新解析，绝不信任预览快照）。
    mode: :data:`RUN_PEOPLE_MODE_DELETE`（删人员+记录，默认）或
        :data:`RUN_PEOPLE_MODE_UNASSIGN`（仅解除匹配，保留人员）。
    """

    run_id: UUID
    mode: str = RUN_PEOPLE_MODE_DELETE


@dataclass(frozen=True, slots=True)
class DeleteRunPhotosCommand:
    """删除某识别运行的快照照片及其级联记录（D4）。

    run_id: 目标识别运行。照片范围 = ``recognition_run_photos`` 中该运行的
    快照行（执行时点重新解析）。
    purge_cluster_generations: 同时删除该运行的聚类代际（及其簇、成员与
        **该代际的身份决策行**——级联删除，必须先披露）。默认 False：保留
        运行历史与代际，只删照片与级联记录。
    delete_run_record: 同时删除运行记录本身（残留代际/观测/快照扫尾 +
        ``recognition_runs`` 行——批次删除功能 C 并入本命令，追加轮 22）。
        置 True 时代际必然随记录消失（隐含 purge，无需重复置位）。
    """

    run_id: UUID
    purge_cluster_generations: bool = False
    delete_run_record: bool = False
