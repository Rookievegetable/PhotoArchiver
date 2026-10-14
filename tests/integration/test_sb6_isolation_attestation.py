"""S-B-6 Isolation Attestation acceptance tests（R3 §6 A 类：T-A1..T-A16）.

全部 fixture 驱动；生产零接触。Fixture 声明：测试构造工件 ≠ 生产工件。
"""

from __future__ import annotations

import shutil
import uuid as uuid_mod
from uuid import UUID

import pytest

from tests.integration.test_sb6_common import (
    VERSION,
    attestation_service,
    build_attestation,
    full_setup,
    make_repos,
    manifest_service,
    read_json,
    rewrite_with_rehash,
)
from tests.integration.test_sb3_reference_eligibility import _guard
from tests.integration.test_sb4_reference_snapshot import _snapshot_service

from photo_archiver.application.services.reference_snapshot_service import (
    SnapshotDocument,
)
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.value_objects.photo_metadata import PhotoMetadata
from photo_archiver.infrastructure.image.content_hash_calculator import (
    ContentHashCalculator,
)


def _documents(repos, setup):
    manifest_document = manifest_service(repos).read_document(
        setup.manifest_result.manifest_path
    )
    snapshot_document = _snapshot_service(repos).read_document(setup.snapshot_path)
    return manifest_document, snapshot_document


def _check_by_id(checks, check_id):
    return next(c for c in checks if c.check_id == check_id)


def test_attestation_build_and_verify_valid(tmp_path):
    """T-A1：全检查通过 → Integrity=pass ∧ Revalidation=pass ∧ valid-and-verified."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result, service = build_attestation(repos, tmp_path, setup)
    assert result.attestation_path.is_file()
    assert len(result.isolation_invariant_sha256) == 64

    verification = service.verify_attestation(
        result.attestation_path,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
    )
    assert verification.integrity == "pass"
    assert verification.revalidation == "pass"
    assert verification.assurance == "valid-and-verified"
    assert verification.ruleset_known is True
    assert verification.bindings == "pass"
    assert verification.evidence_complete is True


def test_ruleset_frozen_value_and_derived_run_set(tmp_path):
    """RULESET 冻结值 + I-4 参考 Run 集权威派生（来自快照 provenance）."""
    from photo_archiver.application.services.sb6_contract import (
        ISOLATION_ATTESTATION_RULESET,
    )

    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    manifest_document, snapshot_document = _documents(repos, setup)
    service = attestation_service(repos)
    evaluation = service.evaluate(
        dataset_id=setup.dataset.id,
        dataset_version=VERSION,
        cluster_run_id=setup.cluster_run.id,
        manifest_document=manifest_document,
        snapshot_document=snapshot_document,
    )
    assert evaluation.all_checks_pass
    assert evaluation.reference_recognition_run_ids == (
        UUID(str(snapshot_document.content["entries"][0]["provenance"]["recognition_run_id"])),
    )
    assert ISOLATION_ATTESTATION_RULESET == "isolation-attestation-rules-v1"


def test_payload_tamper_integrity_fail(tmp_path):
    """T-A2：篡改 canonical payload（不重算）→ Integrity=fail → invalid."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result, service = build_attestation(repos, tmp_path, setup)
    document = read_json(result.attestation_path)
    document["content"]["dataset_version"] = "tampered"
    result.attestation_path.write_text(
        __import__("json").dumps(document, ensure_ascii=False, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    verification = service.verify_attestation(result.attestation_path)
    assert verification.integrity == "fail"
    assert verification.assurance == "invalid"


def test_result_tamper_without_rehash_integrity_fail(tmp_path):
    """T-A3（B4-1）：修改 checks[].result 不重算哈希 → Integrity=fail."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result, service = build_attestation(repos, tmp_path, setup)
    document = read_json(result.attestation_path)
    document["content"]["checks"][0]["result"] = "fail"
    __import__("json")
    import json as _json

    result.attestation_path.write_text(
        _json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    verification = service.verify_attestation(result.attestation_path)
    assert verification.integrity == "fail"
    assert verification.assurance == "invalid"


def test_rehash_consistent_forgery_caught_by_revalidation(tmp_path):
    """T-A4（B4-2）：文件内部完整性通过，但真实源证据与记录不符 → Revalidation 独立检出.

    形态一：源侧在发布后变化（参考照片被写入评估照片字节 → 真实隔离失败），
    记录未改动（哈希仍有效）→ 重验证必须 fail（不得生成 valid-and-verified）。
    形态二：伪造额外检查项并重算哈希 → 检查集不一致 → Revalidation fail。
    """
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result, service = build_attestation(repos, tmp_path, setup)

    # 形态一：源侧破坏（参考照片字节 == 评估照片字节）
    manifest_document, snapshot_document = _documents(repos, setup)
    ref_photo_id = UUID(str(snapshot_document.content["entries"][0]["photo_id"]))
    ref_path = repos.photos.find_by_id(ref_photo_id).path.raw_path
    eval_photo_ids = _guard(repos).build_evaluation_photo_set(setup.dataset.id, VERSION)
    eval_path = repos.photos.find_by_id(next(iter(eval_photo_ids))).path.raw_path
    shutil.copyfile(eval_path, ref_path)
    verification = service.verify_attestation(
        result.attestation_path,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
    )
    assert verification.integrity == "pass"  # 记录未被改动
    assert verification.revalidation == "fail"  # 真实源证据独立复核检出
    assert verification.assurance == "invalid"
    assert any("I-5" in m for m in verification.check_mismatches)


def test_forged_extra_check_caught(tmp_path):
    """T-A4 形态二：伪造额外 check 并重算匹配哈希 → 检查集不一致 → Revalidation fail."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result, service = build_attestation(repos, tmp_path, setup)

    def mutate(document):
        document["content"]["checks"].append(
            {
                "check_id": "I-9-forged",
                "rule_ref": "forged",
                "inputs_digest": "0" * 64,
                "result": "pass",
                "evidence_refs": ["forged"],
                "detail": "forged pass",
            }
        )

    rewrite_with_rehash(result.attestation_path, mutate)
    verification = service.verify_attestation(
        result.attestation_path,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
    )
    assert verification.integrity == "pass"  # 哈希已重算匹配
    assert verification.revalidation == "fail"
    assert verification.assurance == "invalid"


def test_ruleset_unknown_integrity_fail(tmp_path):
    """T-A5：RULESET 缺失/未知 → Integrity=fail（不得 auto-pass）."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result, service = build_attestation(repos, tmp_path, setup)

    def mutate(document):
        document["content"]["ruleset"] = "unknown-ruleset-v9"

    rewrite_with_rehash(result.attestation_path, mutate)
    verification = service.verify_attestation(result.attestation_path)
    assert verification.ruleset_known is False
    assert verification.integrity == "fail"
    assert verification.assurance == "invalid"


def test_evidence_missing_support_fail(tmp_path):
    """T-A6：必要证据缺失（evidence_refs 空）→ Support fail → invalid（Integrity 仍 pass）."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result, service = build_attestation(repos, tmp_path, setup)

    def mutate(document):
        document["content"]["checks"][0]["evidence_refs"] = []

    rewrite_with_rehash(result.attestation_path, mutate)
    verification = service.verify_attestation(
        result.attestation_path,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
    )
    assert verification.integrity == "pass"
    assert verification.revalidation == "pass"
    assert verification.evidence_complete is False
    assert verification.assurance == "invalid"


def test_build_refused_when_reference_bytes_unreadable(tmp_path):
    """T-A7 构建侧：参考照片字节不可读 → 不发布有效 Attestation（fail-closed）."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    _manifest_document, snapshot_document = _documents(repos, setup)
    ref_photo_id = UUID(str(snapshot_document.content["entries"][0]["photo_id"]))
    from pathlib import Path

    Path(repos.photos.find_by_id(ref_photo_id).path.raw_path).unlink()
    with pytest.raises(ValidationError, match="ERR-UNPROVABLE"):
        build_attestation(repos, tmp_path, setup)
    assert not (tmp_path / "attestations" / "attestation.json").exists()


def test_verify_unprovable_after_reference_bytes_lost(tmp_path):
    """T-A7 验证侧：发布后参考字节丢失 → Revalidation=unprovable → Assurance=unprovable."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result, service = build_attestation(repos, tmp_path, setup)
    _manifest_document, snapshot_document = _documents(repos, setup)
    ref_photo_id = UUID(str(snapshot_document.content["entries"][0]["photo_id"]))
    from pathlib import Path

    Path(repos.photos.find_by_id(ref_photo_id).path.raw_path).unlink()
    verification = service.verify_attestation(
        result.attestation_path,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
    )
    assert verification.integrity == "pass"
    assert verification.revalidation == "unprovable"
    assert verification.assurance == "unprovable"


def test_photo_id_intersection_check_fails(tmp_path):
    """T-A8：photo_id 集合存在交集 → I-1 fail（不得通过）."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    manifest_document, snapshot_document = _documents(repos, setup)
    eval_photo_ids = sorted(
        _guard(repos).build_evaluation_photo_set(setup.dataset.id, VERSION), key=str
    )
    tampered_content = dict(snapshot_document.content)
    tampered_entries = [dict(e) for e in snapshot_document.content["entries"]]
    tampered_entries[0]["photo_id"] = str(eval_photo_ids[0])
    tampered_content["entries"] = tampered_entries
    tampered_document = SnapshotDocument(
        snapshot_id=snapshot_document.snapshot_id,
        schema_version=snapshot_document.schema_version,
        created_at=snapshot_document.created_at,
        snapshot_sha256=snapshot_document.snapshot_sha256,
        content=tampered_content,
    )
    service = attestation_service(repos)
    evaluation = service.evaluate(
        dataset_id=setup.dataset.id,
        dataset_version=VERSION,
        cluster_run_id=setup.cluster_run.id,
        manifest_document=manifest_document,
        snapshot_document=tampered_document,
    )
    assert _check_by_id(evaluation.checks, "I-1-photo-id-disjointness").result == "fail"
    assert not evaluation.all_checks_pass


def test_same_bytes_before_build_fails(tmp_path):
    """T-A9：同字节异 photo_id（参考照片实为评估照片字节副本）→ 构建拒绝."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    _manifest_document, snapshot_document = _documents(repos, setup)
    ref_photo_id = UUID(str(snapshot_document.content["entries"][0]["photo_id"]))
    ref_path = repos.photos.find_by_id(ref_photo_id).path.raw_path
    eval_photo_ids = _guard(repos).build_evaluation_photo_set(setup.dataset.id, VERSION)
    eval_path = repos.photos.find_by_id(next(iter(eval_photo_ids))).path.raw_path
    shutil.copyfile(eval_path, ref_path)
    with pytest.raises(ValidationError, match="ERR-UNPROVABLE"):
        build_attestation(repos, tmp_path, setup)


def test_run_set_mismatch_fails(tmp_path):
    """T-A10：调用方 Run 集 ≠ 快照派生集 → I-4 fail（不得任意调用方集合入档）."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    manifest_document, snapshot_document = _documents(repos, setup)
    service = attestation_service(repos)
    evaluation = service.evaluate(
        dataset_id=setup.dataset.id,
        dataset_version=VERSION,
        cluster_run_id=setup.cluster_run.id,
        manifest_document=manifest_document,
        snapshot_document=snapshot_document,
        reference_recognition_run_ids=frozenset({uuid_mod.uuid4()}),
    )
    assert _check_by_id(evaluation.checks, "I-4-cross-run").result == "fail"


def test_offline_verify_internal_only(tmp_path):
    """T-A11 / T-R1：离线（无源路径）→ Integrity=pass ∧ Revalidation=not-run.

    Assurance=internal-only——文件完整性通过不得冒充隔离验证通过。
    """
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result, service = build_attestation(repos, tmp_path, setup)
    verification = service.verify_attestation(result.attestation_path)
    assert verification.integrity == "pass"
    assert verification.revalidation == "not-run"
    assert verification.assurance == "internal-only"
    assert verification.assurance != "valid-and-verified"


def test_verify_unprovable_when_manifest_unreadable(tmp_path):
    """T-A16（c）：重验证时源不可用（manifest 缺失）→ Revalidation=unprovable."""
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result, service = build_attestation(repos, tmp_path, setup)
    from pathlib import Path

    Path(setup.manifest_result.manifest_path).unlink()
    verification = service.verify_attestation(
        result.attestation_path,
        target_manifest_path=setup.manifest_result.manifest_path,
        reference_snapshot_path=setup.snapshot_path,
    )
    assert verification.revalidation == "unprovable"
    assert verification.assurance == "unprovable"


def test_photo_set_digests_offline_recomputable(tmp_path):
    """T-A13：两侧集合摘要可离线复算（= photo_id 集合的 canonical sha256）."""
    import hashlib

    from photo_archiver.application.services.reference_snapshot_service import (
        canonical_json,
    )

    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    result, service = build_attestation(repos, tmp_path, setup)
    content = service.read_document(result.attestation_path).content
    manifest_document, snapshot_document = _documents(repos, setup)

    def digest(ids):
        return hashlib.sha256(
            canonical_json(sorted(str(i) for i in ids))
        ).hexdigest()

    reference_digest = digest(
        UUID(str(e["photo_id"])) for e in snapshot_document.content["entries"]
    )
    target_digest = digest(
        UUID(str(e["photo_id"])) for e in manifest_document.content["entries"]
    )
    assert content["photo_set_digests"]["reference"] == reference_digest
    assert content["photo_set_digests"]["target"] == target_digest


def test_stale_stored_hash_never_used_as_current_bytes(tmp_path):
    """T-A14（B2 负向）：合法格式的历史 stored 哈希不得被视为当前文件字节.

    评估照片回填哈希 H1 → 回填后字节变化为 H2（= 参考照片字节）→
    验证器必须实算当前字节并检出（fail），不得因 stored H1 格式合法而放行。
    """
    repos = make_repos(tmp_path)
    setup = full_setup(repos, tmp_path)
    manifest_document, snapshot_document = _documents(repos, setup)
    ref_photo_id = UUID(str(snapshot_document.content["entries"][0]["photo_id"]))
    ref_path = repos.photos.find_by_id(ref_photo_id).path.raw_path
    eval_photo_ids = sorted(
        _guard(repos).build_evaluation_photo_set(setup.dataset.id, VERSION), key=str
    )
    eval_photo_id = eval_photo_ids[0]
    eval_path = repos.photos.find_by_id(eval_photo_id).path.raw_path

    # 回填时点存储值 H1（旧字节哈希）
    stale_h1 = ContentHashCalculator().calculate(eval_path)
    repos.photos.update_metadata(
        eval_photo_id, PhotoMetadata(content_hash=stale_h1)
    )
    # 字节变化为 H2（= 参考照片字节，构成真实隔离违规）
    shutil.copyfile(ref_path, eval_path)

    service = attestation_service(repos)
    evaluation = service.evaluate(
        dataset_id=setup.dataset.id,
        dataset_version=VERSION,
        cluster_run_id=setup.cluster_run.id,
        manifest_document=manifest_document,
        snapshot_document=snapshot_document,
    )
    i5 = _check_by_id(evaluation.checks, "I-5-byte-hash")
    assert i5.result == "fail"  # 以当前字节实算判定，stored H1 未起作用
    assert not evaluation.all_checks_pass


def test_eval_current_bytes_unobtainable_unprovable(tmp_path):
    """T-A15：评估照片当前字节不可得（无替代证据）→ I-5 unprovable."""
    repositories = make_repos(tmp_path)
    setup = full_setup(repositories, tmp_path)
    manifest_document, snapshot_document = _documents(repositories, setup)
    eval_photo_ids = sorted(
        _guard(repositories).build_evaluation_photo_set(setup.dataset.id, VERSION),
        key=str,
    )
    from pathlib import Path

    Path(repositories.photos.find_by_id(eval_photo_ids[0]).path.raw_path).unlink()
    service = attestation_service(repositories)
    evaluation = service.evaluate(
        dataset_id=setup.dataset.id,
        dataset_version=VERSION,
        cluster_run_id=setup.cluster_run.id,
        manifest_document=manifest_document,
        snapshot_document=snapshot_document,
    )
    i5 = _check_by_id(evaluation.checks, "I-5-byte-hash")
    assert i5.result == "unprovable"
    assert evaluation.unprovable_reasons
    with pytest.raises(ValidationError, match="ERR-UNPROVABLE"):
        build_attestation(repositories, tmp_path, setup)
