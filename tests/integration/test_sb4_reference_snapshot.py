"""S-B-4 Reference Snapshot acceptance tests（任务书 §25 全矩阵）.

复用 S-B-3 测试基建；隔离 SQLite 临时库 + 临时目录，生产库零接触。

覆盖：构建（单/多/多脸/单参考/多参考/coverage-only）、provenance（缺失/
混合/业务 PFE 排除）、完整性（损坏 embedding/哈希篡改/漂移检测）、隔离
（复用 S-B-3 E-05）、canonical 确定性（同输入同哈希、条目序无关）、
不可变（覆盖拒绝）、失败原子性（坏条目 → 无半成品发布）。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from tests.integration.test_sb3_reference_eligibility import (
    _build_three_person_evaluation,
    _eligibility,
    _evaluation_dataset_id,
    _guard,
)

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application import ReferenceSnapshotService
from photo_archiver.application.services.reference_snapshot_service import (
    SNAPSHOT_SCHEMA_VERSION,
    canonical_json,
    embedding_sha256,
)
from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR
from photo_archiver.domain.exceptions import (
    SnapshotAlreadyExistsError,
    ValidationError,
)
from photo_archiver.infrastructure.filesystem.snapshot_store import (
    FilesystemSnapshotStore,
)

VERSION = "pilot-sb3"


def _snapshot_service(repos) -> ReferenceSnapshotService:
    return ReferenceSnapshotService(
        eligibility_service=_eligibility(repos),
        reference_intake=_guard(repos),
        snapshot_store=FilesystemSnapshotStore(),
        observation_repository=repos.face_observations,
        photo_repository=repos.photos,
    )


def _confirmed_reference(repos, tmp_path: Path, people, person_index: int = 0,
                         face_vectors=None, photo_name: str = "r1.jpg"):
    """守卫路径确认一条参考（默认 frozen person[0]，单脸）。"""
    from tests.integration.test_sb3_reference_eligibility import (
        VERSION as _VERSION,
    )
    import tests.integration.test_sb3_reference_eligibility as sb3

    if face_vectors is None:
        face_vectors = [(0.9, (0, 0, 0, 1.0))]
    run, cluster_run, clusters = sb3._reference_batch(
        repos, tmp_path, [(photo_name, face_vectors)])
    person = people[person_index]
    target_cluster = clusters[0] if len(face_vectors) == 1 else clusters
    if len(face_vectors) == 1:
        _guard(repos).confirm_reference_cluster(
            cluster_run.id, {target_cluster.id}, person.id,
            _evaluation_dataset_id(repos), _VERSION)
    return run, cluster_run, clusters, person


def _build(repos, tmp_path: Path, run, cluster_run, scope="eligible",
           name="snapshot.json"):
    destination = tmp_path / "snapshots" / name
    return _snapshot_service(repos).build_snapshot(
        _evaluation_dataset_id(repos), VERSION, {run.id}, {cluster_run.id},
        population_scope=scope, destination=destination,
    ), destination


def test_build_single_eligible_snapshot(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    run, cluster_run, _clusters, _person = _confirmed_reference(repos, tmp_path, people)
    result, destination = _build(repos, tmp_path, run, cluster_run)
    assert destination.is_file()
    assert result.entry_count == 1 and result.person_count == 1
    assert result.snapshot_sha256 == hashlib.sha256(
        canonical_json(json.loads(destination.read_text(encoding="utf-8"))["content"])
    ).hexdigest()
    document = json.loads(destination.read_text(encoding="utf-8"))
    assert document["schema_version"] == SNAPSHOT_SCHEMA_VERSION == "reference-snapshot-v1"
    entry = document["content"]["entries"][0]
    assert entry["enabled"] is True
    assert entry["provenance"]["assignment_ids"]
    assert entry["provenance"]["eligibility_decision"] == "ELIGIBLE"
    # embedding_sha256 = canonical embedding bytes 的哈希（逐位正确）
    pfe = [s for p in people for s in repos.person_face_samples.list_by_person(p.id)][0]
    assert entry["embedding_sha256"] == embedding_sha256(pfe.embedding.vector)
    verification = _snapshot_service(repos).verify_snapshot(destination)
    assert verification.ok


def test_snapshot_determinism_same_input_same_hash(tmp_path):
    """§22：相同冻结输入 → snapshot_id 可变，但内容哈希逐字节稳定。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    run, cluster_run, _clusters, _person = _confirmed_reference(repos, tmp_path, people)
    result_a, path_a = _build(repos, tmp_path, run, cluster_run, name="a.json")
    result_b, path_b = _build(repos, tmp_path, run, cluster_run, name="b.json")
    assert result_a.snapshot_id != result_b.snapshot_id  # 身份 UUID 每次可变
    assert result_a.snapshot_sha256 == result_b.snapshot_sha256  # 内容哈希稳定
    content_a = json.loads(path_a.read_text(encoding="utf-8"))["content"]
    content_b = json.loads(path_b.read_text(encoding="utf-8"))["content"]
    assert content_a == content_b


def test_canonical_entry_order_independent(tmp_path):
    """§12：条目输入顺序不影响 canonical 输出（builder 排序后序列化）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    run, cluster_run, _clusters, _person = _confirmed_reference(
        repos, tmp_path, people,
        face_vectors=[(0.9, (0, 0, 0, 1.0, 0, 0, 0, 0)),
                      (0.9, (0, 1.0, 0, 0, 0, 0, 0, 0))],
        photo_name="two.jpg")
    # 双脸 → 两个簇 → 分别确认给两个 frozen persons → 2 entries
    from tests.integration.test_sb3_reference_eligibility import VERSION as _V
    rclusters = sorted(
        repos.face_clusters.list_clusters(cluster_run.id), key=lambda c: c.ordinal)
    _guard(repos).confirm_reference_cluster(
        cluster_run.id, {rclusters[0].id}, people[0].id,
        _evaluation_dataset_id(repos), _V)
    _guard(repos).confirm_reference_cluster(
        cluster_run.id, {rclusters[1].id}, people[1].id,
        _evaluation_dataset_id(repos), _V)
    result, destination = _build(repos, tmp_path, run, cluster_run)
    assert result.entry_count == 2
    entries = json.loads(destination.read_text(encoding="utf-8"))["content"]["entries"]
    keys = [(e["person_id"], e["photo_id"], e["observation_id"]) for e in entries]
    assert keys == sorted(keys)  # canonical 序：person → photo → observation
    assert len({e["photo_id"] for e in entries}) == 1  # 同 photo 两条合法 entry


def test_coverage_only_scope_semantics(tmp_path):
    """§7/§19：scope 显式；COVERAGE_ONLY 不偷换成 ELIGIBLE。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, _people = _build_three_person_evaluation(repos, tmp_path)
    repos.people.add(
        __import__("photo_archiver.domain", fromlist=["Person"]).Person(name="编外甲"))
    outsider = [p for p in repos.people.list_all() if p.name == "编外甲"][0]
    run, cluster_run, _clusters, _person = _confirmed_reference(
        repos, tmp_path, [outsider], person_index=0)
    # scope=eligible：编外人物的样本是 COVERAGE_ONLY → 无 ELIGIBLE 候选 → 拒绝
    with pytest.raises(ValidationError, match="no eligible snapshot candidates"):
        _build(repos, tmp_path, run, cluster_run, scope="eligible")
    # scope=eligible-and-coverage-only：合法候选 → 构建，scope 入 metadata（哈希域）
    result, destination = _build(
        repos, tmp_path, run, cluster_run, scope="eligible-and-coverage-only")
    assert result.entry_count == 1
    document = json.loads(destination.read_text(encoding="utf-8"))
    assert document["content"]["population_scope"] == "eligible-and-coverage-only"
    assert (document["content"]["entries"][0]["provenance"]
            ["eligibility_decision"] == "COVERAGE_ONLY")


def test_provenance_missing_and_mixed_excluded(tmp_path):
    """P-03：E-02 失败（无确认）与 OWNER-GATE（指定不全）都不是候选。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    # 无人工确认的参考照片（识别+聚类但未确认）→ E-02 fail → 无候选
    run, cluster_run, _clusters, _person = _confirmed_reference(
        repos, tmp_path, people, confirm=False) if False else (None, None, None, None)
    import tests.integration.test_sb3_reference_eligibility as sb3
    run, cluster_run, _clusters = sb3._reference_batch(
        repos, tmp_path, [("unconfirmed.jpg", [(0.9, (0, 0, 0, 1.0))])])
    with pytest.raises(ValidationError, match="no eligible snapshot candidates"):
        _build(repos, tmp_path, run, cluster_run)
    # 指定不全（另一聚类 run 未指定）→ OWNER-GATE → 不是候选
    run2, crun2, _c2 = sb3._reference_batch(
        repos, tmp_path, [("mixed.jpg", [(0.9, (0, 1.0, 0, 1.0))])])
    person = people[0]
    other_crun = sb3._cluster(repos, run2)
    from photo_archiver.application.commands.pairing import AssignClusterPersonCommand
    _workbench(repos).assign_person(AssignClusterPersonCommand(
        cluster_id=repos.face_clusters.list_clusters(other_crun.id)[0].id,
        person_id=person.id), actor=HUMAN_ACTOR)
    # 指定集 = 首批（unconfirmed）聚类 run——不含 mixed 样本 →
    # run 指定 + 簇未指定 = 混合溯源 → OWNER-GATE → 不是候选。
    with pytest.raises(ValidationError, match="no eligible snapshot candidates"):
        _build(repos, tmp_path, run2, cluster_run)


def test_generic_business_pfe_never_snapshotted(tmp_path):
    """P-01：评估照片上的业务 PFE（INELIGIBLE）不进入任何 scope 的 snapshot。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, e_crun, e_clusters, _people = _build_three_person_evaluation(repos, tmp_path)
    from photo_archiver.application.commands.pairing import AssignClusterPersonCommand
    _workbench(repos).assign_person(AssignClusterPersonCommand(
        cluster_id=e_clusters[0].id,
        person_id=[p for p in repos.people.list_all() if p.name == "王五"][0].id),
        actor=HUMAN_ACTOR)
    # 仅存在这一条 INELIGIBLE 业务样本 → 两个 scope 均无候选
    with pytest.raises(ValidationError, match="no eligible snapshot candidates"):
        _build(repos, tmp_path, _run, e_crun, scope="eligible-and-coverage-only")


def _workbench(repos):
    from photo_archiver.application import PairingWorkbenchService
    from photo_archiver.application.services.projection_reconciler import (
        ProjectionReconciler,
    )
    return PairingWorkbenchService(
        repos.cluster_assignments, repos.face_clusters, repos.face_observations,
        repos.people, repos.recognition, repos.person_face_samples,
        reconciler=ProjectionReconciler(
            recognition_repository=repos.recognition,
            assignment_repository=repos.cluster_assignments,
            cluster_repository=repos.face_clusters,
            observation_repository=repos.face_observations))


def test_embedding_drift_detection(tmp_path):
    """§23：snapshot 后 embedding 漂移 → cross_check 失败（文件本身不变）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    run, cluster_run, _clusters, _person = _confirmed_reference(repos, tmp_path, people)
    result, destination = _build(repos, tmp_path, run, cluster_run)
    assert _snapshot_service(repos).verify_snapshot(
        destination, cross_check_current_state=True).ok
    # 篡改现状：改写该 observation 的 embedding（漂移）
    obs_id = json.loads(destination.read_text(encoding="utf-8"))["content"]["entries"][0][
        "observation_id"]
    con = sqlite3.connect(str(tmp_path / "db.sqlite3"))
    con.execute(
        "UPDATE face_observations SET embedding = ? WHERE id = ?",
        ("[0.1, 0.2, 0.3, 0.4]", obs_id))
    con.commit()
    con.close()
    verification = _snapshot_service(repos).verify_snapshot(
        destination, cross_check_current_state=True)
    assert verification.hash_matches  # 文件内部一致性不受影响
    assert verification.embedding_drift_free is False
    assert not verification.ok


def test_verify_tampered_content(tmp_path):
    """篡改 snapshot 文件内容 → 哈希失配 → 拒绝。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    run, cluster_run, _clusters, _person = _confirmed_reference(repos, tmp_path, people)
    _result, destination = _build(repos, tmp_path, run, cluster_run)
    document = json.loads(destination.read_text(encoding="utf-8"))
    document["content"]["entries"][0]["quality_score"] = 0.123456
    destination.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    verification = _snapshot_service(repos).verify_snapshot(destination)
    assert verification.hash_matches is False
    assert not verification.ok


def test_immutability_overwrite_rejected(tmp_path):
    """§15/D-SB-6：覆盖已存在 snapshot → fail-closed，旧内容原样。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    run, cluster_run, _clusters, _person = _confirmed_reference(repos, tmp_path, people)
    result, destination = _build(repos, tmp_path, run, cluster_run)
    before = destination.read_bytes()
    store = FilesystemSnapshotStore()
    with pytest.raises(SnapshotAlreadyExistsError):
        store.write_atomic(destination, b"tampered")
    assert destination.read_bytes() == before
    # 服务/模型无 update/delete API（结构性不可变）
    service = _snapshot_service(repos)
    assert not any(name.startswith(("update_", "delete_", "mutate_"))
                   for name in dir(service))


def test_failure_atomicity_no_partial_snapshot(tmp_path):
    """§21：坏条目（unreadable person）→ build 中止 → 无半成品发布。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    run, cluster_run, _clusters, _person = _confirmed_reference(repos, tmp_path, people)
    # 注入 unreadable person（损坏 embedding 行）→ build 前置拒绝
    from tests.integration.test_sb3_reference_eligibility import VERSION as _V
    import uuid as u
    con = sqlite3.connect(str(tmp_path / "db.sqlite3"))
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute(
        "INSERT INTO person_face_embeddings (id, person_id, observation_id,"
        " embedding, quality_score, enabled, created_at) VALUES (?, ?, ?, ?, 0.5, 1, ?)",
        (str(u.uuid4()), str(people[2].id),
         str(repos.face_clusters.list_members(cluster_run.id)[0].observation_id),
         "not-json", __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()))
    con.commit()
    con.close()
    destination = tmp_path / "snapshots" / "never.json"
    with pytest.raises(ValidationError, match="DO NOT SNAPSHOT"):
        _snapshot_service(repos).build_snapshot(
            _evaluation_dataset_id(repos), _V, {run.id}, {cluster_run.id},
            population_scope="eligible-and-coverage-only", destination=destination)
    assert not destination.exists()  # 无半成品
    assert not (tmp_path / "snapshots" / "never.json.part").exists()
    # 移除损坏行后同一 destination 可成功构建（无残留阻碍）
    con = sqlite3.connect(str(tmp_path / "db.sqlite3"))
    con.execute("DELETE FROM person_face_embeddings WHERE embedding = 'not-json'")
    con.commit()
    con.close()
    result, destination = _build(repos, tmp_path, run, cluster_run,
                                 scope="eligible-and-coverage-only")
    assert result.entry_count == 1
