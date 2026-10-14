"""S-B-6 Mechanical Scoring consumer（v2 Evaluation Unit；member-level outcomes）.

依据 R3 §4.7 与 ORD-1..8 裁决：

* **Gate 0 Input Classification**：v1/unknown → REJECT-TERMINAL（正确拒绝 =
  测试断言成功 ∧ admission=false；报告三字段分离）。
* **六维分离**：Layer A / Layer B / Attestation Integrity / Isolation
  Revalidation / Attestation Assurance / Scoring Admission（由公式导出）。
* **准入公式**：13 项全部 ``pass`` 才 admit；任何 fail/缺失/not-run/unprovable
  → NO SCORING（显式不可评分状态 + 六维明细）。
* **GT 三态派生**：``gt-person(X)`` / ``gt-cluster-out-of-roster`` /
  ``gt-cluster-undecidable``（禁止 NULL 塌缩）；member-level 机械比较为原始
  事实字段（outcome 分类学未在本阶段冻结——不得发明标签）。
* 本服务返回**内存结果对象**：R3 未定义输出文件格式，不发布任何产物。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from uuid import UUID

from photo_archiver.application.services.isolation_attestation_service import (
    IsolationAttestationService,
)
from photo_archiver.application.services.prediction_artifact_v2_service import (
    PredictionArtifactV2Service,
)
from photo_archiver.application.services.reference_snapshot_service import (
    ReferenceSnapshotService,
)
from photo_archiver.application.services.sb6_contract import (
    INPUT_CLASS_V1,
    INPUT_CLASS_V2,
    REJECTION_AS_REQUIRED,
    REJECTION_NOT_REQUIRED,
    SCORING_AUTHORIZED_SOURCES,
)
from photo_archiver.application.services.target_manifest_service import (
    TargetManifestService,
)
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.repositories.calibration_annotation_repository import (
    CalibrationAnnotationRepository,
)
from photo_archiver.domain.repositories.person_repository import PersonRepository

GT_STATE_PERSON = "gt-person"
GT_STATE_OUT_OF_ROSTER = "gt-cluster-out-of-roster"
GT_STATE_UNDECIDABLE = "gt-cluster-undecidable"

ADMISSION_TERMS = (
    "layer_a",
    "layer_b",
    "attestation_integrity",
    "isolation_revalidation",
    "attestation_assurance",
    "manifest_binding",
    "snapshot_binding",
    "manifest_contract",
    "artifact_contract_k",
    "prediction_source_authorization",
    "frozen_gt_validation",
    "reference_snapshot_validation",
    "v1_rejection_check",
)


@dataclass(frozen=True, slots=True)
class GtValidationReport:
    """Frozen GT Validation 六查（R3 §4.7）."""

    gt_set_equal: bool
    exactly_one_verdict: bool
    person_resolvable: bool
    states_independent: bool
    verdict_counts: Mapping[str, int]

    @property
    def ok(self) -> bool:
        return (
            self.gt_set_equal
            and self.exactly_one_verdict
            and self.person_resolvable
            and self.states_independent
        )


@dataclass(frozen=True, slots=True)
class SnapshotValidationReport:
    """Reference Snapshot Validation（schema/完整性/provenance + 源端核验）."""

    schema_ok: bool
    hash_ok: bool
    counts_ok: bool
    identity_unique: bool
    provenance_complete: bool
    drift_free: bool | None
    isolation_valid: bool | None

    @property
    def ok(self) -> bool:
        return all(
            v is True
            for v in (
                self.schema_ok,
                self.hash_ok,
                self.counts_ok,
                self.identity_unique,
                self.provenance_complete,
                self.drift_free,
                self.isolation_valid,
            )
        )


@dataclass(frozen=True, slots=True)
class MemberOutcomeRow:
    """member-level 机械结果（原始事实字段；分类标签未冻结，不发明）."""

    cluster_id: UUID
    observation_id: UUID
    gt_state: str
    truth_person_id: UUID | None
    prediction_type: str
    top1_person_id: UUID | None
    top1_score: float | None
    matches_truth: bool | None


@dataclass(frozen=True, slots=True)
class MechanicalScoringResult:
    input_class: str
    rejection_outcome: str
    layer_a: str
    layer_b: str
    attestation_integrity: str
    isolation_revalidation: str
    assurance: str
    admission: bool
    conditions: Mapping[str, str]
    gt_validation: GtValidationReport | None
    member_outcomes: tuple[MemberOutcomeRow, ...]
    reasons: tuple[str, ...]


class MechanicalScoringService:
    """Verification-layer state machine + admission + member-level outcomes."""

    def __init__(
        self,
        manifest_service: TargetManifestService,
        snapshot_service: ReferenceSnapshotService,
        artifact_service: PredictionArtifactV2Service,
        attestation_service: IsolationAttestationService,
        calibration_repository: CalibrationAnnotationRepository,
        person_repository: PersonRepository,
    ) -> None:
        self._manifests = manifest_service
        self._snapshots = snapshot_service
        self._artifacts = artifact_service
        self._attestations = attestation_service
        self._calibration = calibration_repository
        self._people = person_repository

    # ------------------------------------------------------------------ score

    def score(
        self,
        *,
        artifact_path: Path,
        target_manifest_path: Path,
        reference_snapshot_path: Path,
        isolation_attestation_path: Path,
    ) -> MechanicalScoringResult:
        artifact_path = Path(artifact_path)
        input_class = self._artifacts.classify(artifact_path)

        # Gate 0：v1 / unknown → REJECT-TERMINAL（正确拒绝；无评分产物）
        if input_class != INPUT_CLASS_V2:
            reason = (
                "ERR-V1-INPUT: input classified as prediction-artifact-v1 — "
                "REJECT-TERMINAL（v1 不得作为认证式预测数据集）"
                if input_class == INPUT_CLASS_V1
                else "ERR-UNPROVABLE: artifact unreadable or unknown schema — "
                "REJECT-TERMINAL"
            )
            return MechanicalScoringResult(
                input_class=input_class,
                rejection_outcome=REJECTION_AS_REQUIRED,
                layer_a="not-run",
                layer_b="not-run",
                attestation_integrity="not-run",
                isolation_revalidation="not-run",
                assurance="unprovable",
                admission=False,
                conditions={term: "not-run" for term in ADMISSION_TERMS},
                gt_validation=None,
                member_outcomes=(),
                reasons=(reason,),
            )

        reasons: list[str] = []

        # Manifest：Layer A 永远执行；Layer B = 重读源（评分路径为在线）
        manifest_verification = self._manifests.verify_manifest(
            Path(target_manifest_path), source_check=True
        )
        manifest_document = None
        try:
            manifest_document = self._manifests.read_document(
                Path(target_manifest_path)
            )
        except ValidationError as exc:
            reasons.append(f"ERR-SET-EQUALITY: manifest unreadable ({exc})")

        # Artifact：v2 验证（含合同重派生 + 双绑定 + 双射）
        artifact_verification = self._artifacts.verify_artifact_v2(
            artifact_path,
            target_manifest_path=Path(target_manifest_path),
            reference_snapshot_path=Path(reference_snapshot_path),
        )
        content: dict = {}
        try:
            content = self._artifacts.read_content(artifact_path)
        except ValidationError as exc:
            reasons.append(f"ERR-V1-INPUT: {exc}")

        # Snapshot：独立内容验证（schema/完整性/provenance + 源端核验）
        snapshot_report = self._validate_snapshot(Path(reference_snapshot_path))

        # Attestation：Integrity / Isolation Revalidation / Assurance（六维映射）
        attestation_verification = self._attestations.verify_attestation(
            Path(isolation_attestation_path),
            target_manifest_path=Path(target_manifest_path),
            reference_snapshot_path=Path(reference_snapshot_path),
        )
        # 工件 ↔ Attestation 直接一致性（transitive 之外再显式核对一次）
        try:
            attestation_document = self._attestations.read_document(
                Path(isolation_attestation_path)
            )
            expected_invariant = content.get("isolation_invariant_sha256")
            linked = (
                attestation_document.isolation_invariant_sha256 == expected_invariant
                and str(attestation_document.content.get("target_manifest_id"))
                == str(content.get("target_manifest_id"))
                and str(attestation_document.content.get("reference_snapshot_id"))
                == str(content.get("reference_snapshot_id"))
            )
        except ValidationError as exc:
            linked = False
            reasons.append(f"ERR-UNPROVABLE: attestation unreadable ({exc})")
        isolation_revalidation = attestation_verification.revalidation
        if not linked:
            isolation_revalidation = "fail"
            reasons.append(
                "ERR-IDENTITY-MISMATCH: artifact isolation binding != attestation record"
            )

        # Frozen GT Validation（六查；只读派生）
        gt_report = self._validate_frozen_gt(content, manifest_document, reasons)

        # 六维组合 + 13 项准入
        layer_a = (
            "pass"
            if (
                manifest_verification.layer_a == "pass"
                and artifact_verification.hash_matches
                and artifact_verification.keys_valid
                and artifact_verification.schema_version_valid
            )
            else "fail"
        )
        layer_b = manifest_verification.layer_b
        source = str(content.get("prediction_source"))
        conditions = {
            "layer_a": layer_a,
            "layer_b": layer_b,
            "attestation_integrity": attestation_verification.integrity,
            "isolation_revalidation": isolation_revalidation,
            "attestation_assurance": attestation_verification.assurance,
            "manifest_binding": _flag(artifact_verification.manifest_binding_matches),
            "snapshot_binding": _flag(artifact_verification.snapshot_binding_matches),
            "manifest_contract": manifest_verification.layer_a,
            "artifact_contract_k": _flag(artifact_verification.contracts_valid),
            "prediction_source_authorization": (
                "pass" if source in SCORING_AUTHORIZED_SOURCES else "fail"
            ),
            "frozen_gt_validation": "pass" if gt_report.ok else "fail",
            "reference_snapshot_validation": (
                "pass" if snapshot_report.ok else "fail"
            ),
            "v1_rejection_check": "pass",  # v2 输入 → not-required（=pass）
        }
        if source not in SCORING_AUTHORIZED_SOURCES and source:
            reasons.append(
                f"ERR-SOURCE-OUT-OF-SCOPE: prediction_source={source!r} "
                "not authorized this stage (S-B only)"
            )
        admission = all(
            _term_ok(term, value) for term, value in conditions.items()
        )

        member_outcomes: tuple[MemberOutcomeRow, ...] = ()
        if admission:
            member_outcomes = self._derive_member_outcomes(content, gt_report)
        else:
            failing = [
                k for k, v in conditions.items() if not _term_ok(k, v)
            ]
            reasons.append(
                "NO SCORING: admission=false — failing/undetermined terms: "
                + ", ".join(failing)
            )
        return MechanicalScoringResult(
            input_class=input_class,
            rejection_outcome=REJECTION_NOT_REQUIRED,
            layer_a=layer_a,
            layer_b=layer_b,
            attestation_integrity=attestation_verification.integrity,
            isolation_revalidation=isolation_revalidation,
            assurance=attestation_verification.assurance,
            admission=admission,
            conditions=conditions,
            gt_validation=gt_report,
            member_outcomes=member_outcomes,
            reasons=tuple(reasons),
        )

    # ---------------------------------------------------------------- helpers

    def _validate_snapshot(self, snapshot_path: Path) -> SnapshotValidationReport:
        try:
            inner = self._snapshots.verify_snapshot(
                Path(snapshot_path), cross_check_current_state=True
            )
        except ValidationError:
            return SnapshotValidationReport(
                schema_ok=False,
                hash_ok=False,
                counts_ok=False,
                identity_unique=False,
                provenance_complete=False,
                drift_free=None,
                isolation_valid=None,
            )
        return SnapshotValidationReport(
            schema_ok=inner.schema_version_valid,
            hash_ok=inner.hash_matches,
            counts_ok=inner.entry_count_matches and inner.person_count_matches,
            identity_unique=inner.entry_identity_unique,
            provenance_complete=inner.provenance_complete,
            drift_free=inner.embedding_drift_free,
            isolation_valid=inner.isolation_valid,
        )

    def _validate_frozen_gt(
        self,
        content: dict,
        manifest_document,
        reasons: list[str],
    ) -> GtValidationReport:
        try:
            dataset_uuid = UUID(str(content.get("dataset_id")))
            dataset_version = str(content.get("dataset_version"))
            manifest_cluster_ids = {
                UUID(str(c))
                for c in (
                    manifest_document.content["dataset_cluster_ids"]
                    if manifest_document is not None
                    else []
                )
            }
        except (KeyError, ValueError, TypeError):
            return GtValidationReport(
                gt_set_equal=False,
                exactly_one_verdict=False,
                person_resolvable=False,
                states_independent=False,
                verdict_counts={},
            )
        try:
            rows = self._calibration.list_ground_truth(
                dataset_id=dataset_uuid, dataset_version=dataset_version
            )
        except ValidationError as exc:
            reasons.append(f"ERR-GT-VALIDATION: GT unreadable ({exc})")
            return GtValidationReport(
                gt_set_equal=False,
                exactly_one_verdict=False,
                person_resolvable=False,
                states_independent=False,
                verdict_counts={},
            )
        by_cluster = Counter(row.cluster_id for row in rows)
        gt_cluster_ids = set(by_cluster)
        people_ids = {
            person.id for person in self._people.list_all() if person.id is not None
        }
        allowed_verdicts = {"person", "out_of_roster", "undecidable"}
        person_resolvable = all(
            row.verdict != "person"
            or (row.person_id is not None and row.person_id in people_ids)
            for row in rows
        )
        report = GtValidationReport(
            gt_set_equal=gt_cluster_ids == manifest_cluster_ids,
            exactly_one_verdict=all(count == 1 for count in by_cluster.values()),
            person_resolvable=person_resolvable,
            states_independent=all(row.verdict in allowed_verdicts for row in rows),
            verdict_counts=dict(Counter(row.verdict for row in rows)),
        )
        if not report.ok:
            reasons.append(
                "ERR-GT-VALIDATION: frozen GT validation failed "
                f"(set_equal={report.gt_set_equal}, "
                f"exactly_one={report.exactly_one_verdict}, "
                f"person_resolvable={report.person_resolvable}, "
                f"states={report.states_independent})"
            )
        return report

    def _gt_state_map(self, content: dict) -> dict[UUID, tuple[str, UUID | None]]:
        """成员级 GT 三态派生（verdict 直接映射；禁止 NULL 塌缩）."""
        rows = self._calibration.list_ground_truth(
            dataset_id=UUID(str(content["dataset_id"])),
            dataset_version=str(content["dataset_version"]),
        )
        mapping: dict[UUID, tuple[str, UUID | None]] = {}
        for row in rows:
            if row.verdict == "person":
                mapping[row.cluster_id] = (GT_STATE_PERSON, row.person_id)
            elif row.verdict == "out_of_roster":
                mapping[row.cluster_id] = (GT_STATE_OUT_OF_ROSTER, None)
            else:
                mapping[row.cluster_id] = (GT_STATE_UNDECIDABLE, None)
        return mapping

    def _derive_member_outcomes(
        self, content: dict, gt_report: GtValidationReport
    ) -> tuple[MemberOutcomeRow, ...]:
        del gt_report  # 已由准入保证 ok
        state_map = self._gt_state_map(content)
        rows: list[MemberOutcomeRow] = []
        for item in content.get("predictions") or []:
            cluster_id = UUID(str(item["cluster_id"]))
            state, truth = state_map.get(
                cluster_id, (GT_STATE_UNDECIDABLE, None)
            )
            top1_person = (
                UUID(str(item["top1_person_id"]))
                if item.get("top1_person_id") is not None
                else None
            )
            matches: bool | None = None
            if state == GT_STATE_PERSON and item.get("prediction_type") == "predicted":
                matches = top1_person == truth
            rows.append(
                MemberOutcomeRow(
                    cluster_id=cluster_id,
                    observation_id=UUID(str(item["observation_id"])),
                    gt_state=state,
                    truth_person_id=truth,
                    prediction_type=str(item.get("prediction_type")),
                    top1_person_id=top1_person,
                    top1_score=item.get("top1_score"),
                    matches_truth=matches,
                )
            )
        return tuple(rows)


def _flag(value: bool | None) -> str:
    if value is None:
        return "not-run"
    return "pass" if value else "fail"


def _term_ok(term: str, value: str) -> bool:
    """准入项判定：assurance 的合法值域为 valid-and-verified（非字面 pass）."""
    if term == "attestation_assurance":
        return value == "valid-and-verified"
    return value == "pass"
