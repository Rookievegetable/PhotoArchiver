"""S-B-6 contract primitives（R3 冻结契约的共享常量、规范化与派生规则）.

依据 ``docs/development/S4B2-S-B-6-Mechanical-Scoring-Task-Specification.md``（R3）
与 ``docs/decisions/S4B2-v2-architecture-final-decisions.md``（含 ORD-1..8 裁决）。

本模块只含纯函数与常量——零业务写入、零文件 I/O。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from photo_archiver.domain.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Schema / RULESET 常量（冻结值，实现不得更改）
# ---------------------------------------------------------------------------

TARGET_MANIFEST_SCHEMA_VERSION = "target-manifest-v1"
PREDICTION_ARTIFACT_V1_SCHEMA_VERSION = "prediction-artifact-v1"
PREDICTION_ARTIFACT_V2_SCHEMA_VERSION = "prediction-artifact-v2"
ISOLATION_ATTESTATION_SCHEMA_VERSION = "isolation-attestation-v1"

# RULESET 规范标识值（R3 §4.1 冻结；代码变量名仅为实现标识）
ISOLATION_ATTESTATION_RULESET = "isolation-attestation-rules-v1"

# ORD-4：UUIDv5 namespace —— 配方可复现，且与冻结常量值双记录一致（见 _namespace）
_PREDICTION_NAMESPACE_RECIPE = (
    "https://photoarchiver.local/s4b2/prediction-artifact-v2/prediction-item"
)
_FROZEN_NAMESPACE_VALUE = UUID("4b60862f-952f-5094-98d2-09df3f32d886")

TARGET_MANIFEST_CONTENT_KEYS = (
    "schema_version",
    "dataset_id",
    "dataset_version",
    "cluster_run_id",
    "dataset_cluster_ids",
    "cluster_count",
    "entry_count",
    "source_member_count",
    "entries",
)
TARGET_MANIFEST_ENTRY_KEYS = ("cluster_id", "observation_id", "photo_id")

ISOLATION_ATTESTATION_CONTENT_KEYS = (
    "schema_version",
    "ruleset",
    "dataset_id",
    "dataset_version",
    "cluster_run_id",
    "target_manifest_id",
    "target_manifest_sha256",
    "reference_snapshot_id",
    "reference_snapshot_sha256",
    "reference_recognition_run_ids",
    "photo_set_digests",
    "checks",
    "unprovable_reasons",
)
ISOLATION_ATTESTATION_CHECK_KEYS = (
    "check_id",
    "rule_ref",
    "inputs_digest",
    "result",
    "evidence_refs",
    "detail",
)
ISOLATION_ATTESTATION_RESULTS = ("pass", "fail", "unprovable")

ARTIFACT_V2_CONTENT_KEYS = (
    "schema_version",
    "prediction_source",
    "scorer_version",
    "reference_snapshot_id",
    "reference_snapshot_sha256",
    "target_manifest_id",
    "target_manifest_sha256",
    "dataset_id",
    "dataset_version",
    "input_population_scope",
    "entry_count",
    "cluster_count",
    "score_semantics",
    "git_commit",
    "threshold",
    "isolation_invariant_sha256",
    "predictions",
)
ARTIFACT_V2_ITEM_KEYS = (
    "prediction_id",
    "prediction_type",
    "cluster_run_id",
    "cluster_id",
    "observation_id",
    "photo_id",
    "top1_person_id",
    "top1_score",
    "top2_person_id",
    "top2_score",
    "rank",
    "margin",
    "evidence_winning_reference_observation_id",
)

PREDICTION_SOURCE_SB = "S-B"
PREDICTION_SOURCE_SA = "S-A"
PREDICTION_SOURCE_SC = "S-C"
PREDICTION_SOURCES = (
    PREDICTION_SOURCE_SB,
    PREDICTION_SOURCE_SA,
    PREDICTION_SOURCE_SC,
)
# R3 §4.7 Prediction Source Authorization：本阶段消费者仅有权处理 S-B
SCORING_AUTHORIZED_SOURCES = (PREDICTION_SOURCE_SB,)

PREDICTION_TYPE_PREDICTED = "predicted"
PREDICTION_TYPE_NO_CANDIDATE = "no-candidate"

SB_SCORER_VERSION = "sb-member-max-cosine-v1"
SB_SCORE_SEMANTICS = {
    "method": SB_SCORER_VERSION,
    "domain": "[-1, 1]",
    "unit": "raw-cosine",
    "direction": "higher-is-better",
}

# Gate 0 输入分类（R3 §4.7 / B7.2）
INPUT_CLASS_V2 = PREDICTION_ARTIFACT_V2_SCHEMA_VERSION
INPUT_CLASS_V1 = PREDICTION_ARTIFACT_V1_SCHEMA_VERSION
INPUT_CLASS_UNKNOWN = "unknown"

REJECTION_AS_REQUIRED = "rejected-as-required"
REJECTION_NOT_REQUIRED = "not-required"
REJECTION_BYPASSED_ERROR = "bypassed-error"


def _as_uuid(value: UUID | str) -> UUID:
    """Normalize str/UUID inputs（S-B 链既有纪律：入口即归一，非法输入 fail-closed）."""
    return value if isinstance(value, UUID) else UUID(str(value))


def prediction_namespace() -> UUID:
    """ORD-4：配方派生值与冻结常量双记录一致——不一致 → fail-closed."""
    derived = uuid5(NAMESPACE_URL, _PREDICTION_NAMESPACE_RECIPE)
    if derived != _FROZEN_NAMESPACE_VALUE:
        raise ValidationError(
            "ERR-CONTRACT-FIELDS: UUIDv5 namespace recipe mismatch — "
            f"recipe derives {derived}, frozen constant is {_FROZEN_NAMESPACE_VALUE}"
        )
    return derived


def prediction_id_for(
    cluster_run_id: UUID | str,
    cluster_id: UUID | str,
    observation_id: UUID | str,
) -> UUID:
    """R3 §4.4：prediction_id = uuid5(NAMESPACE, "<run>|<cluster>|<observation>")（小写 RFC 4122 文本）."""
    identity = (
        f"{_as_uuid(cluster_run_id)}|{_as_uuid(cluster_id)}|{_as_uuid(observation_id)}"
    )
    return uuid5(prediction_namespace(), identity)


def derive_prediction_type(top1_person_id: UUID | None) -> str:
    return (
        PREDICTION_TYPE_PREDICTED
        if top1_person_id is not None
        else PREDICTION_TYPE_NO_CANDIDATE
    )


def derive_rank(prediction_type: str, top1_score: float | None) -> int | None:
    """ORD-1 批准：predicted ∧ top1_score 非 NULL ⇒ 1；否则 NULL."""
    if prediction_type == PREDICTION_TYPE_PREDICTED and top1_score is not None:
        return 1
    return None


def derive_margin(top1_score: float | None, top2_score: float | None) -> float | None:
    """修订冻结 1 §4 批准公式：双分齐备 ⇒ top1−top2；否则 NULL."""
    if top1_score is not None and top2_score is not None:
        return top1_score - top2_score
    return None


@dataclass(frozen=True, slots=True)
class PredictionRecordV2:
    """一条 GIVEN 预测（权威字段输入；prediction_type/rank/margin/prediction_id 由 builder 派生）."""

    cluster_run_id: UUID
    cluster_id: UUID
    observation_id: UUID
    photo_id: UUID
    top1_person_id: UUID | None
    top1_score: float | None
    top2_person_id: UUID | None = None
    top2_score: float | None = None


def validate_prediction_record_v2(
    record: PredictionRecordV2, prediction_source: str
) -> None:
    """R3 §5.2.4 合法状态组合（含 ORD-8 批准的四条 top2 规则）；违反 → ERR-CONTRACT-FIELDS."""
    top1p, top1s = record.top1_person_id, record.top1_score
    top2p, top2s = record.top2_person_id, record.top2_score

    if top1p is None:
        # no-candidate 冻结块（R2 R5 指令）：全部权威字段必须 NULL
        if top1s is not None or top2p is not None or top2s is not None:
            raise ValidationError(
                "ERR-CONTRACT-FIELDS: no-candidate must carry NULL score/top2 "
                f"(score={top1s}, top2_person={top2p}, top2_score={top2s})"
            )
        return

    if prediction_source == PREDICTION_SOURCE_SB and top1s is None:
        raise ValidationError(
            "ERR-CONTRACT-FIELDS: S-B predicted requires non-NULL top1_score (K=A+C)"
        )

    # top2 成对约束（ORD-8 批准）
    if top2s is not None and top2p is None:
        raise ValidationError(
            "ERR-CONTRACT-FIELDS: orphan top2_score without top2_person_id"
        )
    if top2p is not None and top2s is None and prediction_source == PREDICTION_SOURCE_SB:
        raise ValidationError(
            "ERR-CONTRACT-FIELDS: S-B top2_person_id requires non-NULL top2_score"
        )
    if top2p is not None and top2p == top1p:
        raise ValidationError(
            "ERR-CONTRACT-FIELDS: top2_person_id must differ from top1_person_id"
        )


def prediction_item_payload(
    record: PredictionRecordV2,
    evidence_winning_reference_observation_id: str | None = None,
) -> dict:
    """逐项 canonical payload（固定键序 = ARTIFACT_V2_ITEM_KEYS；派生字段由权威字段产生）.

    ``evidence_winning_reference_observation_id``（ORD-2 / R3 §5.2.1）：
    键必填可空；值由 builder 经确定性 derivation 生成（见 PredictionArtifactV2Service），
    verifier 独立重验证——本函数只负责按固定键序落盘。
    """
    prediction_type = derive_prediction_type(record.top1_person_id)
    return {
        "prediction_id": str(
            prediction_id_for(
                record.cluster_run_id, record.cluster_id, record.observation_id
            )
        ),
        "prediction_type": prediction_type,
        "cluster_run_id": str(record.cluster_run_id),
        "cluster_id": str(record.cluster_id),
        "observation_id": str(record.observation_id),
        "photo_id": str(record.photo_id),
        "top1_person_id": (
            str(record.top1_person_id) if record.top1_person_id is not None else None
        ),
        "top1_score": record.top1_score,
        "top2_person_id": (
            str(record.top2_person_id) if record.top2_person_id is not None else None
        ),
        "top2_score": record.top2_score,
        "rank": derive_rank(prediction_type, record.top1_score),
        "margin": derive_margin(record.top1_score, record.top2_score),
        "evidence_winning_reference_observation_id": (
            evidence_winning_reference_observation_id
        ),
    }


def uuid_or_none(value) -> UUID | None:
    return None if value is None else UUID(str(value))
