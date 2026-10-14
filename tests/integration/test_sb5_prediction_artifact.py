"""S-B-5 Prediction Artifact acceptance tests（任务书 §33 全矩阵）.

复用 S-B-4 测试基建；隔离 SQLite 临时库 + 临时目录，生产库零接触。
"""

from __future__ import annotations

import json
import uuid as uuid_mod
from pathlib import Path

import pytest

import sqlite3

from tests.integration.test_sb3_reference_eligibility import (
    _evaluation_dataset_id,
    _guard,
)
from tests.integration.test_sb4_reference_snapshot import (
    _build as _build_snapshot,
    _build_three_person_evaluation,
    _snapshot_service,
)

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application import PredictionArtifactService
from photo_archiver.application.services.prediction_artifact_service import (
    PredictionRecord,
)
from photo_archiver.domain.exceptions import (
    SnapshotAlreadyExistsError,
    ValidationError,
)
from photo_archiver.infrastructure.filesystem.snapshot_store import (
    FilesystemSnapshotStore,
)

VERSION = "pilot-sb3"


def _artifact_service(repos) -> PredictionArtifactService:
    return PredictionArtifactService(
        snapshot_service=_snapshot_service(repos),
        artifact_store=FilesystemSnapshotStore(),
    )


def _setup_with_snapshot(repos, tmp_path: Path, scope: str = "eligible"):
    """构建一个快照（默认 eligible scope、frozen person[0] 单脸参考）。"""
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    from tests.integration.test_sb4_reference_snapshot import (
        _confirmed_reference,
    )

    run, cluster_run, _clusters, _person = _confirmed_reference(
        repos, tmp_path, people)
    result, destination = _build_snapshot(
        repos, tmp_path, run, cluster_run, scope=scope)
    return result, destination, people


def _predictions_from_snapshot(repos, snapshot_path: Path, score=0.9, rank=1):
    document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    return [
        PredictionRecord(
            person_id=uuid_mod.UUID(e["person_id"]),
            observation_id=uuid_mod.UUID(e["observation_id"]),
            photo_id=uuid_mod.UUID(e["photo_id"]),
            predicted_person_id=uuid_mod.UUID(e["person_id"]),
            score=score,
            rank=rank,
        )
        for e in document["content"]["entries"]
    ], document


def _build_artifact(repos, tmp_path: Path, snapshot_result, snapshot_path,
                    predictions, source="S-B", name="artifact.json", **kwargs):
    return _artifact_service(repos).build_artifact(
        prediction_source=source,
        prediction_method="sb-member-max-cosine-v1",
        prediction_method_version="sb-member-max-cosine-v1",
        predictions=predictions,
        reference_snapshot_path=(snapshot_path if source == "S-B" else None),
        reference_snapshot_id=(snapshot_result.snapshot_id if source == "S-B"
                               else None),
        reference_snapshot_sha256=(snapshot_result.snapshot_sha256
                                   if source == "S-B" else None),
        destination=tmp_path / "artifacts" / name,
        **kwargs,
    ), tmp_path / "artifacts" / name


def test_sb_artifact_binding_valid(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(repos, tmp_path)
    predictions, _document = _predictions_from_snapshot(repos, snapshot_path)
    result, destination = _build_artifact(
        repos, tmp_path, snapshot_result, snapshot_path, predictions)
    assert destination.is_file()
    assert result.prediction_source == "S-B"
    assert result.prediction_count == 1
    document = json.loads(destination.read_text(encoding="utf-8"))
    content = document["content"]
    assert content["reference_snapshot_id"] == str(snapshot_result.snapshot_id)
    assert content["reference_snapshot_sha256"] == snapshot_result.snapshot_sha256
    assert content["threshold"] is None  # §19：Owner 未批准前恒 NULL
    assert content["score_semantics"]["method"] == "sb-member-max-cosine-v1"
    verification = _artifact_service(repos).verify_artifact(
        destination, reference_snapshot_path=snapshot_path)
    assert verification.ok


def test_sb_wrong_snapshot_id_rejected(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(repos, tmp_path)
    predictions, _document = _predictions_from_snapshot(repos, snapshot_path)
    with pytest.raises(ValidationError, match="ID mismatch"):
        _artifact_service(repos).build_artifact(
            prediction_source="S-B",
            prediction_method="sb-member-max-cosine-v1",
            prediction_method_version="v1",
            predictions=predictions,
            reference_snapshot_path=snapshot_path,
            reference_snapshot_id=uuid_mod.uuid4(),  # 错误 ID
            reference_snapshot_sha256=snapshot_result.snapshot_sha256,
            destination=tmp_path / "artifacts" / "x.json",
        )


def test_sb_wrong_snapshot_sha_rejected(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(repos, tmp_path)
    predictions, _document = _predictions_from_snapshot(repos, snapshot_path)
    with pytest.raises(ValidationError, match="SHA256 mismatch"):
        _artifact_service(repos).build_artifact(
            prediction_source="S-B",
            prediction_method="sb-member-max-cosine-v1",
            prediction_method_version="v1",
            predictions=predictions,
            reference_snapshot_path=snapshot_path,
            reference_snapshot_id=snapshot_result.snapshot_id,
            reference_snapshot_sha256="0" * 64,  # 错误哈希
            destination=tmp_path / "artifacts" / "x.json",
        )


def test_sb_tampered_snapshot_rejected(tmp_path):
    """快照被篡改 → 内部哈希失配 → artifact 构建前置拒绝（§28）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(repos, tmp_path)
    predictions, document = _predictions_from_snapshot(repos, snapshot_path)
    tampered = json.loads(snapshot_path.read_text(encoding="utf-8"))
    tampered["content"]["entries"][0]["quality_score"] = 0.42
    snapshot_path.write_text(
        json.dumps(tampered, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8")
    with pytest.raises(ValidationError, match="failed verification"):
        _build_artifact(repos, tmp_path, snapshot_result, snapshot_path, predictions)


def test_sb_missing_snapshot_rejected(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, _people = _build_three_person_evaluation(repos, tmp_path)
    with pytest.raises(ValidationError, match="requires a reference snapshot"):
        _artifact_service(repos).build_artifact(
            prediction_source="S-B",
            prediction_method="sb-member-max-cosine-v1",
            prediction_method_version="v1",
            predictions=[PredictionRecord(
                person_id=uuid_mod.uuid4(), observation_id=uuid_mod.uuid4(),
                photo_id=uuid_mod.uuid4(), predicted_person_id=uuid_mod.uuid4(),
                score=0.9, rank=1)],
            reference_snapshot_path=None,
            reference_snapshot_id=None,
            reference_snapshot_sha256=None,
            destination=tmp_path / "artifacts" / "x.json",
        )


def test_sa_sc_null_binding_enforced(tmp_path):
    """§7：S-A/S-C 携带 arbitrary snapshot 绑定 → 拒绝；合法 S-C → NULL 绑定。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(repos, tmp_path)
    predictions, _document = _predictions_from_snapshot(repos, snapshot_path)
    with pytest.raises(ValidationError, match="NULL reference snapshot"):
        _artifact_service(repos).build_artifact(
            prediction_source="S-A",
            prediction_method="sa-member-loo-in-sample-v1",
            prediction_method_version="v1",
            predictions=predictions,
            reference_snapshot_path=snapshot_path,  # 禁止
            reference_snapshot_id=snapshot_result.snapshot_id,  # 禁止
            reference_snapshot_sha256=snapshot_result.snapshot_sha256,  # 禁止
            destination=tmp_path / "artifacts" / "x.json",
            entry_count=1, person_count=1,
        )
    # 合法 S-C：无快照绑定 + 调用方计数 → 构建，binding=NULL
    result, destination = _build_artifact(
        repos, tmp_path, snapshot_result, snapshot_path,
        predictions=predictions, source="S-C",
        prediction_method_override=None if False else None,
    ) if False else (
        _artifact_service(repos).build_artifact(
            prediction_source="S-C",
            prediction_method="sc-ordered-deterministic-v1",
            prediction_method_version="v1",
            predictions=predictions,
            reference_snapshot_path=None,
            reference_snapshot_id=None,
            reference_snapshot_sha256=None,
            destination=tmp_path / "artifacts" / "sc.json",
            dataset_id=uuid_mod.uuid4(), dataset_version="round-1",
            input_population_scope="eligible",
            entry_count=1, person_count=1,
        ),
        tmp_path / "artifacts" / "sc.json")
    document = json.loads(destination.read_text(encoding="utf-8"))
    assert document["content"]["reference_snapshot_id"] is None
    assert document["content"]["reference_snapshot_sha256"] is None
    assert document["content"]["prediction_source"] == "S-C"


def test_sb_without_real_scoring_not_creatable(tmp_path):
    """§12：快照在但无 scoring 输出（空 predictions）→ NOT CREATABLE。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(repos, tmp_path)
    with pytest.raises(ValidationError, match="NOT CREATABLE|no predictions"):
        _artifact_service(repos).build_artifact(
            prediction_source="S-B",
            prediction_method="sb-member-max-cosine-v1",
            prediction_method_version="v1",
            predictions=[],  # 无 scoring 输出
            reference_snapshot_path=snapshot_path,
            reference_snapshot_id=snapshot_result.snapshot_id,
            reference_snapshot_sha256=snapshot_result.snapshot_sha256,
            destination=tmp_path / "artifacts" / "x.json",
        )


def test_scope_recorded_exactly_and_not_relabeled(tmp_path):
    """§10：scope 从快照逐字记录；COVERAGE_ONLY 不改标。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(
        repos, tmp_path, scope="eligible-and-coverage-only")
    predictions, snapshot_document = _predictions_from_snapshot(repos, snapshot_path)
    assert snapshot_document["content"]["population_scope"] == "eligible-and-coverage-only"
    result, destination = _build_artifact(
        repos, tmp_path, snapshot_result, snapshot_path, predictions)
    document = json.loads(destination.read_text(encoding="utf-8"))
    assert (document["content"]["input_population_scope"]
            == "eligible-and-coverage-only")  # 逐字记录
    for entry in document["content"]["predictions"]:
        assert entry["prediction_type"] in ("predicted", "no-candidate")


def test_determinism_same_input_same_hash(tmp_path):
    """§21：相同输入 → content 哈希相同、artifact_id 不同。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(repos, tmp_path)
    predictions, _document = _predictions_from_snapshot(repos, snapshot_path)
    result_a, path_a = _build_artifact(
        repos, tmp_path, snapshot_result, snapshot_path, predictions, name="a.json")
    result_b, path_b = _build_artifact(
        repos, tmp_path, snapshot_result, snapshot_path, predictions, name="b.json")
    assert result_a.artifact_id != result_b.artifact_id
    assert result_a.artifact_sha256 == result_b.artifact_sha256
    content_a = json.loads(path_a.read_text(encoding="utf-8"))["content"]
    content_b = json.loads(path_b.read_text(encoding="utf-8"))["content"]
    assert content_a == content_b


def test_serialization_order_and_types(tmp_path):
    """§14：条目乱序输入 → canonical 输出相同；null/bool/unicode 稳定。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(
        repos, tmp_path, scope="eligible-and-coverage-only")
    predictions, _document = _predictions_from_snapshot(repos, snapshot_path)
    import random

    shuffled = list(predictions)
    random.shuffle(shuffled)
    result_a, path_a = _build_artifact(
        repos, tmp_path, snapshot_result, snapshot_path, predictions, name="o1.json")
    result_b, path_b = _build_artifact(
        repos, tmp_path, snapshot_result, snapshot_path, shuffled, name="o2.json")
    assert result_a.artifact_sha256 == result_b.artifact_sha256
    entries = json.loads(path_a.read_text(encoding="utf-8"))["content"]["predictions"]
    keys = [(e["person_id"], e["observation_id"], e["photo_id"]) for e in entries]
    assert keys == sorted(keys)  # canonical 序
    document = json.loads(path_a.read_text(encoding="utf-8"))
    entry = document["content"]["predictions"][0]
    assert entry["score"] == 0.9 and entry["rank"] == 1  # 数值稳定
    assert isinstance(entry["prediction_type"], str)


def test_orphan_prediction_and_photo_mismatch_rejected(tmp_path):
    """§22/§23：orphan prediction / photo 不匹配 → fail-closed。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(repos, tmp_path)
    predictions, document = _predictions_from_snapshot(repos, snapshot_path)
    orphan = PredictionRecord(
        person_id=uuid_mod.uuid4(), observation_id=uuid_mod.uuid4(),
        photo_id=uuid_mod.uuid4(), predicted_person_id=uuid_mod.uuid4(),
        score=0.9, rank=1)
    with pytest.raises(ValidationError, match="orphan"):
        _artifact_service(repos).build_artifact(
            prediction_source="S-B",
            prediction_method="sb-member-max-cosine-v1",
            prediction_method_version="v1",
            predictions=predictions + [orphan],
            reference_snapshot_path=snapshot_path,
            reference_snapshot_id=snapshot_result.snapshot_id,
            reference_snapshot_sha256=snapshot_result.snapshot_sha256,
            destination=tmp_path / "artifacts" / "x.json",
        )
    # photo 不匹配（同 person/observation，错误 photo）
    e = document["content"]["entries"][0]
    mismatched = PredictionRecord(
        person_id=uuid_mod.UUID(e["person_id"]),
        observation_id=uuid_mod.UUID(e["observation_id"]),
        photo_id=uuid_mod.uuid4(),  # 错误
        predicted_person_id=uuid_mod.UUID(e["person_id"]),
        score=0.9, rank=1)
    with pytest.raises(ValidationError, match="photo_id does not match"):
        _artifact_service(repos).build_artifact(
            prediction_source="S-B",
            prediction_method="sb-member-max-cosine-v1",
            prediction_method_version="v1",
            predictions=[mismatched],
            reference_snapshot_path=snapshot_path,
            reference_snapshot_id=snapshot_result.snapshot_id,
            reference_snapshot_sha256=snapshot_result.snapshot_sha256,
            destination=tmp_path / "artifacts" / "x.json",
        )


def test_null_prediction_semantics(tmp_path):
    """§25：no-candidate ⇔ predicted/score/rank 全 NULL；非"wrong person"。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(repos, tmp_path)
    predictions, document = _predictions_from_snapshot(repos, snapshot_path)
    e = document["content"]["entries"][0]
    no_candidate = PredictionRecord(
        person_id=uuid_mod.UUID(e["person_id"]),
        observation_id=uuid_mod.UUID(e["observation_id"]),
        photo_id=uuid_mod.UUID(e["photo_id"]),
        predicted_person_id=None, score=None, rank=None)
    result, destination = _build_artifact(
        repos, tmp_path, snapshot_result, snapshot_path, [no_candidate])
    entry = json.loads(destination.read_text(encoding="utf-8"))["content"]["predictions"][0]
    assert entry["prediction_type"] == "no-candidate"
    assert entry["predicted_person_id"] is None
    assert entry["score"] is None and entry["rank"] is None
    # score 有值但 predicted_person_id NULL → 结构矛盾 → 拒绝
    bad = PredictionRecord(
        person_id=uuid_mod.UUID(e["person_id"]),
        observation_id=uuid_mod.UUID(e["observation_id"]),
        photo_id=uuid_mod.UUID(e["photo_id"]),
        predicted_person_id=None, score=0.9, rank=None)
    with pytest.raises(ValidationError, match="no-candidate"):
        _artifact_service(repos).build_artifact(
            prediction_source="S-B",
            prediction_method="sb-member-max-cosine-v1",
            prediction_method_version="v1",
            predictions=[bad],
            reference_snapshot_path=snapshot_path,
            reference_snapshot_id=snapshot_result.snapshot_id,
            reference_snapshot_sha256=snapshot_result.snapshot_sha256,
            destination=tmp_path / "artifacts" / "x.json",
        )


def test_multi_face_predictions(tmp_path):
    """§24：同 photo 多 entry → 多条预测（无 UNIQUE(photo_id) 丢失）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    import tests.integration.test_sb3_reference_eligibility as sb3

    run, cluster_run, _clusters = sb3._reference_batch(repos, tmp_path, [
        ("two.jpg", [(0.9, (0, 0, 0, 1.0, 0, 0, 0, 0)),
                     (0.9, (0, 1.0, 0, 0, 0, 0, 0, 0))])])
    rclusters = sorted(
        repos.face_clusters.list_clusters(cluster_run.id), key=lambda c: c.ordinal)
    _guard(repos).confirm_reference_cluster(
        cluster_run.id, {rclusters[0].id}, people[0].id,
        _evaluation_dataset_id(repos), VERSION)
    _guard(repos).confirm_reference_cluster(
        cluster_run.id, {rclusters[1].id}, people[1].id,
        _evaluation_dataset_id(repos), VERSION)
    snapshot_result, snapshot_path = _build_snapshot(
        repos, tmp_path, run, cluster_run)
    assert snapshot_result.entry_count == 2
    predictions, document = _predictions_from_snapshot(repos, snapshot_path)
    assert len({e["photo_id"] for e in document["content"]["entries"]}) == 1
    result, _destination = _build_artifact(
        repos, tmp_path, snapshot_result, snapshot_path, predictions)
    assert result.prediction_count == 2  # 同 photo 两条预测都保留


def test_immutability_overwrite_rejected(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(repos, tmp_path)
    predictions, _document = _predictions_from_snapshot(repos, snapshot_path)
    result, destination = _build_artifact(
        repos, tmp_path, snapshot_result, snapshot_path, predictions)
    before = destination.read_bytes()
    store = FilesystemSnapshotStore()
    with pytest.raises(SnapshotAlreadyExistsError):
        store.write_atomic(destination, b"tampered")
    assert destination.read_bytes() == before
    service = _artifact_service(repos)
    assert not any(name.startswith(("update_", "delete_", "replace_", "append_"))
                   for name in dir(service))


def test_atomicity_write_failure(tmp_path):
    """§31：写入失败（destination 是目录）→ OSError、无 .part 残留。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(repos, tmp_path)
    predictions, _document = _predictions_from_snapshot(repos, snapshot_path)
    bad_destination = tmp_path / "artifacts" / "occupied.json"
    bad_destination.mkdir(parents=True)  # 目录占据目标路径
    with pytest.raises(OSError):
        _artifact_service(repos).build_artifact(
            prediction_source="S-B",
            prediction_method="sb-member-max-cosine-v1",
            prediction_method_version="v1",
            predictions=predictions,
            reference_snapshot_path=snapshot_path,
            reference_snapshot_id=snapshot_result.snapshot_id,
            reference_snapshot_sha256=snapshot_result.snapshot_sha256,
            destination=bad_destination,
        )
    assert not (tmp_path / "artifacts" / "occupied.json.part").exists()


def test_no_business_writes(tmp_path):
    """§26：Artifact 构建 → 全部业务表 delta = 0。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    snapshot_result, snapshot_path, _people = _setup_with_snapshot(repos, tmp_path)
    predictions, _document = _predictions_from_snapshot(repos, snapshot_path)

    def counts():
        con = sqlite3.connect(f"file:{(tmp_path / 'db.sqlite3').as_posix()}?mode=ro", uri=True)
        row = con.execute(
            "SELECT (SELECT COUNT(*) FROM cluster_person_assignments),"
            " (SELECT COUNT(*) FROM person_face_embeddings),"
            " (SELECT COUNT(*) FROM archive_records),"
            " (SELECT COUNT(*) FROM recognition_results),"
            " (SELECT COUNT(*) FROM calibration_ground_truth),"
            " (SELECT COUNT(*) FROM calibration_datasets)").fetchone()
        con.close()
        return row

    before = counts()
    _build_artifact(repos, tmp_path, snapshot_result, snapshot_path, predictions)
    assert counts() == before
