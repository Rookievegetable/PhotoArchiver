"""S-B-6 Mechanical Scoring acceptance tests（R3 §6 D/G/N/R 类 + Gate 0）.

全部 fixture 驱动；生产零接触。Fixture 声明：测试构造工件 ≠ 生产工件；
评分结果仅为本服务返回的内存对象——R3 未定义输出文件格式，不发布任何产物。
"""

from __future__ import annotations

from pathlib import Path

from tests.integration.test_sb6_common import (
    VERSION,
    build_artifact_v2,
    build_attestation,
    full_setup,
    make_repos,
    rewrite_with_rehash,
    scoring_service,
)

from photo_archiver.application.services.mechanical_scoring_service import (
    ADMISSION_TERMS,
    GT_STATE_PERSON,
    GT_STATE_UNDECIDABLE,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _happy(tmp_path):
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    attestation_result, _service = build_attestation(repos, tmp_path, setup)
    artifact_result, _artifact_service = build_artifact_v2(
        repos, tmp_path, setup, attestation_result
    )
    return repos, setup, attestation_result, artifact_result


def _score(repos, setup, artifact_result, attestation_result, **overrides):
    service = scoring_service(repos)
    kwargs = dict(
        artifact_path=artifact_result.artifact_path,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
        isolation_attestation_path=attestation_result.attestation_path,
    )
    kwargs.update(overrides)
    return service.score(**kwargs)


def test_happy_path_admission_and_member_outcomes(tmp_path):
    """全条件通过 → admission=True；13 项准入条件齐备；member-level 原始比较事实."""
    repos, setup, attestation_result, artifact_result = _happy(tmp_path)
    result = _score(repos, setup, artifact_result, attestation_result)

    assert result.input_class == "prediction-artifact-v2"
    assert result.rejection_outcome == "not-required"
    assert set(result.conditions.keys()) == set(ADMISSION_TERMS)
    assert result.conditions["attestation_assurance"] == "valid-and-verified"
    others = {
        key: value
        for key, value in result.conditions.items()
        if key != "attestation_assurance"
    }
    assert all(v == "pass" for v in others.values()), others
    assert result.admission is True
    assert result.assurance == "valid-and-verified"
    assert result.layer_a == "pass" and result.layer_b == "pass"

    assert len(result.member_outcomes) == 3
    for row in result.member_outcomes:
        assert row.gt_state == GT_STATE_PERSON
        assert row.truth_person_id is not None
        assert row.matches_truth is True  # fixture 预测 = GT 真值
        assert row.top1_score == 0.9
    assert result.gt_validation is not None and result.gt_validation.ok


def test_v1_input_is_terminal_rejection(tmp_path):
    """T-C10（消费者侧）：v1 工件 → Gate 0 REJECT-TERMINAL.

    正确拒绝 = 测试断言成功 ∧ rejection_outcome=rejected-as-required ∧
    admission=false ∧ 无评分产物、无异常。
    """
    from tests.integration.test_sb5_prediction_artifact import (
        _build_artifact as _build_v1_artifact,
        _predictions_from_snapshot,
        _setup_with_snapshot as _v1_setup,
    )

    repos = make_repos(tmp_path)
    snapshot_result, snapshot_path, _people = _v1_setup(repos, tmp_path)
    predictions, _document = _predictions_from_snapshot(repos, snapshot_path)
    _v1_result, v1_path = _build_v1_artifact(
        repos, tmp_path, snapshot_result, snapshot_path, predictions
    )
    service = scoring_service(repos)
    result = service.score(
        artifact_path=v1_path,
        target_manifest_path=tmp_path / "unused-manifest.json",
        reference_snapshot_path=tmp_path / "unused-snapshot.json",
        isolation_attestation_path=tmp_path / "unused-attestation.json",
    )
    assert result.input_class == "prediction-artifact-v1"
    assert result.rejection_outcome == "rejected-as-required"
    assert result.admission is False
    assert result.member_outcomes == ()
    assert any("ERR-V1-INPUT" in reason for reason in result.reasons)
    assert all(v == "not-run" for v in result.conditions.values())


def test_unknown_input_is_terminal_rejection(tmp_path):
    """Gate 0：未知/缺失输入 → REJECT-TERMINAL（不抛异常、不放行）."""
    repos = make_repos(tmp_path)
    service = scoring_service(repos)
    result = service.score(
        artifact_path=tmp_path / "ghost.json",
        target_manifest_path=tmp_path / "m.json",
        reference_snapshot_path=tmp_path / "s.json",
        isolation_attestation_path=tmp_path / "a.json",
    )
    assert result.input_class == "unknown"
    assert result.rejection_outcome == "rejected-as-required"
    assert result.admission is False
    assert result.member_outcomes == ()


def test_sc_source_out_of_scope_rejected(tmp_path):
    """T-C12（消费者侧）：schema 合法的 S-C 工件 → Source Authorization fail."""
    repos, setup, attestation_result, _artifact_result = _happy(tmp_path)
    sc_result, _service = build_artifact_v2(
        repos, tmp_path, setup, attestation_result, source="S-C", name="sc6.json"
    )
    result = _score(repos, setup, sc_result, attestation_result)
    assert result.conditions["prediction_source_authorization"] == "fail"
    assert result.admission is False
    assert result.member_outcomes == ()
    assert any("ERR-SOURCE-OUT-OF-SCOPE" in reason for reason in result.reasons)


def test_manifest_source_omission_blocks_scoring(tmp_path):
    """T-M6/T-M7（消费者侧）：Layer A pass ∧ Layer B fail → NO SCORING."""
    repos, setup, attestation_result, artifact_result = _happy(tmp_path)

    def mutate(document):
        content = document["content"]
        content["entries"] = content["entries"][:-1]
        content["entry_count"] = len(content["entries"])
        content["source_member_count"] = len(content["entries"])
        content["cluster_count"] = len(
            {e["cluster_id"] for e in content["entries"]}
        )

    rewrite_with_rehash(setup.manifest_result.manifest_path, mutate)
    result = _score(repos, setup, artifact_result, attestation_result)
    assert result.layer_b == "fail"
    assert result.admission is False
    assert result.member_outcomes == ()


def test_gt_duplicate_row_blocks_scoring(tmp_path):
    """T-G2：GT 每簇恰一 verdict——注入重复行 → FrozenGTValidation fail."""
    import uuid as uuid_mod_local

    from photo_archiver.domain.entities.calibration_annotation import (
        CalibrationGroundTruth,
    )

    repos, setup, attestation_result, artifact_result = _happy(tmp_path)
    repos.calibration_annotations.add_ground_truth(
        CalibrationGroundTruth(
            cluster_id=setup.clusters[0].id,
            verdict="person",
            resolution="expert",
            source_annotation_ids=(uuid_mod_local.uuid4(),),
            annotator_count=1,
            person_id=setup.people[0].id,
            dataset_id=setup.dataset.id,
            dataset_version=VERSION,
        )
    )
    result = _score(repos, setup, artifact_result, attestation_result)
    assert result.conditions["frozen_gt_validation"] == "fail"
    assert result.admission is False
    assert result.gt_validation is not None
    assert result.gt_validation.exactly_one_verdict is False


def test_three_state_no_null_collapse(tmp_path):
    """T-G4：gt-person / gt-cluster-undecidable 状态独立（禁止 NULL 塌缩）."""
    repos = make_repos(tmp_path)
    setup = full_setup(
        repos, tmp_path, gt_verdicts=["person", "undecidable", "person"]
    )
    attestation_result, _service = build_attestation(repos, tmp_path, setup)
    artifact_result, _artifact_service = build_artifact_v2(
        repos, tmp_path, setup, attestation_result
    )
    result = _score(repos, setup, artifact_result, attestation_result)
    assert result.admission is True

    by_state = {row.gt_state for row in result.member_outcomes}
    assert by_state == {GT_STATE_PERSON, GT_STATE_UNDECIDABLE}
    undecidable_row = next(
        row for row in result.member_outcomes if row.gt_state == GT_STATE_UNDECIDABLE
    )
    assert undecidable_row.truth_person_id is None
    assert undecidable_row.matches_truth is None  # 不得强制判对错
    assert undecidable_row.prediction_type == "no-candidate"
    person_rows = [
        row for row in result.member_outcomes if row.gt_state == GT_STATE_PERSON
    ]
    assert all(row.matches_truth is True for row in person_rows)


def test_gt_read_only_closure(tmp_path):
    """T-G5：GT 只读——评分前后 GT 行数与聚类/成员表零变化."""
    repos, setup, attestation_result, artifact_result = _happy(tmp_path)
    before = (
        len(
            repos.calibration_annotations.list_ground_truth(
                dataset_id=setup.dataset.id, dataset_version=VERSION
            )
        ),
        len(repos.face_clusters.list_members(setup.cluster_run.id)),
        len(list(repos.calibration_annotations.list_datasets())),
    )
    result = _score(repos, setup, artifact_result, attestation_result)
    assert result.admission is True
    after = (
        len(
            repos.calibration_annotations.list_ground_truth(
                dataset_id=setup.dataset.id, dataset_version=VERSION
            )
        ),
        len(repos.face_clusters.list_members(setup.cluster_run.id)),
        len(list(repos.calibration_annotations.list_datasets())),
    )
    assert before == after


def test_missing_attestation_blocks_scoring(tmp_path):
    """T-A12：必需层不可用（Attestation 缺失）→ admission=false + 六维明细."""
    repos, setup, attestation_result, artifact_result = _happy(tmp_path)
    result = _score(
        repos, setup, artifact_result, attestation_result,
        isolation_attestation_path=tmp_path / "attestations" / "missing.json",
    )
    assert result.admission is False
    assert result.attestation_integrity == "not-run"
    assert result.assurance == "unprovable"
    assert result.member_outcomes == ()
    failing = [k for k, v in result.conditions.items() if v != "pass"]
    assert failing


def test_snapshot_binding_mismatch_blocks_scoring(tmp_path):
    """双绑定：替换为另一合法 Snapshot（身份/哈希不符）→ snapshot_binding=fail."""
    from tests.integration.test_sb4_reference_snapshot import (
        _build as _build_snapshot,
        _confirmed_reference,
    )

    repos, setup, attestation_result, artifact_result = _happy(tmp_path)
    other_run, other_cluster_run, _clusters, _person = _confirmed_reference(
        repos, tmp_path, setup.people, person_index=1, photo_name="r2.jpg"
    )
    _other_snapshot, other_path = _build_snapshot(
        repos, tmp_path, other_run, other_cluster_run, name="snapshot2.json"
    )
    result = _score(
        repos, setup, artifact_result, attestation_result,
        reference_snapshot_path=other_path,
    )
    assert result.conditions["snapshot_binding"] == "fail"
    assert result.admission is False


def test_fixture_boundary_statements_present(tmp_path):
    """T-N1/N2：生产无关性四声明 + fixture 边界在任务书中在位；
    评分服务明示不发布产物；本测试模块标注 fixture。"""
    spec = (
        REPO_ROOT
        / "docs"
        / "development"
        / "S4B2-S-B-6-Mechanical-Scoring-Task-Specification.md"
    ).read_text(encoding="utf-8")
    for statement in (
        "Actual Evaluation 的统计口径和指标政策尚未批准",
        "sb-member-max-cosine-v1 Prediction Producer 尚未实现",
        "测试 Fixture 不等于真实生产预测",
        "本任务书不授权创建或发布生产 Manifest / Artifact",
    ):
        assert statement in spec
    assert "Fixture 仅用于" in spec
    service_module = (
        REPO_ROOT
        / "src"
        / "photo_archiver"
        / "application"
        / "services"
        / "mechanical_scoring_service.py"
    ).read_text(encoding="utf-8")
    assert "不发布任何产物" in service_module
    assert "fixture" in __doc__


def test_admission_single_point_veto_inventory(tmp_path):
    """T-R2（代表性单点否决）：列出已覆盖的否决注入与条件属主."""
    repos, setup, attestation_result, artifact_result = _happy(tmp_path)

    # 注入：source=S-C
    sc_result, _ = build_artifact_v2(
        repos, tmp_path, setup, attestation_result, source="S-C", name="veto-sc.json"
    )
    veto_sc = _score(repos, setup, sc_result, attestation_result)
    assert veto_sc.conditions["prediction_source_authorization"] == "fail"

    # 注入：Attestation 缺失
    veto_missing = _score(
        repos, setup, artifact_result, attestation_result,
        isolation_attestation_path=tmp_path / "none.json",
    )
    assert veto_missing.admission is False
    assert veto_missing.attestation_integrity == "not-run"
