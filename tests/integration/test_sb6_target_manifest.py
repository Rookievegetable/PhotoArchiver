"""S-B-6 Target Manifest acceptance tests（R3 §6 M 类：T-M1..T-M7）.

全部 fixture 驱动（隔离 SQLite 临时库 + 临时目录）；生产零接触。
Fixture 声明：本文件全部工件为测试构造的 fixture（≠ 真实生产预测/工件）。
"""

from __future__ import annotations

import uuid as uuid_mod

import pytest

from tests.integration.test_sb6_common import (
    VERSION,
    build_eval_side,
    build_manifest,
    full_setup,
    make_repos,
    manifest_service,
    read_json,
    rewrite_with_rehash,
)

from photo_archiver.domain.exceptions import ValidationError

_FOUR_FACES = {
    "e1.jpg": [(0.9, (1.0, 0, 0, 0))],
    "e2.jpg": [(0.9, (0, 1.0, 0, 0))],
    "e3.jpg": [(0.9, (0, 0, 1.0, 0))],
    "e4.jpg": [(0.9, (0, 0, 0, 1.0))],
}


def test_build_manifest_basic_and_verify(tmp_path):
    """基础构建：3 簇 3 成员；两计数分别记录；Layer A / Layer B 双 pass."""
    repos = make_repos(tmp_path)
    eval_side = build_eval_side(repos, tmp_path)
    result, service = build_manifest(repos, tmp_path, eval_side)

    assert result.cluster_count == 3
    assert result.entry_count == 3
    assert result.source_member_count == 3
    assert result.run_extra_cluster_ids == ()
    document = service.read_document(result.manifest_path)
    assert document.content["entry_count"] == 3
    assert document.content["source_member_count"] == 3
    assert len(document.content["dataset_cluster_ids"]) == 3

    verification = service.verify_manifest(result.manifest_path, source_check=True)
    assert verification.layer_a == "pass"
    assert verification.layer_b == "pass"
    assert verification.ok


def test_manifest_build_is_deterministic(tmp_path):
    """同冻结输入 → 相同 content 哈希（manifest_id 可变）."""
    repos = make_repos(tmp_path)
    eval_side = build_eval_side(repos, tmp_path)
    first, service = build_manifest(repos, tmp_path, eval_side, name="m1.json")
    second, _ = build_manifest(repos, tmp_path, eval_side, name="m2.json")
    assert first.manifest_id != second.manifest_id
    assert first.manifest_sha256 == second.manifest_sha256


def test_run_extra_cluster_not_failure(tmp_path):
    """T-M2：Run 额外 Cluster 不得导致失败、不得进入 Manifest（仅诊断）."""
    repos = make_repos(tmp_path)
    eval_side = build_eval_side(
        repos, tmp_path, _FOUR_FACES, gt_verdicts=["person", "person", "person", None]
    )
    assert len(eval_side.clusters) == 4
    result, service = build_manifest(repos, tmp_path, eval_side)

    assert result.cluster_count == 3
    assert len(result.run_extra_cluster_ids) == 1
    document = read_json(result.manifest_path)
    entry_clusters = {e["cluster_id"] for e in document["content"]["entries"]}
    assert str(result.run_extra_cluster_ids[0]) not in entry_clusters
    assert service.verify_manifest(result.manifest_path, source_check=True).ok


def test_dataset_cluster_missing_from_run_rejected(tmp_path):
    """T-M3：Dataset Cluster 缺失于指定 Run → NO MANIFEST."""
    repos = make_repos(tmp_path)
    eval_side = build_eval_side(repos, tmp_path)
    from tests.integration.test_sb3_reference_eligibility import _reference_batch

    _run, other_cluster_run, _clusters = _reference_batch(
        repos, tmp_path, [("r9.jpg", [(0.9, (0, 0, 0, 1.0))])]
    )
    service = manifest_service(repos)
    with pytest.raises(ValidationError, match="ERR-SET-EQUALITY"):
        service.build_manifest(
            eval_side.dataset.id,
            VERSION,
            other_cluster_run.id,
            tmp_path / "manifests" / "bad.json",
        )


def test_cluster_set_equality_tamper_layer_a(tmp_path):
    """T-M1：Manifest Cluster Set 与 Dataset 集合严格相等（篡改 → Layer A fail）."""
    repos = make_repos(tmp_path)
    eval_side = build_eval_side(repos, tmp_path)
    result, service = build_manifest(repos, tmp_path, eval_side)

    def mutate(document):
        document["content"]["dataset_cluster_ids"] = document["content"][
            "dataset_cluster_ids"
        ][:2]

    rewrite_with_rehash(result.manifest_path, mutate)
    verification = service.verify_manifest(result.manifest_path, source_check=True)
    assert verification.cluster_set_equal is False
    assert verification.layer_a == "fail"


def test_count_mismatch_layer_a(tmp_path):
    """T-M5：entry_count ≠ source_member_count → Layer A 计数一致性 fail."""
    repos = make_repos(tmp_path)
    eval_side = build_eval_side(repos, tmp_path)
    result, service = build_manifest(repos, tmp_path, eval_side)

    def mutate(document):
        document["content"]["source_member_count"] = 2

    rewrite_with_rehash(result.manifest_path, mutate)
    verification = service.verify_manifest(result.manifest_path, source_check=True)
    assert verification.counts_consistent is False
    assert verification.layer_a == "fail"


def test_counts_consistent_but_source_omission_detected_by_layer_b(tmp_path):
    """T-M6/T-M7：记录自洽（两计数相等）但源端实际遗漏 → Layer A pass ∧ Layer B fail.

    Layer A 的计数相等只证明记录内部自洽，**不得**冒充源成员完整性。
    使用双成员簇（同一簇两个 observation）构造"省略成员但簇集合仍相等"。
    """
    repos = make_repos(tmp_path)
    twin_faces = {
        "e1.jpg": [(0.9, (1.0, 0, 0, 0)), (0.95, (1.0, 0, 0, 0))],
        "e2.jpg": [(0.9, (0, 1.0, 0, 0))],
        "e3.jpg": [(0.9, (0, 0, 1.0, 0))],
    }
    eval_side = build_eval_side(repos, tmp_path, twin_faces)
    result, service = build_manifest(repos, tmp_path, eval_side)
    assert result.entry_count == 4

    def mutate(document):
        content = document["content"]
        by_cluster = {}
        for entry in content["entries"]:
            by_cluster.setdefault(entry["cluster_id"], []).append(entry)
        twin_cluster = next(
            entries for entries in by_cluster.values() if len(entries) == 2
        )
        dropped = twin_cluster[0]
        content["entries"] = [
            e for e in content["entries"] if e is not dropped
        ]
        content["entry_count"] = len(content["entries"])
        content["source_member_count"] = len(content["entries"])

    rewrite_with_rehash(result.manifest_path, mutate)
    verification = service.verify_manifest(result.manifest_path, source_check=True)
    assert verification.layer_a == "pass"  # 内部自洽（计数一致、簇集合仍相等）
    assert verification.layer_b == "fail"  # 源成员遗漏被检出
    assert verification.source_detail is not None
    assert "ERR-MEMBER-CLASS" in verification.source_detail


def test_photo_id_mismatch_detected_by_layer_b(tmp_path):
    """T-M4e：entry photo_id 与源 observation 实际照片错配 → Layer B fail."""
    repos = make_repos(tmp_path)
    eval_side = build_eval_side(repos, tmp_path)
    result, service = build_manifest(repos, tmp_path, eval_side)

    def mutate(document):
        entries = document["content"]["entries"]
        entries[0]["photo_id"] = entries[1]["photo_id"]

    rewrite_with_rehash(result.manifest_path, mutate)
    verification = service.verify_manifest(result.manifest_path, source_check=True)
    assert verification.layer_b == "fail"
    assert "photo_mismatch=1" in (verification.source_detail or "")


def test_duplicate_entry_identity_layer_a(tmp_path):
    """T-M4c：重复成员身份（同 (cluster_id, observation_id) 两行）→ Layer A fail."""
    repos = make_repos(tmp_path)
    eval_side = build_eval_side(repos, tmp_path)
    result, service = build_manifest(repos, tmp_path, eval_side)

    def mutate(document):
        content = document["content"]
        duplicate = dict(content["entries"][0])
        duplicate["id"] = str(uuid_mod.uuid4())
        content["entries"] = content["entries"] + [duplicate]
        content["entry_count"] = len(content["entries"])
        content["source_member_count"] = len(content["entries"])

    rewrite_with_rehash(result.manifest_path, mutate)
    verification = service.verify_manifest(result.manifest_path, source_check=True)
    assert verification.identity_unique is False
    assert verification.layer_a == "fail"


def test_full_setup_snapshot_and_manifest_coexist(tmp_path):
    """组合 fixture 冒烟：Manifest 与参考侧 Snapshot 并存且互不干扰."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    assert setup.manifest_result.entry_count == 3
    assert setup.snapshot_result.entry_count == 1
    verification = manifest_service(repos).verify_manifest(
        setup.manifest_result.manifest_path, source_check=True
    )
    assert verification.layer_a == "pass"
    assert verification.layer_b == "pass"
