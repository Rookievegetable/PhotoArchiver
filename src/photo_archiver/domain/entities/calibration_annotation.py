"""Ground Truth 标注领域模型（S4-B-1）。

与业务域（``cluster_assignment`` / ``recognition``）**完全分离**：本模块不认识
Assignment、不认识 Projection、不认识阈值。评估层（S4-B-2）从这里的真值派生
指标，而不是反过来用机器结果生成真值。

标签语义（Checkpoint 5 的冻结结果）：

======================  ==================================================
verdict                 语义
======================  ==================================================
``person``              核验确认该簇主体 = ``person_id`` 指向的人
``out_of_roster``       核验确认该簇主体**不在名单中**（新人/范围外人员）
``undecidable``         图像不足以支持可靠判断（遮挡/侧脸/过小/模糊/光照/压缩）
======================  ==================================================

三者的区分是硬约束：

* ``undecidable`` **不是**负样本——它表示"证据不足"，S4-B-2 必须把它排除在
  精确率分母之外，而不是算作"正确拒绝"。
* ``out_of_roster`` **不是** ``person`` 的反面——它是一个真实身份判断（这个人
  存在但不在名单里），与"这个人不存在"不同。
* 二者都**不是**机器 label；只来自人工核验。

标注角色（S4-B-2 D-2 单专家协议）：

* ``independent``——现行唯一**产生**角色：一名人类专家逐簇独立判断，
  own 视图彼此不可见对方结果。
* ``adjudication``——旧双标协议的仲裁角色，已随协议废止；词表与存储
  机制仍接受该值，但现行流程**不再产生**，也不存在"终结冲突"语义。

``undecidable`` 须携带 ``difficulty_reason``（否则无法做质量分层）；``person``
须携带 ``person_id``（否则无法评估候选命中）。两条由实体构造期强制。
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from photo_archiver.domain.exceptions import ValidationError

# ── 标签词表 ────────────────────────────────────────────────────────────────

VERDICT_PERSON = "person"
VERDICT_OUT_OF_ROSTER = "out_of_roster"
VERDICT_UNDECIDABLE = "undecidable"
VERDICTS = frozenset({VERDICT_PERSON, VERDICT_OUT_OF_ROSTER, VERDICT_UNDECIDABLE})

ROLE_INDEPENDENT = "independent"
ROLE_ADJUDICATION = "adjudication"
ANNOTATION_ROLES = frozenset({ROLE_INDEPENDENT, ROLE_ADJUDICATION})

# 难例原因（undecidable 的必填分类，用于质量分层）
DIFFICULTY_OCCLUSION = "occlusion"
DIFFICULTY_PROFILE = "profile"
DIFFICULTY_TOO_SMALL = "too_small"
DIFFICULTY_BLUR = "blur"
DIFFICULTY_LIGHTING = "lighting"
DIFFICULTY_COMPRESSION = "compression"
DIFFICULTY_OTHER = "other"
DIFFICULTY_REASONS = frozenset(
    {
        DIFFICULTY_OCCLUSION,
        DIFFICULTY_PROFILE,
        DIFFICULTY_TOO_SMALL,
        DIFFICULTY_BLUR,
        DIFFICULTY_LIGHTING,
        DIFFICULTY_COMPRESSION,
        DIFFICULTY_OTHER,
    }
)

# 真值解析方式（S4-B-2 D-2 单专家协议：专家判断直接成为真值；双标共识
# agreed 与仲裁 adjudicated 已随旧协议废止，不得再产出）
RESOLUTION_EXPERT = "expert"
RESOLUTIONS = frozenset({RESOLUTION_EXPERT})

# 数据集状态（CP2.4）
#
# ``draft``  = 仍在收集标注，可随当前 truth 变化；
# ``frozen`` = 评估集内容**不可原地修改**——新一轮标注必须产生新的 dataset
#             version，旧版本的成员与真值保持原样（否则历史校准报告无法复现）。
DATASET_STATUS_DRAFT = "draft"
DATASET_STATUS_FROZEN = "frozen"
DATASET_STATUSES = frozenset({DATASET_STATUS_DRAFT, DATASET_STATUS_FROZEN})

PROTOCOL_VERSION = "s4b1-v1"

#: "最新标注"的唯一判据（CP1.8）。
#:
#: 仓储与查询层必须按 ``(created_at, id)`` **升序**返回标注，"最新"= 序列最后
#: 一条。不得改用 UUID 序、插入内存序或任何其他代理键——同刻写入时 UUID 序是
#: 随机的，会让"最新"变成任意行（该陷阱在 S1-F 的 ``created_at`` 全序问题上已
#: 出现过一次）。服务层另用单调时间戳保证写入序 == 逻辑序，本常量是**读取侧**
#: 必须遵守的契约。
LATEST_ANNOTATION_ORDER = "(created_at ASC, id ASC) — last element is latest"


def validate_verdict_payload(
    verdict: str, person_id: UUID | None, difficulty_reason: str | None,
) -> None:
    """Enforce the verdict/payload coupling shared by annotation and ground truth.

    ``person`` 必须绑定人；``undecidable`` 必须给出难例原因；``out_of_roster``
    既不绑人也不需要难例原因。集中在此以便两个实体复用同一规则。
    """
    if verdict not in VERDICTS:
        raise ValidationError(f"Unknown calibration verdict: {verdict}")
    if verdict == VERDICT_PERSON:
        if person_id is None:
            raise ValidationError("verdict 'person' requires a person_id")
        if difficulty_reason is not None:
            raise ValidationError("difficulty_reason only applies to 'undecidable'")
        return
    if person_id is not None:
        raise ValidationError(f"verdict {verdict!r} must not carry a person_id")
    if verdict == VERDICT_UNDECIDABLE:
        if difficulty_reason is None:
            raise ValidationError("verdict 'undecidable' requires a difficulty_reason")
        if difficulty_reason not in DIFFICULTY_REASONS:
            raise ValidationError(f"Unknown difficulty reason: {difficulty_reason}")
    elif difficulty_reason is not None:
        raise ValidationError("difficulty_reason only applies to 'undecidable'")


# ── 实体 ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CalibrationAnnotation:
    """One human expert annotation of a FaceCluster（单专家协议）.

    **只读**（frozen）：标注一经写入不可修改；重新标注 = 追加新行。这是
    "标注历史必须保留"的结构性保证，而不是靠调用方自律。
    """

    cluster_id: UUID
    annotator_id: str
    verdict: str
    protocol_version: str = PROTOCOL_VERSION
    role: str = ROLE_INDEPENDENT
    person_id: UUID | None = None
    difficulty_reason: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.cluster_id is None:  # pragma: no cover - type-level guarantee
            raise ValidationError("annotation must reference a cluster_id")
        if not self.annotator_id or not self.annotator_id.strip():
            raise ValidationError("annotator_id must not be empty")
        if self.role not in ANNOTATION_ROLES:
            raise ValidationError(f"Unknown annotation role: {self.role}")
        if self.role == ROLE_ADJUDICATION and not self.annotator_id.strip():
            raise ValidationError("adjudication requires a non-empty adjudicator_id")
        if not self.protocol_version.strip():
            raise ValidationError("protocol_version must not be empty")
        validate_verdict_payload(self.verdict, self.person_id, self.difficulty_reason)
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())


@dataclass(frozen=True, slots=True)
class CalibrationGroundTruth:
    """Final ground truth for one FaceCluster（单专家协议）.

    ``source_annotation_ids`` 记录支撑该真值的标注行 id —— "最终真值由什么
    得出"是显式的、可审计的。单专家协议下恰为**一条**专家标注
    （``annotator_count == 1 == len(source_annotation_ids)``）。
    """

    cluster_id: UUID
    verdict: str
    resolution: str
    source_annotation_ids: tuple[UUID, ...]
    annotator_count: int
    person_id: UUID | None = None
    difficulty_reason: str | None = None
    """Carried through from the source annotation so S4-B-2 can stratify by
    difficulty. ``undecidable`` truth rows must keep their reason (the verdict
    itself is what matters for stratification)."""
    dataset_id: UUID | None = None
    dataset_version: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_verdict_payload(self.verdict, self.person_id, self.difficulty_reason)
        if self.resolution not in RESOLUTIONS:
            raise ValidationError(f"Unknown resolution: {self.resolution}")
        if not self.source_annotation_ids:
            raise ValidationError("ground truth requires explicit source annotations")
        if self.annotator_count != len(self.source_annotation_ids):
            raise ValidationError(
                "annotator_count must equal the number of source annotations"
            )
        if self.annotator_count != 1:
            raise ValidationError(
                "single-expert ground truth requires exactly one annotation "
                "(annotator_count == 1 == len(source_annotation_ids))"
            )
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())


@dataclass(frozen=True, slots=True)
class CalibrationDataset:
    """One evaluation dataset (versioned; frozen content is immutable).

    ``frozen`` 表示该数据集的内容已被固定为某个 ``(id, version)``：其成员真值
    行（``dataset_id`` / ``dataset_version``）不再随新的标注改变。重新标注之后
    必须创建**新的 version**，旧版本保持原样以保证已产出的校准报告可复现。

    **只读**（frozen）：数据集一经构造即不可就地修改——这是"冻结"的结构性
    表达，而不是靠调用方自律。
    """

    version: str
    cluster_count: int
    usable_count: int
    excluded_count: int
    protocol_version: str = PROTOCOL_VERSION
    status: str = DATASET_STATUS_FROZEN
    notes: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValidationError("dataset version must not be empty")
        if self.status not in DATASET_STATUSES:
            raise ValidationError(f"Unknown dataset status: {self.status}")
        if self.cluster_count < 0 or self.usable_count < 0 or self.excluded_count < 0:
            raise ValidationError("dataset counters must be non-negative")
        if self.usable_count > self.cluster_count:
            raise ValidationError(
                "usable_count must not exceed cluster_count (usable rows are a "
                "subset of the annotated clusters)"
            )
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())

    @property
    def is_frozen(self) -> bool:
        """Whether the dataset content is fixed against further annotation."""
        return self.status == DATASET_STATUS_FROZEN