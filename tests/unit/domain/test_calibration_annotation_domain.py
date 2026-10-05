"""S4-B-1 / Checkpoint 1/2 — Ground Truth Domain 与 Contract 的可执行约束。

这些测试**只**覆盖 Domain 实体与 Repository Contract 的语义，不触及 SQLite、
UI 或业务链（那属于后续 Checkpoint）。目的是让 Ground Truth 的业务规则在
Domain + Contract 层成为**可执行约束**，避免后续实现产生语义漂移。

对应本阶段的 19 项要求，逐条钉死。
"""

from __future__ import annotations

import ast
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from photo_archiver.domain.entities.calibration_annotation import (
    DATASET_STATUS_DRAFT,
    DATASET_STATUS_FROZEN,
    LATEST_ANNOTATION_ORDER,
    PROTOCOL_VERSION,
    RESOLUTION_EXPERT,
    RESOLUTIONS,
    ROLE_ADJUDICATION,
    ROLE_INDEPENDENT,
    VERDICT_OUT_OF_ROSTER,
    VERDICT_PERSON,
    VERDICT_UNDECIDABLE,
    DIFFICULTY_OCCLUSION,
    CalibrationAnnotation,
    CalibrationDataset,
    CalibrationGroundTruth,
)
from photo_archiver.domain.exceptions import ValidationError

_SRC = Path(__file__).resolve().parents[3] / "src" / "photo_archiver"


def _person() -> UUID:
    return uuid4()


def _annotation(**overrides) -> CalibrationAnnotation:
    payload = {
        "cluster_id": uuid4(),
        "annotator_id": "annotator-a",
        "verdict": VERDICT_OUT_OF_ROSTER,
    }
    payload.update(overrides)
    return CalibrationAnnotation(**payload)


# ══ 1. 三种 verdict 合法状态 ═══════════════════════════════════════════════


@pytest.mark.parametrize(
    "verdict,person_id,difficulty",
    [
        (VERDICT_PERSON, "PERSON", None),
        (VERDICT_OUT_OF_ROSTER, None, None),
        (VERDICT_UNDECIDABLE, None, DIFFICULTY_OCCLUSION),
    ],
)
def test_three_verdicts_are_constructible(verdict, person_id, difficulty) -> None:
    """CP1.1：三种标签语义各自可构造。"""
    annotation = _annotation(
        verdict=verdict,
        person_id=_person() if person_id else None,
        difficulty_reason=difficulty,
    )
    assert annotation.verdict == verdict


# ══ 2. 三种 verdict 非法状态 ═══════════════════════════════════════════════


def test_person_without_person_id_rejected() -> None:
    """CP1.1/1.2：person 必须绑定人——不留 'person + person_id=null' 模糊态。"""
    with pytest.raises(ValidationError, match="requires a person_id"):
        _annotation(verdict=VERDICT_PERSON)


@pytest.mark.parametrize("verdict", [VERDICT_OUT_OF_ROSTER, VERDICT_UNDECIDABLE])
def test_non_person_verdicts_reject_person_id(verdict) -> None:
    """CP1.1：out_of_roster / undecidable 不得携带 person_id。"""
    with pytest.raises(ValidationError, match="must not carry a person_id"):
        _annotation(verdict=verdict, person_id=_person())


def test_undecidable_requires_difficulty_reason() -> None:
    """CP1.1/1.2：undecidable 必须说明难例原因（否则无法做质量分层）。"""
    with pytest.raises(ValidationError, match="requires a difficulty_reason"):
        _annotation(verdict=VERDICT_UNDECIDABLE)


def test_out_of_roster_rejects_difficulty_reason() -> None:
    with pytest.raises(ValidationError, match="only applies to 'undecidable'"):
        _annotation(
            verdict=VERDICT_OUT_OF_ROSTER, difficulty_reason=DIFFICULTY_OCCLUSION
        )


def test_unknown_verdict_rejected() -> None:
    with pytest.raises(ValidationError, match="Unknown calibration verdict"):
        _annotation(verdict="probably_fine")


def test_unknown_difficulty_reason_rejected() -> None:
    with pytest.raises(ValidationError, match="Unknown difficulty reason"):
        _annotation(verdict=VERDICT_UNDECIDABLE, difficulty_reason="vibes")


# ══ 3. difficulty_reason 不丢失 ════════════════════════════════════════════


def test_difficulty_reason_preserved_on_annotation_and_truth() -> None:
    """CP1.1：difficulty_reason 必须贯通 Annotation → GroundTruth。"""
    annotation = _annotation(
        verdict=VERDICT_UNDECIDABLE, difficulty_reason=DIFFICULTY_OCCLUSION
    )
    assert annotation.difficulty_reason == DIFFICULTY_OCCLUSION

    truth = CalibrationGroundTruth(
        cluster_id=annotation.cluster_id,
        verdict=VERDICT_UNDECIDABLE,
        resolution=RESOLUTION_EXPERT,
        difficulty_reason=annotation.difficulty_reason,
        source_annotation_ids=(annotation.id,),
        annotator_count=1,
    )
    assert truth.difficulty_reason == DIFFICULTY_OCCLUSION


def test_undecidable_truth_requires_difficulty_reason() -> None:
    """GroundTruth 层同样强制——防止真值丢失难例分类。"""
    with pytest.raises(ValidationError, match="requires a difficulty_reason"):
        CalibrationGroundTruth(
            cluster_id=uuid4(),
            verdict=VERDICT_UNDECIDABLE,
            resolution=RESOLUTION_EXPERT,
            source_annotation_ids=(uuid4(),),
            annotator_count=1,
        )


# ══ 4/5. annotator / adjudicator 非空 ═════════════════════════════════════


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_blank_annotator_rejected(blank) -> None:
    """CP1.2：trim 后为空的 annotator_id 必须拒绝。"""
    with pytest.raises(ValidationError, match="annotator_id must not be empty"):
        _annotation(annotator_id=blank)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_adjudication_adjudicator_rejected(blank) -> None:
    """CP1.7：仲裁必须由具名仲裁者作出。"""
    with pytest.raises(ValidationError, match="annotator_id"):
        _annotation(role=ROLE_ADJUDICATION, annotator_id=blank)


def test_blank_protocol_version_rejected() -> None:
    """CP1.2：protocol_version 不可为空白。"""
    with pytest.raises(ValidationError, match="protocol_version"):
        _annotation(protocol_version="   ")


def test_unknown_role_rejected() -> None:
    """CP1.3：role 词表封闭。"""
    with pytest.raises(ValidationError, match="Unknown annotation role"):
        _annotation(role="peer-review")


def test_adjudication_role_is_accepted() -> None:
    """CP1.3：adjudication 是合法 role（与 independent 并列）。"""
    assert _annotation(role=ROLE_ADJUDICATION).role == ROLE_ADJUDICATION


# ══ 6. 单专家真值（D-2 = Single Human Expert）══════════════════════════


def test_single_expert_truth_is_constructible() -> None:
    """D-2：一条专家标注直接构成真值（annotator_count == 1 == len(source)）。"""
    annotation = _annotation(role=ROLE_INDEPENDENT)
    truth = CalibrationGroundTruth(
        cluster_id=annotation.cluster_id,
        verdict=VERDICT_PERSON,
        person_id=_person(),
        resolution=RESOLUTION_EXPERT,
        source_annotation_ids=(annotation.id,),
        annotator_count=1,
    )
    assert truth.resolution == RESOLUTION_EXPERT
    assert truth.annotator_count == 1
    assert truth.source_annotation_ids == (annotation.id,)


@pytest.mark.parametrize(
    ("count", "message"),
    [
        (0, "explicit source annotations"),
        (2, "exactly one annotation"),
    ],
)
def test_ground_truth_requires_exactly_one_annotator(count, message) -> None:
    """D-2：annotator_count 必须恰为 1（0 仍非法，2 即伪造第二标注）。"""
    sources = (uuid4(),) * count
    with pytest.raises(ValidationError, match=message):
        CalibrationGroundTruth(
            cluster_id=uuid4(),
            verdict=VERDICT_OUT_OF_ROSTER,
            resolution=RESOLUTION_EXPERT,
            source_annotation_ids=sources,
            annotator_count=count,
        )


def test_ground_truth_count_must_match_source_ids() -> None:
    """D-2：annotator_count 与 source_annotation_ids 语义一致（1 带双源即伪造）。"""
    with pytest.raises(ValidationError, match="must equal the number of source"):
        CalibrationGroundTruth(
            cluster_id=uuid4(),
            verdict=VERDICT_OUT_OF_ROSTER,
            resolution=RESOLUTION_EXPERT,
            source_annotation_ids=(uuid4(), uuid4()),
            annotator_count=1,
        )


# ══ 7-10. 废止词表拒绝（agreed / adjudicated 不再存在）══════════════════


@pytest.mark.parametrize("resolution", ["agreed", "adjudicated"])
def test_deprecated_resolutions_rejected(resolution) -> None:
    """D-2：双标/仲裁词表已废止 —— 实体层拒绝（DB CHECK 同步收敛为 expert）。"""
    with pytest.raises(ValidationError, match="Unknown resolution"):
        CalibrationGroundTruth(
            cluster_id=uuid4(),
            verdict=VERDICT_OUT_OF_ROSTER,
            resolution=resolution,
            source_annotation_ids=(uuid4(),),
            annotator_count=1,
        )


def test_resolution_vocabulary_collapsed_to_expert() -> None:
    """D-2：词表恰为 {'expert'}，无任何伪兼容残留。"""
    assert RESOLUTIONS == {RESOLUTION_EXPERT}


# ══ 11/12. append-only 由 frozen 数据类保证 ═══════════════════════════════


@pytest.mark.parametrize(
    "entity",
    [
        lambda: _annotation(),
        lambda: CalibrationGroundTruth(
            cluster_id=uuid4(), verdict=VERDICT_OUT_OF_ROSTER,
            resolution=RESOLUTION_EXPERT, source_annotation_ids=(uuid4(),),
            annotator_count=1,
        ),
        lambda: CalibrationDataset(version="v1", cluster_count=1, usable_count=1,
                                   excluded_count=0),
    ],
)
def test_entities_are_immutable(entity) -> None:
    """CP2.3：实体 frozen —— 没有就地修改入口，历史只能追加。"""
    instance = entity()
    with pytest.raises(Exception):
        instance.created_at = None  # type: ignore[misc]


# ══ 13. source annotation ids 强制 ════════════════════════════════════════


def test_ground_truth_requires_source_annotation_ids() -> None:
    """CP1.4/1.5：真值必须能回答'由哪些标注得出'。"""
    with pytest.raises(ValidationError, match="explicit source annotations"):
        CalibrationGroundTruth(
            cluster_id=uuid4(),
            verdict=VERDICT_OUT_OF_ROSTER,
            resolution=RESOLUTION_EXPERT,
            source_annotation_ids=(),
            annotator_count=1,
        )


# ══ 15/16. Blind view 与契约隔离（静态 + 运行时） ═════════════════════════


def test_contract_separates_blind_view_from_audit_view() -> None:
    """CP2.2：own 视图与审计视图是两个不同方法，不是一过滤。"""
    from photo_archiver.domain.repositories.calibration_annotation_repository import (
        CalibrationAnnotationRepository,
    )

    declared = {
        name for name in dir(CalibrationAnnotationRepository)
        if not name.startswith("_")
    }
    assert "find_latest_own_annotation" in declared, "缺少 own（盲）视图"
    assert "list_annotations" in declared, "缺少审计视图"
    assert declared - {"find_latest_own_annotation"} != {"list_annotations"}, (
        "两个视图必须是独立方法，不能由 UI 内存过滤代替"
    )


def test_contract_excludes_business_capabilities() -> None:
    """CP2.1：契约不含任何业务仓储写能力。"""
    from photo_archiver.domain.repositories.calibration_annotation_repository import (
        CalibrationAnnotationRepository,
    )

    forbidden = {
        # assignment
        "add_assignments", "update_assignment", "assign", "confirm_identity",
        # recognition
        "add", "add_many", "update_status", "list_pending", "list_projections",
        "remove_results_for_person_photos", "list_approved_by_person",
        # sample
        "add_samples", "disable_samples", "list_enabled",
        # archive
        "archive", "list_all_approved",
    }
    declared = {
        name for name in dir(CalibrationAnnotationRepository)
        if not name.startswith("_")
    }
    assert not (declared & forbidden), f"契约泄漏业务能力：{declared & forbidden}"


def test_contract_has_no_update_or_delete() -> None:
    """CP2.3：append-only —— 契约不提供破坏历史真实性的方法。"""
    from photo_archiver.domain.repositories.calibration_annotation_repository import (
        CalibrationAnnotationRepository,
    )

    declared = [
        name for name in dir(CalibrationAnnotationRepository)
        if not name.startswith("_")
    ]
    assert not [n for n in declared if n.startswith("update_")]
    assert not [n for n in declared if n.startswith("delete_")]
    assert [n for n in declared if n.startswith("add_")], "应只有 add_ 写入"


# ══ 17/18. Frozen dataset ═════════════════════════════════════════════════


def test_dataset_defaults_to_frozen_and_exposes_is_frozen() -> None:
    """CP2.4：默认冻结。"""
    dataset = CalibrationDataset(
        version="v1", cluster_count=3, usable_count=2, excluded_count=1
    )
    assert dataset.status == DATASET_STATUS_FROZEN
    assert dataset.is_frozen is True


def test_dataset_accepts_draft() -> None:
    """CP2.4：draft 是合法状态（仍在收集标注）。"""
    dataset = CalibrationDataset(
        version="draft", cluster_count=1, usable_count=0, excluded_count=0,
        status=DATASET_STATUS_DRAFT,
    )
    assert dataset.status == DATASET_STATUS_DRAFT
    assert dataset.is_frozen is False


def test_dataset_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError, match="Unknown dataset status"):
        CalibrationDataset(
            version="v1", cluster_count=0, usable_count=0, excluded_count=0,
            status="published",
        )


def test_dataset_identity_is_version_scoped() -> None:
    """CP2.4：新版本是一个**新行**，旧行不被就地改写。

    ``CalibrationDataset`` 的 ``id`` 是逐实例生成的行标识；同一逻辑数据集的
    "同一性"由调用方显式传入（Service 的 ``freeze_dataset(dataset_id, version)``），
    Domain 只保证"冻结"这一属性落在版本上。
    """
    shared_id = uuid4()
    first = CalibrationDataset(version="v1", cluster_count=1, usable_count=1,
                               excluded_count=0, id=shared_id)
    second = CalibrationDataset(version="v2", cluster_count=1, usable_count=1,
                                excluded_count=0, id=shared_id)
    assert first.id == second.id, "同一数据集共用 id"
    assert first.version != second.version, "版本不同 = 不同行"
    assert first.is_frozen and second.is_frozen


@pytest.mark.parametrize("blank", ["", "   "])
def test_dataset_rejects_blank_version(blank) -> None:
    with pytest.raises(ValidationError, match="version must not be empty"):
        CalibrationDataset(
            version=blank, cluster_count=0, usable_count=0, excluded_count=0
        )


def test_dataset_rejects_usable_exceeding_cluster_count() -> None:
    """可用数不得超过总簇数——否则数据集自相矛盾。"""
    with pytest.raises(ValidationError, match="must not exceed cluster_count"):
        CalibrationDataset(
            version="v1", cluster_count=2, usable_count=5, excluded_count=0
        )


# ══ 19. 依赖隔离（CP2.6，静态 AST 核查） ══════════════════════════════════


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import) and node.names:
            modules.update(alias.name for alias in node.names)
    return modules


def test_calibration_domain_has_no_business_dependency() -> None:
    """CP2.6：Calibration domain 只依赖 domain 自身与 exceptions。"""
    modules = _imports_of(
        _SRC / "domain" / "entities" / "calibration_annotation.py"
    )
    forbidden = {
        "photo_archiver.infrastructure",
        "photo_archiver.application",
        "photo_archiver.presentation",
        "photo_archiver.ai",
    }
    assert not (modules & forbidden), f"domain 依赖越界：{modules & forbidden}"


def test_calibration_contract_has_no_business_dependency() -> None:
    """CP2.6：Calibration contract 同样不依赖业务仓储/基础设施。"""
    modules = _imports_of(
        _SRC / "domain" / "repositories" / "calibration_annotation_repository.py"
    )
    forbidden = {
        "photo_archiver.infrastructure",
        "photo_archiver.application",
        "photo_archiver.presentation",
    }
    assert not (modules & forbidden), f"contract 依赖越界：{modules & forbidden}"


def test_latest_order_contract_is_declared() -> None:
    """CP1.8：'最新'的判据被显式声明，且明确禁用 UUID 序。"""
    assert "created_at" in LATEST_ANNOTATION_ORDER
    assert "id ASC" in LATEST_ANNOTATION_ORDER
    assert "id" in LATEST_ANNOTATION_ORDER
    assert PROTOCOL_VERSION  # 规程版本随标注记录保存


def test_annotation_carries_protocol_version() -> None:
    """CP1.2：每条标注都带当时的规程版本。"""
    assert _annotation().protocol_version == PROTOCOL_VERSION
    assert _annotation(protocol_version="s4b1-v2").protocol_version == "s4b1-v2"