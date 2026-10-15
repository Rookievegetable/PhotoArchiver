"""位置自动确认的批次准入纯函数 — S4 C-2（BD-2；D2/D4/D5=A 裁决）.

判定当前批次剩余的位置配对是否满足**整批**自动确认准入条件，返回准入
结果与确定性阻断原因。本模块是**纯判定**：不查询数据、不过滤样本、不
消耗人员、不持久化记录、不创建身份决策、不计算相似度、不引入新阈值。

规则（逐条对应已批准裁决）：

- 准入 = 剩余 Cluster 数 == 剩余人员数、两序列非空、每个参与 Cluster 的
  ``first_captured_at`` 非空（D5=A：任一缺失即整批不准入），且每个严格
  位置对 ``(E_c[i].id, E_p[i].id)`` 均不在 ``rejected_pairs`` 中（D4=A：
  不跳过拒绝对、不顺延人员、不交换顺序）。
- 任一条件不满足 → 整批不准入。回退为现状 ``suggested`` 建议属调用方
  职责（D3=A），本函数只评估传入快照、不做回退决策。

输入契约（排序责任在调用方）：

- ``remaining_clusters`` / ``remaining_persons`` 为**有序序列**：分别由
  现有流程按 ``sort_key`` 升序与 ``roster_order`` 升序（无序者排末、
  person_id 兜底）提供——沿用现有规则③排序语义；本函数按传入下标做
  严格位置配对，不重排、不排序、不改输入。
- ``rejected_pairs`` 沿用 ``suggest_pairings`` 既有形态
  ``frozenset[tuple[UUID, UUID]]``（(cluster_id, person_id)，当前代际）。

阻断原因与优先级（同批多因时取最高优先级，同一输入恒定同一结果）：

1. ``COUNT_MISMATCH``——剩余 Cluster 与人员数量不一致；
2. ``EMPTY_INPUT``——数量相等但两侧均为空；
3. ``MISSING_CAPTURE_TIME``——任一参与 Cluster 的拍摄时间缺失
   （诊断取最低缺失下标）；
4. ``REJECTED_POSITIONAL_PAIR``——任一严格位置对已被拒绝
   （诊断取最低冲突下标及其 (cluster_id, person_id) 对）。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from photo_archiver.domain.entities.face_cluster import FaceCluster
from photo_archiver.domain.entities.person import Person

ADMISSION_REASON_COUNT_MISMATCH = "COUNT_MISMATCH"
ADMISSION_REASON_EMPTY_INPUT = "EMPTY_INPUT"
ADMISSION_REASON_MISSING_CAPTURE_TIME = "MISSING_CAPTURE_TIME"
ADMISSION_REASON_REJECTED_POSITIONAL_PAIR = "REJECTED_POSITIONAL_PAIR"


@dataclass(frozen=True, slots=True)
class PositionalAdmissionResult:
    """整批位置自动确认的准入判定结果（确定性、可诊断、不持久化）。

    ``admitted=False`` 时 ``reason`` 为四个阻断原因常量之一；诊断字段
    按原因填充（数量恒填，其余仅对应原因填充），供调用方与测试断言，
    不构成持久化业务状态。
    """

    admitted: bool
    reason: str | None
    cluster_count: int
    person_count: int
    missing_time_index: int | None = None
    rejected_positional_index: int | None = None
    rejected_positional_pair: tuple[UUID, UUID] | None = None


def evaluate_positional_auto_confirm(
    remaining_clusters: Sequence[FaceCluster],
    remaining_persons: Sequence[Person],
    rejected_pairs: frozenset[tuple[UUID, UUID]] = frozenset(),
) -> PositionalAdmissionResult:
    """评估剩余位置配对的整批自动确认准入（纯函数，规则见模块 docstring）。

    只读取传入序列的 ``id`` 与 ``first_captured_at`` 字段并查
    ``rejected_pairs``；不修改任何输入，不产生副作用。
    """

    cluster_count = len(remaining_clusters)
    person_count = len(remaining_persons)

    # 优先级 1：数量不一致（D2=A——两集合取规则①消耗后的剩余集，由调用方提供）。
    if cluster_count != person_count:
        return PositionalAdmissionResult(
            admitted=False,
            reason=ADMISSION_REASON_COUNT_MISMATCH,
            cluster_count=cluster_count,
            person_count=person_count,
        )

    # 优先级 2：数量相等但均为空（无可配对对象；"无剩余"不等于"全部可自动确认"）。
    if cluster_count == 0:
        return PositionalAdmissionResult(
            admitted=False,
            reason=ADMISSION_REASON_EMPTY_INPUT,
            cluster_count=0,
            person_count=0,
        )

    # 优先级 3：任一参与 Cluster 缺少有效拍摄时间（D5=A——整批不准入，
    # 一个不可靠位置污染全序；诊断取最低缺失下标）。
    missing_time_index = next(
        (
            index
            for index, cluster in enumerate(remaining_clusters)
            if cluster.first_captured_at is None
        ),
        None,
    )
    if missing_time_index is not None:
        return PositionalAdmissionResult(
            admitted=False,
            reason=ADMISSION_REASON_MISSING_CAPTURE_TIME,
            cluster_count=cluster_count,
            person_count=person_count,
            missing_time_index=missing_time_index,
        )

    # 优先级 4：任一严格位置对已被拒绝（D4=A——不跳过、不顺延；诊断取
    # 最低冲突下标及其 (cluster_id, person_id) 对）。
    for index, (cluster, person) in enumerate(
        zip(remaining_clusters, remaining_persons)
    ):
        cluster_id, person_id = cluster.id, person.id
        assert cluster_id is not None and person_id is not None  # 实体 __post_init__ 保证
        if (cluster_id, person_id) in rejected_pairs:
            return PositionalAdmissionResult(
                admitted=False,
                reason=ADMISSION_REASON_REJECTED_POSITIONAL_PAIR,
                cluster_count=cluster_count,
                person_count=person_count,
                rejected_positional_index=index,
                rejected_positional_pair=(cluster_id, person_id),
            )

    # 全部条件成立：整批准入，无阻断原因。
    return PositionalAdmissionResult(
        admitted=True,
        reason=None,
        cluster_count=cluster_count,
        person_count=person_count,
    )
