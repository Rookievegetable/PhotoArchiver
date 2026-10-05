"""Domain exceptions for PhotoArchiver."""


class PhotoArchiverDomainError(Exception):
    """Base exception for domain-layer errors."""


class ValidationError(PhotoArchiverDomainError):
    """Raised when a domain value violates business validation rules."""


class ManualDecisionProtectedError(ValidationError):
    """S0 INV-4：机器操作试图修改/撤销人工身份决策。

    人工决策（``source ∈ MANUAL_ASSIGNMENT_SOURCES``）只能被**人工**操作终结或
    改派。机器侧（自动确认、自动重跑、机器侧撤回）必须先声明 actor 并接受此
    守卫拒绝——决策历史一旦被机器改成 terminal，reconcile 重算支撑就会发现
    "无 active Assignment" 并连带删除投影，INV-4 在投影层无法补救（已实证）。
    """


class PhotoNotClusteredError(ValidationError):
    """D-2（B 方案，Owner 冻结 2026-10-02）：照片尚未聚类，不得完成身份确认。

    Review 批准的硬前置：该照片至少存在一个有效 FaceObservation，且该观测已进入
    ``face_cluster_members``（observation → cluster 链真实存在）。未聚类照片必须
    先运行聚类——禁止为通过审核而偷偷创建人工单成员簇。fail-closed：不产生
    Assignment、不产生 projection、pending 行保持原状。
    """


class ReviewAnchorAmbiguousError(ValidationError):
    """S1-F 语义修正：照片在最新聚类代际中对应**多个**簇，审核无法唯一定锚。

    Review 的输入是照片级 ``(photo, person)``，而 Assignment 是簇级
    ``(cluster, person)``——合影中不同脸分落不同簇时，"批准照片给某人"无法
    唯一确定该改写哪个簇（实测反例：C1→A 已确认，approve(P,B) 按 Top-1 会
    错把 C1→B）。fail-closed：不猜测、不落任何写入；多人照片的逐簇身份
    决策走配对工作台（其 UI 本就是簇粒度），或由调用方显式提供 cluster_id。
    """


class ConcurrentDecisionConflictError(PhotoArchiverDomainError):
    """S1：并发决策事务在重试预算内仍未获得写锁（BEGIN IMMEDIATE 超窗）。

    整个事务已回滚、无部分写入；调用方应提示用户稍后重试，而非静默失败。
    """


class RepositoryError(PhotoArchiverDomainError):
    """Raised by repository abstractions for persistence-related failures."""


class ImageUnreadableError(PhotoArchiverDomainError):
    """Raised when an image file cannot be read or decoded.

    Distinct from "no faces detected": an unreadable file (missing, locked,
    partial download, unsupported encoding) is an input problem the user can
    act on, so the recognition pipeline surfaces it per-photo instead of
    silently treating it as a faceless photo (AUDIT 2026-09-20: cv2.imread
    returned None for every Chinese-path photo and 473/473 were silently
    dropped). Lives in the domain layer so both ``ai`` adapters (raise) and
    ``application`` services (handle) may reference it per DEP rules.
    """