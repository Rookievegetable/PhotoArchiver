"""S-B-6 Isolation Attestation（``isolation-attestation-v1``）builder + verifier.

依据 R3 §4.1：RULESET 规范值 ``isolation-attestation-rules-v1``（冻结）；
I-1..I-7 检查复用 S-B-2 守卫 API 与 S-B-3 E-05 冻结规则；**两侧均实算当前
字节 SHA-256**（v2 契约；历史存储值不得作为当前字节证据；无冻结新鲜度机制
→ 不可得即 ``unprovable``）；证据缺失/未知 RULESET/检查失败 → fail-closed；
``isolation_invariant_sha256 = sha256(canonical(payload))``——**摘要本身不构成
隔离证明**（Assurance 映射见 R3 §4.7 / B3）。

零业务写入；发布复用不可变文件层（原子 + 拒绝覆盖）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from photo_archiver.application.ports import PhotoContentHasher, SnapshotStore
from photo_archiver.application.services.reference_intake_service import (
    ReferenceIntakeService,
)
from photo_archiver.application.services.reference_snapshot_service import (
    ReferenceSnapshotService,
    SnapshotDocument,
    canonical_json,
)
from photo_archiver.application.services.sb6_contract import (
    ISOLATION_ATTESTATION_CHECK_KEYS,
    ISOLATION_ATTESTATION_CONTENT_KEYS,
    ISOLATION_ATTESTATION_RULESET,
    ISOLATION_ATTESTATION_SCHEMA_VERSION,
    _as_uuid,
)
from photo_archiver.application.services.target_manifest_service import (
    TargetManifestDocument,
    TargetManifestService,
)
from photo_archiver.domain import PhotoRepository
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.repositories.face_observation_repository import (
    FaceObservationRepository,
)

_RESULT_PASS = "pass"
_RESULT_FAIL = "fail"
_RESULT_UNPROVABLE = "unprovable"


@dataclass(frozen=True, slots=True)
class AttestationCheck:
    """One named isolation check with evidence（RULESET 内容 = I-1..I-7）."""

    check_id: str
    rule_ref: str
    inputs_digest: str
    result: str
    evidence_refs: tuple[str, ...]
    detail: str

    def to_content_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "rule_ref": self.rule_ref,
            "inputs_digest": self.inputs_digest,
            "result": self.result,
            "evidence_refs": list(self.evidence_refs),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class AttestationEvaluation:
    """Read-only evaluation outcome（构建与重验证共用）."""

    checks: tuple[AttestationCheck, ...]
    reference_photo_set_sha256: str
    eval_photo_set_sha256: str
    target_photo_set_sha256: str
    reference_recognition_run_ids: tuple[UUID, ...]
    unprovable_reasons: tuple[str, ...]

    @property
    def all_checks_pass(self) -> bool:
        return not self.unprovable_reasons and all(
            c.result == _RESULT_PASS for c in self.checks
        )


@dataclass(frozen=True, slots=True)
class AttestationDocument:
    """A parsed attestation file（不可变视图）."""

    attestation_id: UUID
    schema_version: str
    created_at: str
    isolation_invariant_sha256: str
    content: dict


@dataclass(frozen=True, slots=True)
class AttestationCreationResult:
    attestation_id: UUID
    attestation_path: Path
    isolation_invariant_sha256: str
    checks: tuple[AttestationCheck, ...]


@dataclass(frozen=True, slots=True)
class AttestationVerification:
    """六维相关判定（Assurance 映射见 R3 §4.7）."""

    file_exists: bool
    integrity: str  # pass / fail / not-run
    revalidation: str  # pass / fail / not-run / unprovable
    assurance: str  # valid-and-verified / internal-only / unprovable / invalid
    ruleset_known: bool
    bindings: str  # pass / fail / undeterminable
    evidence_complete: bool
    check_mismatches: tuple[str, ...]
    detail: str | None = None


def _digest(values) -> str:
    return hashlib.sha256(
        canonical_json(sorted(str(v) for v in values))
    ).hexdigest()


class IsolationAttestationService:
    """Build + verify isolation attestation documents（零业务写入）."""

    def __init__(
        self,
        reference_intake: ReferenceIntakeService,
        manifest_service: TargetManifestService,
        snapshot_service: ReferenceSnapshotService,
        observation_repository: FaceObservationRepository,
        photo_repository: PhotoRepository,
        content_hasher: PhotoContentHasher,
        attestation_store: SnapshotStore,
    ) -> None:
        self._intake = reference_intake
        self._manifests = manifest_service
        self._snapshots = snapshot_service
        self._observations = observation_repository
        self._photos = photo_repository
        self._hasher = content_hasher
        self._store = attestation_store

    # -------------------------------------------------------------- evaluate

    def evaluate(
        self,
        *,
        dataset_id: UUID | str,
        dataset_version: str,
        cluster_run_id: UUID | str,
        manifest_document: TargetManifestDocument,
        snapshot_document: SnapshotDocument,
        reference_recognition_run_ids: frozenset[UUID] | None = None,
    ) -> AttestationEvaluation:
        dataset_uuid = _as_uuid(dataset_id)
        run_uuid = _as_uuid(cluster_run_id)
        if str(manifest_document.content.get("cluster_run_id")) != str(run_uuid):
            raise ValidationError(
                "ERR-IDENTITY-MISMATCH: cluster_run_id does not match the manifest "
                "generation anchor"
            )
        snapshot_entries = snapshot_document.entries
        reference_photo_ids = frozenset(UUID(e["photo_id"]) for e in snapshot_entries)
        reference_observation_ids = frozenset(
            UUID(e["observation_id"]) for e in snapshot_entries
        )
        target_photo_ids = frozenset(
            UUID(e["photo_id"]) for e in manifest_document.content["entries"]
        )
        eval_photo_ids = self._intake.build_evaluation_photo_set(
            dataset_uuid, dataset_version
        )
        eval_member_obs = self._intake.evaluation_member_observations(
            dataset_uuid, dataset_version
        )

        detection_checks: list[AttestationCheck] = []
        unprovable: list[str] = []

        # I-1 photo_id 集合互斥（主不变量）
        ref_eval_intersection = reference_photo_ids & eval_photo_ids
        ref_target_intersection = reference_photo_ids & target_photo_ids
        i1_result = (
            _RESULT_PASS
            if not ref_eval_intersection and not ref_target_intersection
            else _RESULT_FAIL
        )
        detection_checks.append(
            AttestationCheck(
                check_id="I-1-photo-id-disjointness",
                rule_ref="14 硬约束 #1/#4 + S-B-2 verify_reference_photos",
                inputs_digest=_digest(
                    sorted(str(v) for v in reference_photo_ids)
                    + sorted(str(v) for v in eval_photo_ids)
                ),
                result=i1_result,
                evidence_refs=(
                    f"reference_photo_set_sha256:{_digest(reference_photo_ids)}",
                    f"eval_photo_set_sha256:{_digest(eval_photo_ids)}",
                    f"target_photo_set_sha256:{_digest(target_photo_ids)}",
                ),
                detail=(
                    f"reference∩eval={len(ref_eval_intersection)} "
                    f"reference∩target={len(ref_target_intersection)}"
                ),
            )
        )

        # I-2 same-cluster
        i2_violations = reference_observation_ids & eval_member_obs
        detection_checks.append(
            AttestationCheck(
                check_id="I-2-same-cluster",
                rule_ref="E-05-same-cluster + S-B-2 (b)",
                inputs_digest=_digest(reference_observation_ids),
                result=_RESULT_PASS if not i2_violations else _RESULT_FAIL,
                evidence_refs=(
                    f"eval_member_observations_sha256:{_digest(eval_member_obs)}",
                ),
                detail=f"offending={len(i2_violations)}",
            )
        )

        # I-3 photo-on-eval（逐 photo 结果；输入同 I-1）
        detection_checks.append(
            AttestationCheck(
                check_id="I-3-photo-on-eval",
                rule_ref="E-05-eval-photo-isolation + S-B-2 (c)",
                inputs_digest=_digest(reference_photo_ids),
                result=i1_result,
                evidence_refs=(
                    f"violations:{len(ref_eval_intersection)}",
                ),
                detail=f"reference photos on EvalPhotoSet={len(ref_eval_intersection)}",
            )
        )

        # I-4 cross-run（参考 Run 集权威派生自快照 entry provenance）
        derived_runs: set[UUID] = set()
        provenance_ok = True
        try:
            derived_runs = {
                UUID(str(e["provenance"]["recognition_run_id"]))
                for e in snapshot_entries
            }
        except (KeyError, ValueError, TypeError):
            provenance_ok = False
        if not provenance_ok or not derived_runs:
            detection_checks.append(
                AttestationCheck(
                    check_id="I-4-cross-run",
                    rule_ref="E-05-cross-run",
                    inputs_digest=_digest(()),
                    result=_RESULT_FAIL,
                    evidence_refs=(),
                    detail="snapshot entry provenance.recognition_run_id unreadable",
                )
            )
            unprovable.append("I-4: snapshot provenance unreadable")
        if derived_runs:
            if reference_recognition_run_ids is not None and (
                frozenset(_as_uuid(r) for r in reference_recognition_run_ids)
                != frozenset(derived_runs)
            ):
                detection_checks.append(
                    AttestationCheck(
                        check_id="I-4-cross-run",
                        rule_ref="E-05-cross-run",
                        inputs_digest=_digest(derived_runs),
                        result=_RESULT_FAIL,
                        evidence_refs=(),
                        detail="caller-supplied run set != derived-from-snapshot set",
                    )
                )
            else:
                i4_result = _RESULT_PASS
                i4_detail = f"derived_runs={len(derived_runs)}"
                i4_unprovable = False
                for photo_id in sorted(reference_photo_ids, key=str):
                    try:
                        observations = self._observations.list_by_photo(photo_id)
                    except ValidationError:
                        observations = None
                    if observations is None:
                        i4_result = _RESULT_UNPROVABLE
                        i4_detail = f"photo {photo_id} observations unreadable"
                        i4_unprovable = True
                        break
                    if not observations:
                        i4_result = _RESULT_UNPROVABLE
                        i4_detail = f"photo {photo_id} has no observations"
                        i4_unprovable = True
                        break
                    if not {o.run_id for o in observations} <= derived_runs:
                        i4_result = _RESULT_FAIL
                        i4_detail = f"photo {photo_id} has observations outside derived runs"
                        break
                if i4_unprovable:
                    unprovable.append(f"I-4: {i4_detail}")
                detection_checks.append(
                    AttestationCheck(
                        check_id="I-4-cross-run",
                        rule_ref="E-05-cross-run",
                        inputs_digest=_digest(derived_runs),
                        result=i4_result,
                        evidence_refs=(
                            f"reference_recognition_run_ids:{len(derived_runs)}",
                        ),
                        detail=i4_detail,
                    )
                )

        # I-5 byte-hash（两侧均实算当前字节；无替代证据）
        i5_result = _RESULT_PASS
        i5_detail = "current-byte hashes disjoint"
        ref_hashes: set[str] = set()
        eval_hashes: set[str] = set()
        unreadable: list[str] = []
        for photo_id in sorted(reference_photo_ids, key=str):
            digest = self._live_photo_digest(photo_id)
            if digest is None:
                unreadable.append(f"ref:{photo_id}")
            else:
                ref_hashes.add(digest)
        for photo_id in sorted(eval_photo_ids, key=str):
            digest = self._live_photo_digest(photo_id)
            if digest is None:
                unreadable.append(f"eval:{photo_id}")
            else:
                eval_hashes.add(digest)
        if unreadable:
            i5_result = _RESULT_UNPROVABLE
            i5_detail = (
                "current bytes unobtainable (no substitute evidence): "
                + ", ".join(unreadable[:5])
            )
            unprovable.append(f"I-5: {i5_detail}")
        else:
            byte_intersection = ref_hashes & eval_hashes
            if byte_intersection:
                i5_result = _RESULT_FAIL
                i5_detail = f"byte-identical copy detected ({len(byte_intersection)})"
        detection_checks.append(
            AttestationCheck(
                check_id="I-5-byte-hash",
                rule_ref="E-05-content-hash + S-B-2 _verify_content_hashes（v2：两侧实算）",
                inputs_digest=_digest(sorted(ref_hashes) + sorted(eval_hashes)),
                result=i5_result,
                evidence_refs=(
                    f"reference_live_hashes:{len(ref_hashes)}",
                    f"eval_live_hashes:{len(eval_hashes)}",
                ),
                detail=i5_detail,
            )
        )

        # I-6 dangling/existence
        dangling: list[str] = []
        for entry in snapshot_entries:
            photo_id = UUID(entry["photo_id"])
            observation_id = UUID(entry["observation_id"])
            photo = self._photos.find_by_id(photo_id)
            if photo is None:
                dangling.append(str(photo_id))
                continue
            try:
                observed = {o.id for o in self._observations.list_by_photo(photo_id)}
            except ValidationError:
                observed = set()
            if observation_id not in observed:
                dangling.append(str(observation_id))
        detection_checks.append(
            AttestationCheck(
                check_id="I-6-dangling",
                rule_ref="S-B-2 dangling/existence",
                inputs_digest=_digest(reference_observation_ids),
                result=_RESULT_PASS if not dangling else _RESULT_FAIL,
                evidence_refs=(f"reference_entries:{len(snapshot_entries)}",),
                detail=f"dangling={len(dangling)}",
            )
        )

        # I-7 enabled（辅助，非隔离判定；信息记录）
        enabled_count = sum(1 for e in snapshot_entries if e.get("enabled") is True)
        detection_checks.append(
            AttestationCheck(
                check_id="I-7-enabled-frozen",
                rule_ref="14 硬约束 #8（enabled 按 snapshot 冻结）",
                inputs_digest=_digest(()),
                result=_RESULT_PASS,
                evidence_refs=(f"enabled_entries:{enabled_count}",),
                detail=f"enabled {enabled_count}/{len(snapshot_entries)}（信息项）",
            )
        )

        return AttestationEvaluation(
            checks=tuple(detection_checks),
            reference_photo_set_sha256=_digest(reference_photo_ids),
            eval_photo_set_sha256=_digest(eval_photo_ids),
            target_photo_set_sha256=_digest(target_photo_ids),
            reference_recognition_run_ids=tuple(
                sorted(derived_runs, key=str)
            ),
            unprovable_reasons=tuple(unprovable),
        )

    def _live_photo_digest(self, photo_id: UUID) -> str | None:
        """当前字节实算（ContentHashCalculator）；不可读 → None（无替代证据）."""
        photo = self._photos.find_by_id(photo_id)
        if photo is None:
            return None
        try:
            return self._hasher.calculate(photo.path.raw_path)
        except (OSError, ValueError):
            return None

    # ----------------------------------------------------------------- build

    def build_attestation(
        self,
        *,
        dataset_id: UUID | str,
        dataset_version: str,
        cluster_run_id: UUID | str,
        target_manifest_path: Path,
        target_manifest_id: UUID | str,
        target_manifest_sha256: str,
        reference_snapshot_path: Path,
        reference_snapshot_id: UUID | str,
        reference_snapshot_sha256: str,
        destination: Path,
        reference_recognition_run_ids: frozenset[UUID] | None = None,
    ) -> AttestationCreationResult:
        manifest_document = self._manifests.read_document(Path(target_manifest_path))
        if manifest_document.manifest_id != _as_uuid(target_manifest_id):
            raise ValidationError(
                "ERR-IDENTITY-MISMATCH: target manifest ID mismatch "
                f"(expected {target_manifest_id}, file {manifest_document.manifest_id})"
            )
        if self._manifests.manifest_sha256(manifest_document) != target_manifest_sha256:
            raise ValidationError(
                "ERR-HASH-MISMATCH: target manifest SHA256 mismatch"
            )
        snapshot_document = self._snapshots.read_document(Path(reference_snapshot_path))
        inner = self._snapshots.verify_snapshot(Path(reference_snapshot_path))
        if not inner.ok:
            raise ValidationError(
                f"ERR-HASH-MISMATCH: snapshot failed verification: {inner}"
            )
        if snapshot_document.snapshot_id != _as_uuid(reference_snapshot_id):
            raise ValidationError("ERR-IDENTITY-MISMATCH: reference snapshot ID mismatch")
        snapshot_recomputed = hashlib.sha256(
            canonical_json(snapshot_document.content)
        ).hexdigest()
        if snapshot_recomputed != reference_snapshot_sha256:
            raise ValidationError("ERR-HASH-MISMATCH: reference snapshot SHA256 mismatch")

        evaluation = self.evaluate(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            cluster_run_id=cluster_run_id,
            manifest_document=manifest_document,
            snapshot_document=snapshot_document,
            reference_recognition_run_ids=reference_recognition_run_ids,
        )
        if not evaluation.all_checks_pass:
            failing = [
                f"{c.check_id}={c.result}" for c in evaluation.checks
                if c.result != _RESULT_PASS
            ]
            raise ValidationError(
                "ERR-UNPROVABLE: isolation checks not all passing — NO ATTESTATION "
                f"(unprovable={list(evaluation.unprovable_reasons)}, "
                f"failing={failing})"
            )

        content = {
            "schema_version": ISOLATION_ATTESTATION_SCHEMA_VERSION,
            "ruleset": ISOLATION_ATTESTATION_RULESET,
            "dataset_id": str(_as_uuid(dataset_id)),
            "dataset_version": dataset_version,
            "cluster_run_id": str(_as_uuid(cluster_run_id)),
            "target_manifest_id": str(manifest_document.manifest_id),
            "target_manifest_sha256": target_manifest_sha256,
            "reference_snapshot_id": str(snapshot_document.snapshot_id),
            "reference_snapshot_sha256": reference_snapshot_sha256,
            "reference_recognition_run_ids": [
                str(r) for r in evaluation.reference_recognition_run_ids
            ],
            "photo_set_digests": {
                "reference": evaluation.reference_photo_set_sha256,
                "eval": evaluation.eval_photo_set_sha256,
                "target": evaluation.target_photo_set_sha256,
            },
            "checks": [c.to_content_dict() for c in evaluation.checks],
            "unprovable_reasons": list(evaluation.unprovable_reasons),
        }
        invariant_sha = hashlib.sha256(canonical_json(content)).hexdigest()
        attestation_id = uuid4()
        document = {
            "attestation_id": str(attestation_id),
            "schema_version": ISOLATION_ATTESTATION_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "isolation_invariant_sha256": invariant_sha,
            "content": content,
        }
        self._store.write_atomic(Path(destination), canonical_json(document))
        post = self.verify_attestation(
            Path(destination),
            target_manifest_path=Path(target_manifest_path),
            reference_snapshot_path=Path(reference_snapshot_path),
        )
        if post.assurance != "valid-and-verified":
            raise ValidationError(
                f"post-publish verification failed: assurance={post.assurance}"
            )
        return AttestationCreationResult(
            attestation_id=attestation_id,
            attestation_path=Path(destination),
            isolation_invariant_sha256=invariant_sha,
            checks=evaluation.checks,
        )

    # ------------------------------------------------------------------ read

    def read_document(self, attestation_path: Path) -> AttestationDocument:
        path = Path(attestation_path)
        if not self._store.path_exists(path):
            raise ValidationError(f"attestation file missing: {path}")
        try:
            document = json.loads(self._store.read_bytes(path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValidationError(f"attestation file unparseable: {exc}") from None
        if document.get("schema_version") != ISOLATION_ATTESTATION_SCHEMA_VERSION:
            raise ValidationError(
                "unsupported attestation schema version: "
                f"{document.get('schema_version')!r}"
            )
        return AttestationDocument(
            attestation_id=UUID(document["attestation_id"]),
            schema_version=document["schema_version"],
            created_at=document["created_at"],
            isolation_invariant_sha256=document["isolation_invariant_sha256"],
            content=document["content"],
        )

    # ---------------------------------------------------------------- verify

    def verify_attestation(
        self,
        attestation_path: Path,
        *,
        target_manifest_path: Path | None = None,
        reference_snapshot_path: Path | None = None,
    ) -> AttestationVerification:
        path = Path(attestation_path)
        if not self._store.path_exists(path):
            return AttestationVerification(
                file_exists=False,
                integrity="not-run",
                revalidation="not-run",
                assurance="unprovable",
                ruleset_known=False,
                bindings="undeterminable",
                evidence_complete=False,
                check_mismatches=(),
                detail="attestation file missing",
            )
        try:
            document = json.loads(self._store.read_bytes(path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return AttestationVerification(
                file_exists=True,
                integrity="fail",
                revalidation="not-run",
                assurance="invalid",
                ruleset_known=False,
                bindings="undeterminable",
                evidence_complete=False,
                check_mismatches=(),
                detail="attestation file unparseable",
            )
        schema_ok = (
            document.get("schema_version") == ISOLATION_ATTESTATION_SCHEMA_VERSION
        )
        content = document.get("content") or {}
        recomputed = hashlib.sha256(canonical_json(content)).hexdigest()
        hash_ok = document.get("isolation_invariant_sha256") == recomputed
        keys_ok = set(content.keys()) == set(ISOLATION_ATTESTATION_CONTENT_KEYS) and all(
            isinstance(c, dict) and set(c.keys()) == set(ISOLATION_ATTESTATION_CHECK_KEYS)
            for c in content.get("checks") or []
        )
        ruleset_known = content.get("ruleset") == ISOLATION_ATTESTATION_RULESET
        recorded_checks = content.get("checks") or []
        evidence_complete = (
            not content.get("unprovable_reasons")
            and all(bool(c.get("evidence_refs")) for c in recorded_checks)
        )
        integrity = "pass" if (schema_ok and hash_ok and keys_ok and ruleset_known) else "fail"

        mismatches: list[str] = []
        bindings = "undeterminable"
        revalidation = "not-run"
        if integrity != "pass":
            detail = (
                None if schema_ok else "schema/key/RULESET failure"
            )
            return AttestationVerification(
                file_exists=True,
                integrity=integrity,
                revalidation="not-run",
                assurance="invalid",
                ruleset_known=ruleset_known,
                bindings=bindings,
                evidence_complete=evidence_complete,
                check_mismatches=(),
                detail=detail or "integrity failure",
            )
        if target_manifest_path is not None and reference_snapshot_path is not None:
            try:
                manifest_document = self._manifests.read_document(
                    Path(target_manifest_path)
                )
                snapshot_document = self._snapshots.read_document(
                    Path(reference_snapshot_path)
                )
                manifests_match = (
                    str(manifest_document.manifest_id)
                    == str(content.get("target_manifest_id"))
                    and self._manifests.manifest_sha256(manifest_document)
                    == content.get("target_manifest_sha256")
                )
                snapshots_match = (
                    str(snapshot_document.snapshot_id)
                    == str(content.get("reference_snapshot_id"))
                    and hashlib.sha256(canonical_json(snapshot_document.content)).hexdigest()
                    == content.get("reference_snapshot_sha256")
                )
                bindings = "pass" if (manifests_match and snapshots_match) else "fail"
                evaluation = self.evaluate(
                    dataset_id=str(content.get("dataset_id")),
                    dataset_version=str(content.get("dataset_version")),
                    cluster_run_id=str(content.get("cluster_run_id")),
                    manifest_document=manifest_document,
                    snapshot_document=snapshot_document,
                )
                recorded_by_id = {
                    c["check_id"]: c for c in recorded_checks
                }
                evaluated_by_id = {
                    c.check_id: c for c in evaluation.checks
                }
                definite: list[str] = []
                unprovable_mismatch: list[str] = []
                if set(recorded_by_id) != set(evaluated_by_id):
                    definite.append("ERR-EVIDENCE-MISSING: check id set mismatch")
                for check_id, replayed in evaluated_by_id.items():
                    recorded = recorded_by_id.get(check_id)
                    if recorded is None:
                        continue
                    if replayed.result == _RESULT_UNPROVABLE:
                        if recorded.get("result") != _RESULT_UNPROVABLE:
                            unprovable_mismatch.append(
                                f"{check_id}: recorded={recorded.get('result')} "
                                "replay=unprovable（证据不可得）"
                            )
                    elif recorded.get("result") != replayed.result:
                        definite.append(
                            f"{check_id}: recorded={recorded.get('result')} "
                            f"replayed={replayed.result}"
                        )
                    elif recorded.get("inputs_digest") != replayed.inputs_digest:
                        definite.append(f"{check_id}: inputs_digest mismatch")
                recorded_runs = content.get("reference_recognition_run_ids") or []
                replay_runs = [str(r) for r in evaluation.reference_recognition_run_ids]
                if list(recorded_runs) != replay_runs:
                    definite.append("reference_recognition_run_ids mismatch")
                mismatches.extend(definite)
                mismatches.extend(unprovable_mismatch)
                if definite:
                    revalidation = "fail"
                elif unprovable_mismatch or not evaluation.all_checks_pass:
                    # 无确凿失配，但真实证据不可复核 → 不得判 fail 也不得判 pass
                    revalidation = "unprovable"
                else:
                    revalidation = "pass"
            except ValidationError as exc:
                revalidation = "unprovable"
                mismatches.append(f"ERR-UNPROVABLE: re-execution failed ({exc})")

        support = self._assurance_support(bindings, evidence_complete)
        assurance = self._map_assurance(integrity, revalidation, support)
        return AttestationVerification(
            file_exists=True,
            integrity=integrity,
            revalidation=revalidation,
            assurance=assurance,
            ruleset_known=ruleset_known,
            bindings=bindings,
            evidence_complete=evidence_complete,
            check_mismatches=tuple(mismatches),
        )

    @staticmethod
    def _assurance_support(bindings: str, evidence_complete: bool) -> str:
        if bindings == "fail" or not evidence_complete:
            return "fail"
        if bindings == "undeterminable":
            return "undeterminable"
        return "pass"

    @staticmethod
    def _map_assurance(integrity: str, revalidation: str, support: str) -> str:
        """R3 §4.7 / B3 确定性映射（不得把枚举填 pass 替代真实验证）."""
        if integrity == "not-run":
            return "unprovable"
        if integrity == "fail":
            return "invalid"
        if revalidation == "fail":
            return "invalid"
        if revalidation == "not-run":
            return "internal-only"
        if revalidation == "unprovable":
            return "unprovable"
        if support == "fail":
            return "invalid"
        if support == "undeterminable":
            return "unprovable"
        return "valid-and-verified"
