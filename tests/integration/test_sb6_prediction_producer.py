"""S-B Prediction Producer 验收测试（任务书 v0.3 §9；Owner 批准的 D-1..D-7）.

全部 fixture 驱动（tmp 隔离库/目录）；生产零接触。D-4 异常以裸 SQL 在隔离
测试库上制造（观测仓储无 update/delete 是生产纪律；测试库允许）。本文件
断言 Producer 当前实现行为与冻结决策——不构成生产可用性或正式工件。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import fields as dc_fields
from pathlib import Path
from uuid import UUID

import pytest

from tests.integration.test_sb1_reference_intake import _evaluation_dataset_id
from tests.integration.test_sb3_reference_eligibility import _guard, _reference_batch
from tests.integration.test_sb4_reference_snapshot import (
    _confirmed_reference,
    _snapshot_service,
)
from tests.integration.test_sb6_common import (
    VERSION,
    build_artifact_v2,
    build_attestation,
    build_eval_side,
    build_manifest,
    full_setup,
    make_repos,
    manifest_service,
    read_json,
    scoring_service,
)

from photo_archiver.application.services.reference_snapshot_service import (
    canonical_json,
    embedding_sha256,
)
from photo_archiver.application.services.sb_prediction_producer import (
    EXCLUSION_DISABLED,
    EXCLUSION_HASH_MISMATCH,
    EXCLUSION_MISSING,
    EXCLUSION_UNREADABLE,
    ProducerExclusion,
    SbPredictionProducer,
)
from photo_archiver.domain import FaceEmbedding
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.infrastructure.cosine_kernel import NumpyCosineSimilarityFactory


def _producer(repos) -> SbPredictionProducer:
    return SbPredictionProducer(
        manifest_service=manifest_service(repos),
        snapshot_service=_snapshot_service(repos),
        cluster_repository=repos.face_clusters,
        observation_repository=repos.face_observations,
        photo_repository=repos.photos,
        similarity_factory=NumpyCosineSimilarityFactory(),
    )


def _produce(repos, setup):
    return _producer(repos).produce(
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
    )


def _multi_ref_setup(repos, tmp_path: Path, refs, *, gt_verdicts=None):
    """评估侧 + Manifest + 多条参考；refs 项 = (person_index, face_vectors, photo_name).

    每项必须为**单脸**调用（``_confirmed_reference`` 仅对单脸执行守卫确认）；
    同一 Person 多条 entry = 对同一 person_index 多次单脸调用。
    """
    eval_side = build_eval_side(repos, tmp_path, gt_verdicts=gt_verdicts)
    manifest_result, _service = build_manifest(repos, tmp_path, eval_side)
    runs, cluster_runs = [], []
    for person_index, face_vectors, photo_name in refs:
        run, cluster_run, _clusters, _person = _confirmed_reference(
            repos, tmp_path, eval_side.people, person_index=person_index,
            face_vectors=face_vectors, photo_name=photo_name,
        )
        runs.append(run)
        cluster_runs.append(cluster_run)
    snapshot_path = tmp_path / "snapshots" / "multi_ref.json"
    snapshot_result = _snapshot_service(repos).build_snapshot(
        _evaluation_dataset_id(repos), VERSION,
        {run.id for run in runs}, {cluster_run.id for cluster_run in cluster_runs},
        destination=snapshot_path,
    )
    return eval_side, manifest_result, snapshot_result, snapshot_path


def _two_plus_one_setup(repos, tmp_path: Path):
    """Person0 两条参考 + Person1 一条参考（D-4 降级场景的公共底座）.

    Person0 的两条 entry = 两次单脸确认调用（守卫仅确认单脸参考）。
    """
    return _multi_ref_setup(
        repos, tmp_path,
        refs=[
            (0, [(0.9, (1.0, 0, 0, 0))], "r1a.jpg"),
            (0, [(0.9, (0, 1.0, 0, 0))], "r1b.jpg"),
            (1, [(0.9, (0, 0, 1.0, 0))], "r2.jpg"),
        ],
    )


def _db_exec(tmp_path: Path, sql: str, params: tuple = ()) -> None:
    conn = sqlite3.connect(tmp_path / "db.sqlite3")
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _table_count(tmp_path: Path, table: str) -> int:
    conn = sqlite3.connect(tmp_path / "db.sqlite3")
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _business_counts(tmp_path: Path) -> dict:
    tables = (
        "face_observations", "cluster_person_assignments", "people",
        "recognition_results", "person_face_embeddings",
    )
    return {table: _table_count(tmp_path, table) for table in tables}


def _other_photo_id(repos, claimed_photo_id: str) -> UUID:
    return next(
        photo.id for photo in repos.photos.list_all()
        if str(photo.id) != claimed_photo_id
    )


def _snapshot_entry(repos, snapshot_path: Path, person_id: UUID | None = None) -> dict:
    document = _snapshot_service(repos).read_document(snapshot_path)
    entries = document.entries
    if person_id is None:
        return entries[0]
    return next(e for e in entries if str(e["person_id"]) == str(person_id))


def _manifest_first_entry(repos, setup) -> dict:
    document = manifest_service(repos).read_document(setup.manifest_result.manifest_path)
    return document.content["entries"][0]


def _record_by_observation(result, observation_id: str):
    return next(
        record for record in result.predictions
        if str(record.observation_id) == observation_id
    )


# ── A. 正常预测与 Person 聚合 ────────────────────────────────────────────────


def test_happy_path_bijection_scores_and_zero_db_writes(tmp_path):
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    counts_before = _business_counts(tmp_path)

    result = _produce(repos, setup)

    assert _business_counts(tmp_path) == counts_before  # 零业务写入（D-5）
    document = manifest_service(repos).read_document(setup.manifest_result.manifest_path)
    entries = document.content["entries"]
    assert result.target_member_count == len(result.predictions) == len(entries)
    produced_keys = {
        (str(record.cluster_id), str(record.observation_id))
        for record in result.predictions
    }
    manifest_keys = {
        (str(entry["cluster_id"]), str(entry["observation_id"])) for entry in entries
    }
    assert produced_keys == manifest_keys  # 与 Manifest 一对一（D-3/架构边界）
    assert result.exclusions == ()
    assert result.candidate_person_count == 1
    for record in result.predictions:
        assert record.top1_person_id == setup.ref_person.id  # 唯一候选
        assert record.top1_score is not None  # K=A+C：S-B predicted 必带分
        assert record.top2_person_id is None and record.top2_score is None


def test_producer_output_flows_through_builder_verifier_and_consumer(tmp_path):
    """Producer → builder → verifier → scoring consumer 全链契约兼容（§6.E）."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result = _produce(repos, setup)
    attestation_result, _svc = build_attestation(repos, tmp_path, setup)
    artifact_result, artifact_service = build_artifact_v2(
        repos, tmp_path, setup, attestation_result,
        predictions=list(result.predictions),
    )
    verification = artifact_service.verify_artifact_v2(
        artifact_result.artifact_path,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
    )
    assert verification.ok is True
    score = scoring_service(repos).score(
        artifact_path=artifact_result.artifact_path,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
        isolation_attestation_path=attestation_result.attestation_path,
    )
    assert score.admission is True
    assert len(score.member_outcomes) == len(result.predictions)


def test_multi_entry_person_scores_max_of_entries(tmp_path):
    repos = make_repos(tmp_path)
    # 同一 Person 的两条 entry = 两次单脸确认调用（守卫仅确认单脸参考）。
    _eval_side, manifest_result, _snapshot_result, snapshot_path = _multi_ref_setup(
        repos, tmp_path,
        refs=[(0, [(0.9, (0.8, 0.6, 0, 0))], "r1a.jpg"),
              (0, [(0.9, (0, 1.0, 0, 0))], "r1b.jpg")],
    )
    result = _producer(repos).produce(
        target_manifest_path=manifest_result.manifest_path,
        reference_snapshot_path=snapshot_path,
    )
    assert result.candidate_person_count == 1
    # 独立内核重算：e1=(1,0,0,0) 对两条参考的 max=0.8；e2=(0,1,0,0)→1.0；e3→0.0
    #（三个期望值互不相同 ⇒ 三条预测分别取到 max 而非均值/质心）。
    lookup = NumpyCosineSimilarityFactory().build([
        FaceEmbedding(vector=(0.8, 0.6, 0, 0)),
        FaceEmbedding(vector=(0, 1.0, 0, 0)),
        FaceEmbedding(vector=(1.0, 0, 0, 0)),
        FaceEmbedding(vector=(0, 1.0, 0, 0)),
        FaceEmbedding(vector=(0, 0, 1.0, 0)),
    ])
    expected = {
        max(lookup.similarity(0, 2), lookup.similarity(1, 2)),
        max(lookup.similarity(0, 3), lookup.similarity(1, 3)),
        max(lookup.similarity(0, 4), lookup.similarity(1, 4)),
    }
    assert expected == {0.8, 1.0, 0.0}
    assert {record.top1_score for record in result.predictions} == expected


def test_person_tie_breaks_by_person_id_string_order(tmp_path):
    repos = make_repos(tmp_path)
    same_face = (0.9, (1.0, 0, 0, 0))
    eval_side, manifest_result, _snapshot_result, snapshot_path = _multi_ref_setup(
        repos, tmp_path,
        refs=[(0, [same_face], "r1.jpg"), (1, [same_face], "r2.jpg")],
    )
    result = _producer(repos).produce(
        target_manifest_path=manifest_result.manifest_path,
        reference_snapshot_path=snapshot_path,
    )
    # D-1 排序范围 = 候选参考 Person（未入围的花名册人员不参与并列决胜）
    ordered = sorted(str(person.id) for person in eval_side.people[:2])
    for record in result.predictions:
        assert str(record.top1_person_id) == ordered[0]  # D-1：并列→person_id 升序
        assert str(record.top2_person_id) == ordered[1]
        assert record.top1_score == record.top2_score  # 量化网格上严格并列


def test_quantized_score_matches_kernel_without_double_rounding(tmp_path):
    repos = make_repos(tmp_path)
    _eval_side, manifest_result, _snapshot_result, snapshot_path = _multi_ref_setup(
        repos, tmp_path, refs=[(0, [(0.9, (1.0, 1.0, 1.0, 0))], "r1.jpg")],
    )
    result = _producer(repos).produce(
        target_manifest_path=manifest_result.manifest_path,
        reference_snapshot_path=snapshot_path,
    )
    lookup = NumpyCosineSimilarityFactory().build([
        FaceEmbedding(vector=(1.0, 1.0, 1.0, 0)),
        FaceEmbedding(vector=(1.0, 0, 0, 0)),
        FaceEmbedding(vector=(0, 1.0, 0, 0)),
        FaceEmbedding(vector=(0, 0, 1.0, 0)),
    ])
    raw = 1.0 / (3 ** 0.5)
    kernel_value = lookup.similarity(0, 1)  # 等分量参考对三个正交目标同为 1/√3
    assert kernel_value == pytest.approx(round(raw, 6))
    scores = {record.top1_score for record in result.predictions}
    assert scores == {kernel_value}  # 落盘值=kernel 量化值（D-7：同一量化分数）
    assert kernel_value == round(raw, 6)
    assert all(round(score, 6) == score for score in scores)  # 无二次舍入空间（D-7）


# ── B. D-2 边界 ──────────────────────────────────────────────────────────────


def test_eligible_zero_returns_no_snapshot_upstream(tmp_path):
    """eligible=0 → 上游 NO SNAPSHOT（规范失败路径），不是空快照/空工件."""
    repos = make_repos(tmp_path)
    build_eval_side(repos, tmp_path)
    run, cluster_run, _clusters = _reference_batch(
        repos, tmp_path, [("r1.jpg", [(0.9, (0, 0, 0, 1.0))])])
    with pytest.raises(ValidationError, match="no eligible snapshot candidates"):
        _snapshot_service(repos).build_snapshot(
            _evaluation_dataset_id(repos), VERSION,
            {run.id}, {cluster_run.id},
            destination=tmp_path / "snapshots" / "never.json",
        )


def test_valid_inputs_with_scoreable_candidates_must_predict(tmp_path):
    """有有效输入与可评分候选 ⇒ 必须产生预测（D-2 正常路径）."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result = _produce(repos, setup)
    assert result.predictions
    assert all(record.top1_person_id is not None for record in result.predictions)
    assert all(record.top1_score is not None for record in result.predictions)


def test_all_candidates_excluded_batch_failure_not_no_candidate(tmp_path):
    """全部候选被排除 ⇒ 整批失败；不得静默输出 no-candidate（D-2/D-4）."""
    repos = make_repos(tmp_path)
    _eval_side, manifest_result, _snapshot_result, snapshot_path = _multi_ref_setup(
        repos, tmp_path, refs=[(0, [(0.9, (1.0, 0, 0, 0))], "r1.jpg")],
    )
    entry = _snapshot_entry(repos, snapshot_path)
    _db_exec(tmp_path, "DELETE FROM face_observations WHERE id = ?",
             (str(entry["observation_id"]),))
    with pytest.raises(ValidationError, match="every reference candidate was excluded"):
        _producer(repos).produce(
            target_manifest_path=manifest_result.manifest_path,
            reference_snapshot_path=snapshot_path,
        )


# ── C. D-4 异常 ──────────────────────────────────────────────────────────────


def test_reference_missing_degrades_and_person_survives(tmp_path):
    repos = make_repos(tmp_path)
    eval_side, manifest_result, _snapshot_result, snapshot_path = _two_plus_one_setup(
        repos, tmp_path)
    victim = _snapshot_entry(repos, snapshot_path, eval_side.people[0].id)
    _db_exec(tmp_path, "DELETE FROM face_observations WHERE id = ?",
             (str(victim["observation_id"]),))
    result = _producer(repos).produce(
        target_manifest_path=manifest_result.manifest_path,
        reference_snapshot_path=snapshot_path,
    )
    assert [exclusion.reason for exclusion in result.exclusions] == [EXCLUSION_MISSING]
    assert result.candidate_person_count == 2  # Person0 经另一条参考幸存
    assert all(record.top1_person_id is not None for record in result.predictions)


def test_reference_hash_mismatch_degrades_with_diagnostic(tmp_path):
    repos = make_repos(tmp_path)
    eval_side, manifest_result, _snapshot_result, snapshot_path = _two_plus_one_setup(
        repos, tmp_path)
    victim = _snapshot_entry(repos, snapshot_path, eval_side.people[0].id)
    _db_exec(tmp_path, "UPDATE face_observations SET embedding = ? WHERE id = ?",
             ("[0.5, 0.5, 0.5, 0.5]", str(victim["observation_id"])))
    result = _producer(repos).produce(
        target_manifest_path=manifest_result.manifest_path,
        reference_snapshot_path=snapshot_path,
    )
    assert [exclusion.reason for exclusion in result.exclusions] == [
        EXCLUSION_HASH_MISMATCH]
    assert result.candidate_person_count == 2
    # 诊断结构固定：身份+原因，不含向量内容（D-4 补充约束）
    assert {f.name for f in dc_fields(ProducerExclusion)} == {
        "person_id", "observation_id", "photo_id", "reason"}


def test_unreadable_reference_embedding_degrades(tmp_path):
    repos = make_repos(tmp_path)
    eval_side, manifest_result, _snapshot_result, snapshot_path = _two_plus_one_setup(
        repos, tmp_path)
    victim = _snapshot_entry(repos, snapshot_path, eval_side.people[0].id)
    _db_exec(tmp_path, "UPDATE face_observations SET embedding = '[]' WHERE id = ?",
             (str(victim["observation_id"]),))
    result = _producer(repos).produce(
        target_manifest_path=manifest_result.manifest_path,
        reference_snapshot_path=snapshot_path,
    )
    assert [exclusion.reason for exclusion in result.exclusions] == [
        EXCLUSION_UNREADABLE]
    assert result.candidate_person_count == 2


def test_disabled_entry_excluded_and_other_person_survives(tmp_path):
    """快照 entry enabled=False → 按冻结评分基元（仅 enabled 参考样本）排除."""
    repos = make_repos(tmp_path)
    eval_side, manifest_result, _snapshot_result, snapshot_path = _multi_ref_setup(
        repos, tmp_path,
        refs=[(0, [(0.9, (1.0, 0, 0, 0))], "r1.jpg"),
              (1, [(0.9, (0, 1.0, 0, 0))], "r2.jpg")],
    )
    victim = _snapshot_entry(repos, snapshot_path, eval_side.people[0].id)
    document = read_json(snapshot_path)
    for entry in document["content"]["entries"]:
        if entry["observation_id"] == victim["observation_id"]:
            entry["enabled"] = False
    content = document["content"]
    document["snapshot_sha256"] = hashlib.sha256(
        canonical_json(content)).hexdigest()
    snapshot_path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8")
    result = _producer(repos).produce(
        target_manifest_path=manifest_result.manifest_path,
        reference_snapshot_path=snapshot_path,
    )
    assert [exclusion.reason for exclusion in result.exclusions] == [EXCLUSION_DISABLED]
    assert result.candidate_person_count == 1
    assert all(
        record.top1_person_id == eval_side.people[1].id
        for record in result.predictions
    )


def test_target_missing_batch_failure(tmp_path):
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    entry = _manifest_first_entry(repos, setup)
    _db_exec(tmp_path, "DELETE FROM face_observations WHERE id = ?",
             (str(entry["observation_id"]),))
    with pytest.raises(ValidationError, match="not resolvable in the pinned cluster run"):
        _produce(repos, setup)


def test_target_identity_mismatch_batch_failure(tmp_path):
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    entry = _manifest_first_entry(repos, setup)
    ref_entry = _snapshot_entry(repos, setup.snapshot_path)
    # 移入参考照片（该照片在本 run 内无观测行，避开 UNIQUE(run, photo, face_index)）
    _db_exec(tmp_path, "UPDATE face_observations SET photo_id = ? WHERE id = ?",
             (str(ref_entry["photo_id"]), str(entry["observation_id"])))
    with pytest.raises(ValidationError, match="ERR-IDENTITY-MISMATCH"):
        _produce(repos, setup)


def test_reference_identity_mismatch_batch_failure(tmp_path):
    """D-4.1 身份矛盾（整批失败）≠ D-4.2 缺失（逐条降级）——两条路径并存."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    entry = _snapshot_entry(repos, setup.snapshot_path)
    other_photo = _other_photo_id(repos, str(entry["photo_id"]))
    _db_exec(tmp_path, "UPDATE face_observations SET photo_id = ? WHERE id = ?",
             (str(other_photo), str(entry["observation_id"])))
    with pytest.raises(ValidationError, match="ERR-IDENTITY-MISMATCH"):
        _produce(repos, setup)


def test_reference_identity_mismatch_in_corrupt_run_fallback_batch_failure(tmp_path):
    """F-1 回归（审计实证场景）：损坏行使 run 级读取失败的回退路径中，
    被移动的参考观测必须触发整批失败——不得误判 missing 并继续产出预测。"""
    repos = make_repos(tmp_path)
    eval_side = build_eval_side(repos, tmp_path)
    manifest_result, _svc = build_manifest(repos, tmp_path, eval_side)
    # run A：两张照片各一脸，同属 person0（守卫仅确认单脸调用→手动确认两簇）
    run_a, crun_a, clusters_a = _reference_batch(repos, tmp_path, [
        ("ra.jpg", [(0.9, (1.0, 0, 0, 0))]),
        ("rb.jpg", [(0.9, (0, 1.0, 0, 0))]),
    ])
    _guard(repos).confirm_reference_cluster(
        crun_a.id, {c.id for c in clusters_a}, eval_side.people[0].id,
        _evaluation_dataset_id(repos), VERSION)
    run_b, crun_b, _cl, _person = _confirmed_reference(
        repos, tmp_path, eval_side.people, person_index=1,
        face_vectors=[(0.9, (0, 0, 1.0, 0))], photo_name="rc.jpg")
    snapshot_path = tmp_path / "snapshots" / "fallback_identity.json"
    _snapshot_service(repos).build_snapshot(
        _evaluation_dataset_id(repos), VERSION,
        {run_a.id, run_b.id}, {crun_a.id, crun_b.id}, destination=snapshot_path)
    obs_a = sorted(repos.face_observations.list_by_run(run_a.id),
                   key=lambda o: str(o.photo_id))
    rc_photo = repos.face_observations.list_by_run(run_b.id)[0].photo_id
    # ra 行损坏（list_by_run(A) 失败→回退）+ rb 行跨照片移动（身份矛盾）
    _db_exec(tmp_path, "UPDATE face_observations SET embedding = '[]' WHERE id = ?",
             (str(obs_a[0].id),))
    _db_exec(tmp_path, "UPDATE face_observations SET photo_id = ? WHERE id = ?",
             (str(rc_photo), str(obs_a[1].id)))
    with pytest.raises(ValidationError, match="ERR-IDENTITY-MISMATCH|ERR-UNPROVABLE"):
        _producer(repos).produce(
            target_manifest_path=manifest_result.manifest_path,
            reference_snapshot_path=snapshot_path,
        )


def test_reference_moved_across_run_identity_batch_failure(tmp_path):
    """F-1 回归（正常路径 run 移动盲区）：观测移至他 run ⇒ 身份矛盾整批失败."""
    repos = make_repos(tmp_path)
    eval_side, manifest_result, _snapshot_result, snapshot_path = _multi_ref_setup(
        repos, tmp_path,
        refs=[(0, [(0.9, (1.0, 0, 0, 0))], "r1.jpg"),
              (1, [(0.9, (0, 1.0, 0, 0))], "r2.jpg")])
    document = _snapshot_service(repos).read_document(snapshot_path)
    person0_entry = next(e for e in document.entries
                         if str(e["person_id"]) == str(eval_side.people[0].id))
    person1_entry = next(e for e in document.entries
                         if str(e["person_id"]) == str(eval_side.people[1].id))
    other_run = person1_entry["provenance"]["recognition_run_id"]
    # 移入 person1 的 run、照片不变（该 (run, photo) 无既有行，避开 UNIQUE 冲突）
    _db_exec(tmp_path, "UPDATE face_observations SET run_id = ? WHERE id = ?",
             (str(other_run), str(person0_entry["observation_id"])))
    with pytest.raises(ValidationError, match="ERR-IDENTITY-MISMATCH"):
        _producer(repos).produce(
            target_manifest_path=manifest_result.manifest_path,
            reference_snapshot_path=snapshot_path,
        )


def test_identity_search_unreadable_source_fails_closed(tmp_path):
    """Owner 整改令：身份搜索遇不可读源 ⇒ ERR-UNPROVABLE 整批失败（不降级）.

    person0 的观测被删除（真缺失）触发搜索；person1 的观测行损坏位于搜索
    必经之路上——身份完整性无法确认，必须 fail-closed 终止产出。
    """
    repos = make_repos(tmp_path)
    eval_side, manifest_result, _snapshot_result, snapshot_path = _multi_ref_setup(
        repos, tmp_path,
        refs=[(0, [(0.9, (1.0, 0, 0, 0))], "r1.jpg"),
              (1, [(0.9, (0, 1.0, 0, 0))], "r2.jpg")])
    document = _snapshot_service(repos).read_document(snapshot_path)
    person0_entry = next(e for e in document.entries
                         if str(e["person_id"]) == str(eval_side.people[0].id))
    person1_entry = next(e for e in document.entries
                         if str(e["person_id"]) == str(eval_side.people[1].id))
    _db_exec(tmp_path, "DELETE FROM face_observations WHERE id = ?",
             (str(person0_entry["observation_id"]),))
    _db_exec(tmp_path, "UPDATE face_observations SET embedding = '[]' WHERE id = ?",
             (str(person1_entry["observation_id"]),))
    with pytest.raises(ValidationError, match="identity search"):
        _producer(repos).produce(
            target_manifest_path=manifest_result.manifest_path,
            reference_snapshot_path=snapshot_path,
        )


def test_mixed_dimensions_batch_failure(tmp_path):
    repos = make_repos(tmp_path)
    eval_side, manifest_result, _snapshot_result, snapshot_path = _two_plus_one_setup(
        repos, tmp_path)
    victim = _snapshot_entry(repos, snapshot_path, eval_side.people[1].id)
    short_vector = (1.0, 0.0)
    _db_exec(tmp_path, "UPDATE face_observations SET embedding = ? WHERE id = ?",
             ("[1.0, 0.0]", str(victim["observation_id"])))
    # 同步冻结 entry 哈希——否则 D-4.3 哈希降级先于 D-4.4 维度检查发生；
    # 本用例构造"冻结时即存在混维"的边界场景，使混维到达整批检查。
    document = read_json(snapshot_path)
    for entry in document["content"]["entries"]:
        if entry["observation_id"] == victim["observation_id"]:
            entry["embedding_sha256"] = embedding_sha256(short_vector)
    content = document["content"]
    document["snapshot_sha256"] = hashlib.sha256(canonical_json(content)).hexdigest()
    snapshot_path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8")
    with pytest.raises(ValidationError, match="mixed embedding dimensions"):
        _producer(repos).produce(
            target_manifest_path=manifest_result.manifest_path,
            reference_snapshot_path=snapshot_path,
        )


def test_zero_vector_target_scores_zero_still_predicted(tmp_path):
    """零向量目标：kernel 语义 0.0（D-7）——仍产生 predicted，而非 no-candidate."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    entry = _manifest_first_entry(repos, setup)
    _db_exec(tmp_path, "UPDATE face_observations SET embedding = ? WHERE id = ?",
             ("[0.0, 0.0, 0.0, 0.0]", str(entry["observation_id"])))
    result = _produce(repos, setup)
    record = _record_by_observation(result, str(entry["observation_id"]))
    assert record.top1_person_id == setup.ref_person.id
    assert record.top1_score == 0.0
    assert record.top1_score is not None  # predicted 而非 no-candidate


# ── D/E. 确定性与契约 ────────────────────────────────────────────────────────


def test_determinism_same_inputs_same_predictions(tmp_path):
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    first = _produce(repos, setup)
    second = _produce(repos, setup)
    assert first.predictions == second.predictions
    assert first.exclusions == second.exclusions
    assert first.manifest_sha256 == second.manifest_sha256
