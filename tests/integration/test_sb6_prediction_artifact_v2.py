"""S-B-6 Prediction Artifact v2 acceptance tests（R3 §6 B/S/C/D 类）.

全部 fixture 驱动；生产零接触。Fixture 声明：测试构造工件 ≠ 生产工件。
"""

from __future__ import annotations

import json
import shutil
import uuid as uuid_mod
from uuid import UUID

import pytest

from tests.integration.test_sb6_common import (
    VERSION,
    FullSetup,
    artifact_v2_service,
    build_artifact_v2,
    build_attestation,
    build_eval_side,
    build_manifest,
    full_setup,
    make_repos,
    predictions_from_manifest,
    read_json,
    rewrite_with_rehash,
)
from tests.integration.test_sb3_reference_eligibility import (
    _guard,
    _reference_batch,
)
from tests.integration.test_sb4_reference_snapshot import (
    _build as _build_snapshot,
    _snapshot_service,
)
from tests.integration.test_sb5_prediction_artifact import (
    _build_artifact as _build_v1_artifact,
    _predictions_from_snapshot,
    _setup_with_snapshot as _v1_setup,
)

from photo_archiver.application.services.reference_snapshot_service import (
    SnapshotDocument,
    canonical_json,
    embedding_sha256,
)
from photo_archiver.application.services.sb6_contract import (
    ARTIFACT_V2_CONTENT_KEYS,
    INPUT_CLASS_V1,
    PredictionRecordV2,
)
from photo_archiver.domain.exceptions import ValidationError

import hashlib


def _prepared(tmp_path):
    """full_setup + 合法 Attestation（三件套就绪）."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    attestation_result, _service = build_attestation(repos, tmp_path, setup)
    return repos, setup, attestation_result


def _verify(service, result, setup):
    return service.verify_artifact_v2(
        result.artifact_path,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
    )


def test_build_valid_determinism_and_rederivation(tmp_path):
    """T-D1（三分比较）+ T-D4（跨构建独立重派生）."""
    repos, setup, attestation_result = _prepared(tmp_path)
    first, service = build_artifact_v2(
        repos, tmp_path, setup, attestation_result,
        computed_at="2026-10-09T00:00:00+00:00", name="a.json",
    )
    second, _ = build_artifact_v2(
        repos, tmp_path, setup, attestation_result,
        computed_at="2026-10-09T01:00:00+00:00", name="b.json",
    )
    # (b) content SHA 相同；(a) payload bytes 相同；(c) envelope 允许不同
    assert first.artifact_sha256 == second.artifact_sha256
    doc_a = read_json(first.artifact_path)
    doc_b = read_json(second.artifact_path)
    assert canonical_json(doc_a["content"]) == canonical_json(doc_b["content"])
    assert doc_a["artifact_id"] != doc_b["artifact_id"]
    assert doc_a["computed_at"] != doc_b["computed_at"]
    # T-D4：独立重派生 prediction_id
    from photo_archiver.application.services.sb6_contract import prediction_id_for

    for item in doc_a["content"]["predictions"]:
        rederived = prediction_id_for(
            item["cluster_run_id"], item["cluster_id"], item["observation_id"]
        )
        assert item["prediction_id"] == str(rederived)


def test_content_keys_and_envelope_shape(tmp_path):
    """编码约定：content 键集固定；Envelope 含 computed_at；threshold 恒 None."""
    repos, setup, attestation_result = _prepared(tmp_path)
    result, _ = build_artifact_v2(repos, tmp_path, setup, attestation_result)
    document = read_json(result.artifact_path)
    assert set(document["content"].keys()) == set(ARTIFACT_V2_CONTENT_KEYS)
    assert document["content"]["threshold"] is None
    assert "computed_at" in document  # envelope（不入哈希域）
    assert document["content"]["entry_count"] == 3
    assert document["content"]["cluster_count"] == 3
    assert document["content"]["score_semantics"]["method"] == "sb-member-max-cosine-v1"


def test_v1_artifact_classified_and_refused(tmp_path):
    """T-C10（分类侧）：v1 工件 → input_class=prediction-artifact-v1；v2 verifier 不通过."""
    repos = make_repos(tmp_path)
    snapshot_result, snapshot_path, _people = _v1_setup(repos, tmp_path)
    predictions, _document = _predictions_from_snapshot(repos, snapshot_path)
    _v1_result, v1_path = _build_v1_artifact(
        repos, tmp_path, snapshot_result, snapshot_path, predictions
    )
    service = artifact_v2_service(repos)
    assert service.classify(v1_path) == INPUT_CLASS_V1
    verification = service.verify_artifact_v2(v1_path)
    assert verification.input_class == INPUT_CLASS_V1
    assert verification.schema_version_valid is False
    assert verification.ok is False
    assert service.classify(tmp_path / "missing.json") == "unknown"


def test_no_candidate_block_builder_and_verifier(tmp_path):
    """T-C1：no-candidate 全 NULL 冻结块（builder 拒绝违规；verifier 检出篡改）."""
    repos, setup, attestation_result = _prepared(tmp_path)
    records = predictions_from_manifest(repos, setup)
    bad = PredictionRecordV2(
        cluster_run_id=records[0].cluster_run_id,
        cluster_id=records[0].cluster_id,
        observation_id=records[0].observation_id,
        photo_id=records[0].photo_id,
        top1_person_id=None,
        top1_score=0.9,  # no-candidate 携带 score → 非法
    )
    with pytest.raises(ValidationError, match="ERR-CONTRACT-FIELDS"):
        build_artifact_v2(
            repos, tmp_path, setup, attestation_result, predictions=[bad]
        )
    # 合法 no-candidate
    no_candidate = [
        PredictionRecordV2(
            cluster_run_id=record.cluster_run_id,
            cluster_id=record.cluster_id,
            observation_id=record.observation_id,
            photo_id=record.photo_id,
            top1_person_id=None,
            top1_score=None,
        )
        for record in records
    ]
    result, service = build_artifact_v2(
        repos, tmp_path, setup, attestation_result, predictions=no_candidate,
        name="abstain.json",
    )
    document = read_json(result.artifact_path)
    for item in document["content"]["predictions"]:
        assert item["prediction_type"] == "no-candidate"
        assert item["top1_person_id"] is None and item["top1_score"] is None
        assert item["rank"] is None and item["margin"] is None
    assert _verify(service, result, setup).contracts_valid is True


def test_predicted_without_top1_rejected_by_verifier(tmp_path):
    """T-C2：predicted 而 top1_person_id 为空（篡改）→ 契约拒绝."""
    repos, setup, attestation_result = _prepared(tmp_path)
    result, service = build_artifact_v2(repos, tmp_path, setup, attestation_result)

    def mutate(document):
        document["content"]["predictions"][0]["prediction_type"] = "predicted"
        document["content"]["predictions"][0]["top1_person_id"] = None

    rewrite_with_rehash(result.artifact_path, mutate)
    assert _verify(service, result, setup).contracts_valid is False


def test_sb_predicted_requires_score(tmp_path):
    """T-C3：S-B predicted 且 top1_score=NULL → builder 拒绝（K=A+C）."""
    repos, setup, attestation_result = _prepared(tmp_path)
    records = predictions_from_manifest(repos, setup, score=None)
    with pytest.raises(ValidationError, match="ERR-CONTRACT-FIELDS"):
        build_artifact_v2(repos, tmp_path, setup, attestation_result, predictions=records)


def test_sc_predicted_null_score_is_legal(tmp_path):
    """T-C4：S-C predicted + score=NULL 合法（不补分、不修正）.

    注意：S-C 的**阶段授权**由评分消费者拒绝（Source Authorization），
    此处仅验证 schema/契约层合法性。
    """
    repos, setup, attestation_result = _prepared(tmp_path)
    records = predictions_from_manifest(repos, setup, score=None)
    result, service = build_artifact_v2(
        repos, tmp_path, setup, attestation_result, predictions=records,
        source="S-C", name="sc.json",
    )
    document = read_json(result.artifact_path)
    for item in document["content"]["predictions"]:
        assert item["prediction_type"] == "predicted"
        assert item["top1_score"] is None  # 未被补分/修正
        assert item["rank"] is None
    assert _verify(service, result, setup).contracts_valid is True


def test_top2_pairing_and_uniqueness_rules(tmp_path):
    """T-C5/C6/C7（ORD-8 批准）：孤儿 top2_score / S-B top2 无分 / top2==top1 → 拒绝."""
    repos, setup, attestation_result = _prepared(tmp_path)
    records = predictions_from_manifest(repos, setup)
    base = records[0]

    orphan = PredictionRecordV2(
        cluster_run_id=base.cluster_run_id, cluster_id=base.cluster_id,
        observation_id=base.observation_id, photo_id=base.photo_id,
        top1_person_id=base.top1_person_id, top1_score=0.9,
        top2_person_id=None, top2_score=0.5,
    )
    with pytest.raises(ValidationError, match="ERR-CONTRACT-FIELDS"):
        build_artifact_v2(
            repos, tmp_path, setup, attestation_result, predictions=[orphan]
        )

    sb_missing_score = PredictionRecordV2(
        cluster_run_id=base.cluster_run_id, cluster_id=base.cluster_id,
        observation_id=base.observation_id, photo_id=base.photo_id,
        top1_person_id=base.top1_person_id, top1_score=0.9,
        top2_person_id=uuid_mod.uuid4(), top2_score=None,
    )
    with pytest.raises(ValidationError, match="ERR-CONTRACT-FIELDS"):
        build_artifact_v2(
            repos, tmp_path, setup, attestation_result, predictions=[sb_missing_score]
        )

    duplicate_person = PredictionRecordV2(
        cluster_run_id=base.cluster_run_id, cluster_id=base.cluster_id,
        observation_id=base.observation_id, photo_id=base.photo_id,
        top1_person_id=base.top1_person_id, top1_score=0.9,
        top2_person_id=base.top1_person_id, top2_score=0.8,
    )
    with pytest.raises(ValidationError, match="ERR-CONTRACT-FIELDS"):
        build_artifact_v2(
            repos, tmp_path, setup, attestation_result, predictions=[duplicate_person]
        )


def test_rank_margin_tamper_and_null_rules(tmp_path):
    """T-C8/T-C9：派生字段被篡改 / margin 在 top2=NULL 时给出 → 契约拒绝."""
    repos, setup, attestation_result = _prepared(tmp_path)
    result, service = build_artifact_v2(repos, tmp_path, setup, attestation_result)

    def tamper_margin(document):
        document["content"]["predictions"][0]["margin"] = 0.01

    rewrite_with_rehash(result.artifact_path, tamper_margin)
    assert _verify(service, result, setup).contracts_valid is False

    result2, service2 = build_artifact_v2(
        repos, tmp_path, setup, attestation_result, name="rank2.json"
    )

    def tamper_rank(document):
        document["content"]["predictions"][0]["rank"] = 2

    rewrite_with_rehash(result2.artifact_path, tamper_rank)
    assert _verify(service2, result2, setup).contracts_valid is False

    # top2 全 NULL 时 margin 必须 NULL（篡改为非空 → 拒绝）
    result3, service3 = build_artifact_v2(
        repos, tmp_path, setup, attestation_result, name="rank3.json"
    )

    def tamper_margin_without_top2(document):
        document["content"]["predictions"][0]["margin"] = 0.2

    rewrite_with_rehash(result3.artifact_path, tamper_margin_without_top2)
    assert _verify(service3, result3, setup).contracts_valid is False


def test_silent_fix_probe(tmp_path):
    """T-C11：非法输入 → 拒绝且无产物、无改写（静默修正探针）."""
    repos, setup, attestation_result = _prepared(tmp_path)
    records = predictions_from_manifest(repos, setup)
    bad = PredictionRecordV2(
        cluster_run_id=records[0].cluster_run_id, cluster_id=records[0].cluster_id,
        observation_id=records[0].observation_id, photo_id=records[0].photo_id,
        top1_person_id=records[0].top1_person_id, top1_score=None,  # S-B 无分非法
    )
    original = [bad]
    with pytest.raises(ValidationError):
        build_artifact_v2(
            repos, tmp_path, setup, attestation_result, predictions=original,
            name="nope.json",
        )
    assert not (tmp_path / "artifacts" / "nope.json").exists()
    assert original[0].top1_score is None  # 输入对象未被改写


def test_bijection_orphan_missing_and_photo_mismatch(tmp_path):
    """Artifact ↔ Manifest 逐项双射：orphan / missing / photo 错配 → 拒绝."""
    repos, setup, attestation_result = _prepared(tmp_path)
    records = predictions_from_manifest(repos, setup)

    orphan = PredictionRecordV2(
        cluster_run_id=records[0].cluster_run_id,
        cluster_id=uuid_mod.uuid4(),
        observation_id=uuid_mod.uuid4(),
        photo_id=uuid_mod.uuid4(),
        top1_person_id=records[0].top1_person_id,
        top1_score=0.9,
    )
    with pytest.raises(ValidationError, match="ERR-IDENTITY-MISMATCH"):
        build_artifact_v2(
            repos, tmp_path, setup, attestation_result, predictions=records + [orphan]
        )
    with pytest.raises(ValidationError, match="ERR-COUNT-MISMATCH"):
        build_artifact_v2(
            repos, tmp_path, setup, attestation_result, predictions=records[:-1]
        )
    mismatched = PredictionRecordV2(
        cluster_run_id=records[0].cluster_run_id,
        cluster_id=records[0].cluster_id,
        observation_id=records[0].observation_id,
        photo_id=uuid_mod.uuid4(),
        top1_person_id=records[0].top1_person_id,
        top1_score=0.9,
    )
    with pytest.raises(ValidationError, match="ERR-IDENTITY-MISMATCH|ERR-COUNT-MISMATCH"):
        build_artifact_v2(
            repos, tmp_path, setup, attestation_result,
            predictions=[mismatched] + records[1:],
        )


def test_wrong_bindings_rejected(tmp_path):
    """T-B1..T-B4：ID / SHA 各错误（Manifest / Snapshot）→ 双 fail-closed."""
    repos, setup, attestation_result = _prepared(tmp_path)
    records = predictions_from_manifest(repos, setup)
    service = artifact_v2_service(repos)
    base_kwargs = dict(
        prediction_source="S-B",
        scorer_version="sb-member-max-cosine-v1",
        predictions=records,
        reference_snapshot_path=setup.snapshot_path,
        reference_snapshot_id=setup.snapshot_result.snapshot_id,
        reference_snapshot_sha256=setup.snapshot_result.snapshot_sha256,
        target_manifest_path=setup.manifest_result.manifest_path,
        target_manifest_id=setup.manifest_result.manifest_id,
        target_manifest_sha256=setup.manifest_result.manifest_sha256,
        isolation_attestation_path=attestation_result.attestation_path,
    )
    with pytest.raises(ValidationError, match="ERR-IDENTITY-MISMATCH"):
        service.build_artifact_v2(
            destination=tmp_path / "artifacts" / "x1.json",
            **{**base_kwargs, "reference_snapshot_id": uuid_mod.uuid4()},
        )
    with pytest.raises(ValidationError, match="ERR-HASH-MISMATCH"):
        service.build_artifact_v2(
            destination=tmp_path / "artifacts" / "x2.json",
            **{**base_kwargs, "reference_snapshot_sha256": "0" * 64},
        )
    with pytest.raises(ValidationError, match="ERR-IDENTITY-MISMATCH"):
        service.build_artifact_v2(
            destination=tmp_path / "artifacts" / "x3.json",
            **{**base_kwargs, "target_manifest_id": uuid_mod.uuid4()},
        )
    with pytest.raises(ValidationError, match="ERR-HASH-MISMATCH"):
        service.build_artifact_v2(
            destination=tmp_path / "artifacts" / "x4.json",
            **{**base_kwargs, "target_manifest_sha256": "0" * 64},
        )


def test_same_content_different_manifest_id_refused(tmp_path):
    """T-B6：同内容不同 ID 的 Manifest 不得被视为相同身份."""
    repos, setup, attestation_result = _prepared(tmp_path)
    document = read_json(setup.manifest_result.manifest_path)
    document["manifest_id"] = str(uuid_mod.uuid4())  # 内容不变 → sha 不变
    clone_path = tmp_path / "manifests" / "clone.json"
    clone_path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    assert hashlib.sha256(canonical_json(document["content"])).hexdigest() == (
        setup.manifest_result.manifest_sha256
    )
    with pytest.raises(ValidationError, match="ERR-IDENTITY-MISMATCH"):
        artifact_v2_service(repos).build_artifact_v2(
            prediction_source="S-B",
            scorer_version="sb-member-max-cosine-v1",
            predictions=predictions_from_manifest(repos, setup),
            reference_snapshot_path=setup.snapshot_path,
            reference_snapshot_id=setup.snapshot_result.snapshot_id,
            reference_snapshot_sha256=setup.snapshot_result.snapshot_sha256,
            target_manifest_path=clone_path,  # 同内容、新 ID
            target_manifest_id=setup.manifest_result.manifest_id,  # 旧 ID
            target_manifest_sha256=setup.manifest_result.manifest_sha256,
            isolation_attestation_path=attestation_result.attestation_path,
            destination=tmp_path / "artifacts" / "clone-artifact.json",
        )


def test_relocation_and_envelope_only_tamper(tmp_path):
    """T-B7：等价位移内容哈希不变；Envelope-only 篡改不影响 content 哈希."""
    repos, setup, attestation_result = _prepared(tmp_path)
    result, service = build_artifact_v2(repos, tmp_path, setup, attestation_result)
    relocated = tmp_path / "elsewhere" / "relocated.json"
    relocated.parent.mkdir()
    shutil.copyfile(result.artifact_path, relocated)
    verification = service.verify_artifact_v2(
        relocated,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
    )
    assert verification.ok

    document = read_json(result.artifact_path)
    document["artifact_id"] = str(uuid_mod.uuid4())  # envelope-only
    result.artifact_path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    verification2 = _verify(service, result, setup)
    assert verification2.hash_matches is True  # envelope 不入哈希域

    # content 篡改（**不**重算哈希）→ 哈希失配
    document = read_json(result.artifact_path)
    document["content"]["dataset_version"] = "tampered"
    result.artifact_path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    assert _verify(service, result, setup).hash_matches is False


def test_missing_binding_and_key_omission_rejected(tmp_path):
    """T-B8 + §5.2.7：绑定字段缺失 / 键省略 → 校验失败."""
    repos, setup, attestation_result = _prepared(tmp_path)
    result, service = build_artifact_v2(repos, tmp_path, setup, attestation_result)

    def drop_invariant(document):
        document["content"]["isolation_invariant_sha256"] = None

    rewrite_with_rehash(result.artifact_path, drop_invariant)
    verification = _verify(service, result, setup)
    assert verification.binding_consistent is False

    result2, service2 = build_artifact_v2(
        repos, tmp_path, setup, attestation_result, name="keys.json"
    )

    def drop_key(document):
        del document["content"]["git_commit"]

    rewrite_with_rehash(result2.artifact_path, drop_key)
    assert _verify(service2, result2, setup).keys_valid is False


def test_attestation_bound_to_other_manifest_rejected(tmp_path):
    """Attestation ↔ Artifact 绑定一致性：跨 setup 的 Attestation → 拒绝."""
    repos_a = make_repos(tmp_path / "a")
    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "b").mkdir(exist_ok=True)
    setup_a = full_setup(repos_a, tmp_path / "a")
    setup_b = full_setup(make_repos(tmp_path / "b"), tmp_path / "b")
    attestation_b, _service_b = build_attestation(
        make_repos(tmp_path / "b"), tmp_path / "b", setup_b
    )
    with pytest.raises(ValidationError, match="ERR-IDENTITY-MISMATCH"):
        build_artifact_v2(
            repos_a, tmp_path / "a", setup_a, attestation_b,
            name="cross.json",
        )


def test_unknown_source_rejected(tmp_path):
    """§2 职责：未知 prediction_source → 拒绝."""
    repos, setup, attestation_result = _prepared(tmp_path)
    with pytest.raises(ValidationError, match="ERR-CONTRACT-FIELDS"):
        build_artifact_v2(
            repos, tmp_path, setup, attestation_result,
            source="S-X", name="sx.json",
        )


# ---------------------------------------------------------------------------
# F-1 补充（ORD-2 winning evidence：T-EV-1 正常 / T-EV-2 并列 / T-EV-3 伪造）
# ---------------------------------------------------------------------------


def _setup_two_refs(repos, tmp_path, *, ref_a, ref_b, name="snap6.json"):
    """评估侧 + Manifest + 同一人（张三）两条参考的 Snapshot（孤立 fixture）."""
    eval_side = build_eval_side(repos, tmp_path)
    manifest_result, _service = build_manifest(repos, tmp_path, eval_side)
    ref_run, ref_crun, ref_clusters = _reference_batch(
        repos, tmp_path, [("ra.jpg", [(0.9, ref_a)]), ("rb.jpg", [(0.9, ref_b)])]
    )
    guard = _guard(repos)
    for cluster in sorted(ref_clusters, key=lambda c: c.ordinal):
        guard.confirm_reference_cluster(
            ref_crun.id,
            {cluster.id},
            eval_side.people[0].id,
            eval_side.dataset.id,
            VERSION,
        )
    snapshot_result, snapshot_path = _build_snapshot(
        repos, tmp_path, ref_run, ref_crun, name=name
    )
    return FullSetup(
        eval_side=eval_side,
        manifest_result=manifest_result,
        snapshot_result=snapshot_result,
        snapshot_path=snapshot_path,
        ref_person=eval_side.people[0],
    )


def _item_for(document, cluster_id):
    return next(
        item
        for item in document["content"]["predictions"]
        if item["cluster_id"] == str(cluster_id)
    )


def test_evidence_unique_winner_selected_and_verified(tmp_path):
    """T-EV-1：唯一最大 cosine 的参考观测被选为 evidence；verifier 独立通过."""
    repos = make_repos(tmp_path)
    setup = _setup_two_refs(
        repos, tmp_path, ref_a=(1.0, 0, 0, 0), ref_b=(0, 1.0, 0, 0)
    )
    attestation_result, _s = build_attestation(repos, tmp_path, setup)
    result, service = build_artifact_v2(repos, tmp_path, setup, attestation_result)

    snapshot_document = _snapshot_service(repos).read_document(setup.snapshot_path)
    winner_hash = embedding_sha256((1.0, 0.0, 0.0, 0.0))
    winner_obs = next(
        e["observation_id"]
        for e in snapshot_document.content["entries"]
        if e["embedding_sha256"] == winner_hash
    )
    item = _item_for(read_json(result.artifact_path), setup.clusters[0].id)
    assert item["evidence_winning_reference_observation_id"] == winner_obs
    # 无参考的人物 ⇒ null（source-aware 合法省略；不得凭空推导）
    assert (
        _item_for(read_json(result.artifact_path), setup.clusters[1].id)[
            "evidence_winning_reference_observation_id"
        ]
        is None
    )
    verification = service.verify_artifact_v2(
        result.artifact_path,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
    )
    assert verification.evidence_verification == "pass"
    assert verification.contracts_valid is True
    assert verification.ok


def test_evidence_tie_break_deterministic(tmp_path):
    """T-EV-2：并列最大 cosine → 规范化 observation_id 字符串序最小者.

    顺序无关（反序 entries 独立重推导结果不变）+ 跨重建可复现 + verifier 独立通过。
    """
    repos = make_repos(tmp_path)
    setup = _setup_two_refs(
        repos, tmp_path, ref_a=(1.0, 0, 0, 0), ref_b=(1.0, 0, 0, 0), name="tie6.json"
    )
    attestation_result, _s = build_attestation(repos, tmp_path, setup)
    first, service = build_artifact_v2(
        repos, tmp_path, setup, attestation_result, name="tie_a.json"
    )
    second, _s2 = build_artifact_v2(
        repos, tmp_path, setup, attestation_result, name="tie_b.json"
    )
    snapshot_document = _snapshot_service(repos).read_document(setup.snapshot_path)
    obs_ids = sorted(
        str(e["observation_id"]) for e in snapshot_document.content["entries"]
    )
    assert len(obs_ids) == 2  # 两条并列候选

    item_a = _item_for(read_json(first.artifact_path), setup.clusters[0].id)
    item_b = _item_for(read_json(second.artifact_path), setup.clusters[0].id)
    assert item_a["evidence_winning_reference_observation_id"] == obs_ids[0]
    assert item_a == item_b  # 重建可复现

    # 顺序无关：entries 反序后的独立重推导必须给出同一 winner
    reversed_content = dict(snapshot_document.content)
    reversed_content["entries"] = list(reversed(snapshot_document.content["entries"]))
    reversed_document = SnapshotDocument(
        snapshot_id=snapshot_document.snapshot_id,
        schema_version=snapshot_document.schema_version,
        created_at=snapshot_document.created_at,
        snapshot_sha256=snapshot_document.snapshot_sha256,
        content=reversed_content,
    )
    derived, status = service._derive_evidence(
        top1_person_id=UUID(str(item_a["top1_person_id"])),
        top1_score=item_a["top1_score"],
        observation_id=UUID(str(item_a["observation_id"])),
        photo_id=UUID(str(item_a["photo_id"])),
        snapshot_document=reversed_document,
    )
    assert status == "determined"
    assert derived == obs_ids[0]

    verification = service.verify_artifact_v2(
        first.artifact_path,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
    )
    assert verification.evidence_verification == "pass"


def test_evidence_forgery_rejected_semantically(tmp_path):
    """T-EV-3：伪造 evidence → verifier 语义拒绝（哈希已重算匹配，非哈希失配）.

    子例：① 合法候选但非获胜者；② 不在 Reference Snapshot 中；③ 并列但非规范最小者。
    """
    repos = make_repos(tmp_path)
    setup = _setup_two_refs(
        repos, tmp_path, ref_a=(1.0, 0, 0, 0), ref_b=(0, 1.0, 0, 0),
        name="forgery6.json",
    )
    attestation_result, _s = build_attestation(repos, tmp_path, setup)
    snapshot_document = _snapshot_service(repos).read_document(setup.snapshot_path)
    entries = snapshot_document.content["entries"]
    winner_hash = embedding_sha256((1.0, 0.0, 0.0, 0.0))
    winner_obs = next(
        e["observation_id"] for e in entries if e["embedding_sha256"] == winner_hash
    )
    loser_obs = next(
        e["observation_id"] for e in entries if e["observation_id"] != winner_obs
    )

    def _forge(name: str, forged_value: str):
        result, service = build_artifact_v2(
            repos, tmp_path, setup, attestation_result, name=name
        )

        def mutate(document):
            _item_for(document, setup.clusters[0].id)[
                "evidence_winning_reference_observation_id"
            ] = forged_value

        rewrite_with_rehash(result.artifact_path, mutate)
        return service.verify_artifact_v2(
            result.artifact_path,
            target_manifest_path=setup.manifest_result.manifest_path,
            reference_snapshot_path=setup.snapshot_path,
        )

    # 子例 ①：合法候选（同样属于 top1 人员）但非获胜者
    verification = _forge("forge_a.json", loser_obs)
    assert verification.hash_matches is True  # 哈希已重算——拒绝必须是语义性的
    assert verification.evidence_verification == "fail"
    assert verification.contracts_valid is False

    # 子例 ②：不在 Reference Snapshot 集合中
    verification = _forge("forge_b.json", str(uuid_mod.uuid4()))
    assert verification.hash_matches is True
    assert verification.evidence_verification == "fail"
    assert verification.contracts_valid is False

    # 子例 ③：并列场景下伪造为"非规范最小"候选
    tie_dir = tmp_path / "tie"
    tie_dir.mkdir()
    repos_t = make_repos(tie_dir)
    tie_setup = _setup_two_refs(
        repos_t, tie_dir, ref_a=(1.0, 0, 0, 0), ref_b=(1.0, 0, 0, 0),
        name="t.json",
    )
    attestation_t, _st = build_attestation(repos_t, tie_dir, tie_setup)
    sd_t = _snapshot_service(repos_t).read_document(tie_setup.snapshot_path)
    obs_ids = sorted(str(e["observation_id"]) for e in sd_t.content["entries"])
    non_minimal = obs_ids[1]
    result_t, service_t = build_artifact_v2(
        repos_t, tie_dir, tie_setup, attestation_t, name="forge_tie.json"
    )

    def mutate_tie(document):
        _item_for(document, tie_setup.clusters[0].id)[
            "evidence_winning_reference_observation_id"
        ] = non_minimal

    rewrite_with_rehash(result_t.artifact_path, mutate_tie)
    verification_t = service_t.verify_artifact_v2(
        result_t.artifact_path,
        target_manifest_path=tie_setup.manifest_result.manifest_path,
        reference_snapshot_path=tie_setup.snapshot_path,
    )
    assert verification_t.hash_matches is True
    assert verification_t.evidence_verification == "fail"
    assert verification_t.contracts_valid is False
