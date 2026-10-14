"""S-B-6 Prediction Artifact v2（``prediction-artifact-v2``）builder + verifier.

依据 R3 §5.2 与 ORD-1..8 裁决：
* 条目身份 = Target Cluster Member ``(cluster_run_id, cluster_id, observation_id)``；
* ``prediction_id`` = UUIDv5 确定性派生（ORD-4 常量 + 配方双记录一致）；
* 权威字段 = top1/top2 person/score；``rank`` / ``margin`` 仅派生（ORD-1）；
* ``computed_at`` 在 Envelope、必填可空、不入哈希域（ORD-6）；
* ``score_semantics`` / ``git_commit`` 保留为非权威描述字段（ORD-7）；
* 双绑定 = Manifest + Snapshot 的 ID + 重算 SHA 双 fail-closed（OG-2=A）；
* ``isolation_invariant_sha256`` 取自经完整性验证的 Attestation 文档（OG-1）；
* ``evidence_winning_reference_observation_id``（ORD-2 / F-1 补齐）：键必填可空；
  builder 以**现有余弦内核**（L2 归一化 + 6 位小数量化；并列严格相等）+ 规范化
  ``observation_id`` 字符串序最小者生成；``top1_person_id``/``top1_score`` 为 NULL
  或无候选 ⇒ null（不得凭空推导）；候选不可读/漂移/维度不一致 ⇒ null（builder）与
  ``unprovable``（verifier，不得予过）；verifier 独立重推导（硬约束 + winning 复核），
  不使用 builder 写入值；
* Artifact ↔ Manifest 逐项双射；输入分类 Gate 0 区分 v1/v2/unknown（B7.2）。

零业务写入；发布复用不可变文件层（原子 + 拒绝覆盖）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from photo_archiver.application.ports import SnapshotStore, SimilarityKernelFactory
from photo_archiver.application.services.reference_snapshot_service import (
    ReferenceSnapshotService,
    SnapshotDocument,
    canonical_json,
    embedding_sha256,
)
from photo_archiver.application.services.sb6_contract import (
    ARTIFACT_V2_CONTENT_KEYS,
    ARTIFACT_V2_ITEM_KEYS,
    INPUT_CLASS_UNKNOWN,
    INPUT_CLASS_V1,
    INPUT_CLASS_V2,
    ISOLATION_ATTESTATION_SCHEMA_VERSION,
    PREDICTION_ARTIFACT_V1_SCHEMA_VERSION,
    PREDICTION_ARTIFACT_V2_SCHEMA_VERSION,
    PREDICTION_SOURCES,
    PREDICTION_SOURCE_SB,
    PREDICTION_TYPE_NO_CANDIDATE,
    PREDICTION_TYPE_PREDICTED,
    SB_SCORE_SEMANTICS,
    SB_SCORER_VERSION,
    PredictionRecordV2,
    _as_uuid,
    derive_margin,
    derive_prediction_type,
    derive_rank,
    prediction_item_payload,
    validate_prediction_record_v2,
)
from photo_archiver.application.services.target_manifest_service import (
    TargetManifestDocument,
    TargetManifestService,
)
from photo_archiver.domain import FaceEmbedding
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.repositories.face_observation_repository import (
    FaceObservationRepository,
)

# evidence winning-check 状态（B/C：builder 生成与 verifier 重验证共用同一 derivation）
_EVIDENCE_DETERMINED = "determined"
_EVIDENCE_NONE = "none"  # 规则不适用/无候选（source-aware 合法 null）
_EVIDENCE_UNPROVABLE = "unprovable"  # 候选不可读/漂移/维度不一致——不得猜测

_RESULT_PASS = "pass"
_RESULT_FAIL = "fail"
_RESULT_UNPROVABLE = "unprovable"


@dataclass(frozen=True, slots=True)
class PredictionArtifactV2Result:
    artifact_id: UUID
    artifact_path: Path
    artifact_sha256: str
    prediction_source: str
    entry_count: int
    cluster_count: int


@dataclass(frozen=True, slots=True)
class PredictionArtifactV2Verification:
    """验证结果：``input_class`` 显式区分 v1/v2/unknown（Gate 0 依据）.

    ``evidence_verification`` ∈ {pass, fail, unprovable, not-run}——
    evidence winning-check 的独立维度（not-run = 未提供 snapshot 路径，未执行）。
    """

    file_exists: bool
    input_class: str
    schema_version_valid: bool
    hash_matches: bool
    keys_valid: bool
    binding_consistent: bool
    manifest_binding_matches: bool | None
    snapshot_binding_matches: bool | None
    bijection: bool | None
    contracts_valid: bool | None
    evidence_verification: str = "not-run"

    @property
    def ok(self) -> bool:
        return all(
            v is True or v is None
            for v in (
                self.file_exists,
                self.input_class == INPUT_CLASS_V2,
                self.schema_version_valid,
                self.hash_matches,
                self.keys_valid,
                self.binding_consistent,
                self.manifest_binding_matches,
                self.snapshot_binding_matches,
                self.bijection,
                self.contracts_valid,
            )
        ) and self.evidence_verification in ("pass", "not-run")


class PredictionArtifactV2Service:
    """Build + verify immutable Prediction Artifact v2 files（零业务写入）."""

    def __init__(
        self,
        snapshot_service: ReferenceSnapshotService,
        manifest_service: TargetManifestService,
        artifact_store: SnapshotStore,
        observation_repository: FaceObservationRepository,
        similarity_factory: SimilarityKernelFactory,
    ) -> None:
        """Store read-only dependencies（evidence derivation 需观测向量 + 现成 cosine 内核）."""
        self._snapshots = snapshot_service
        self._manifests = manifest_service
        self._store = artifact_store
        self._observations = observation_repository
        self._similarity = similarity_factory

    # ----------------------------------------------------------------- build

    def build_artifact_v2(
        self,
        *,
        prediction_source: str,
        scorer_version: str,
        predictions: list[PredictionRecordV2],
        reference_snapshot_path: Path,
        reference_snapshot_id: UUID | str,
        reference_snapshot_sha256: str,
        target_manifest_path: Path,
        target_manifest_id: UUID | str,
        target_manifest_sha256: str,
        isolation_attestation_path: Path,
        destination: Path,
        computed_at: str | None = None,
        git_commit: str | None = None,
    ) -> PredictionArtifactV2Result:
        if prediction_source not in PREDICTION_SOURCES:
            raise ValidationError(
                f"ERR-CONTRACT-FIELDS: unknown prediction source {prediction_source!r}"
            )
        if not predictions:
            raise ValidationError(
                "ERR-CONTRACT-FIELDS: no predictions given — v2 artifact is NOT "
                "CREATABLE without prediction output"
            )
        if destination is None:
            raise ValidationError("ERR-CONTRACT-FIELDS: destination path is required")

        # 双绑定：Snapshot（ID + 重算 SHA）
        snapshot_document = self._snapshots.read_document(Path(reference_snapshot_path))
        inner = self._snapshots.verify_snapshot(Path(reference_snapshot_path))
        if not inner.ok:
            raise ValidationError(
                f"ERR-HASH-MISMATCH: reference snapshot failed verification: {inner}"
            )
        if snapshot_document.snapshot_id != _as_uuid(reference_snapshot_id):
            raise ValidationError("ERR-IDENTITY-MISMATCH: reference snapshot ID mismatch")
        snapshot_recomputed = hashlib.sha256(
            canonical_json(snapshot_document.content)
        ).hexdigest()
        if snapshot_recomputed != reference_snapshot_sha256:
            raise ValidationError("ERR-HASH-MISMATCH: reference snapshot SHA256 mismatch")

        # 双绑定：Manifest（ID + 重算 SHA）
        manifest_document = self._manifests.read_document(Path(target_manifest_path))
        if manifest_document.manifest_id != _as_uuid(target_manifest_id):
            raise ValidationError("ERR-IDENTITY-MISMATCH: target manifest ID mismatch")
        manifest_recomputed = self._manifests.manifest_sha256(manifest_document)
        if manifest_recomputed != target_manifest_sha256:
            raise ValidationError("ERR-HASH-MISMATCH: target manifest SHA256 mismatch")

        # Attestation 完整性 + 与本工件绑定一致（不得伪造 isolation_invariant_sha256）
        attestation_document, isolation_invariant_sha256 = self._read_attestation(
            Path(isolation_attestation_path), manifest_document, snapshot_document
        )
        del attestation_document

        manifest_entries = manifest_document.content["entries"]
        manifest_cluster_run_id = UUID(str(manifest_document.content["cluster_run_id"]))
        manifest_keys = {
            (str(e["cluster_id"]), str(e["observation_id"])): e
            for e in manifest_entries
        }
        seen: set[tuple[str, str]] = set()
        item_payloads: list[dict] = []
        for record in predictions:
            validate_prediction_record_v2(record, prediction_source)
            if record.cluster_run_id != manifest_cluster_run_id:
                raise ValidationError(
                    "ERR-IDENTITY-MISMATCH: prediction cluster_run_id does not match "
                    "the pinned manifest generation"
                )
            key = (str(record.cluster_id), str(record.observation_id))
            entry = manifest_keys.get(key)
            if entry is None:
                raise ValidationError(
                    f"ERR-IDENTITY-MISMATCH: orphan prediction {key} — "
                    "not a target manifest entry"
                )
            if key in seen:
                raise ValidationError(
                    f"ERR-COUNT-MISMATCH: duplicate prediction for entry {key}"
                )
            seen.add(key)
            if str(entry["photo_id"]) != str(record.photo_id):
                raise ValidationError(
                    f"ERR-IDENTITY-MISMATCH: prediction photo_id does not match "
                    f"manifest entry {key}"
                )
            evidence_id, _evidence_status = self._derive_evidence(
                top1_person_id=record.top1_person_id,
                top1_score=record.top1_score,
                observation_id=record.observation_id,
                photo_id=record.photo_id,
                snapshot_document=snapshot_document,
            )
            item_payloads.append(
                prediction_item_payload(
                    record,
                    evidence_winning_reference_observation_id=evidence_id,
                )
            )
        if len(seen) != len(manifest_keys):
            raise ValidationError(
                "ERR-COUNT-MISMATCH: manifest entries without prediction — "
                "artifact requires entry-level bijection"
            )
        item_payloads.sort(
            key=lambda e: (e["cluster_id"], e["observation_id"])
        )

        content = {
            "schema_version": PREDICTION_ARTIFACT_V2_SCHEMA_VERSION,
            "prediction_source": prediction_source,
            "scorer_version": scorer_version,
            "reference_snapshot_id": str(snapshot_document.snapshot_id),
            "reference_snapshot_sha256": reference_snapshot_sha256,
            "target_manifest_id": str(manifest_document.manifest_id),
            "target_manifest_sha256": target_manifest_sha256,
            "dataset_id": str(manifest_document.content["dataset_id"]),
            "dataset_version": str(manifest_document.content["dataset_version"]),
            "input_population_scope": str(
                snapshot_document.content["population_scope"]
            ),
            "entry_count": len(item_payloads),
            "cluster_count": len(
                {e["cluster_id"] for e in item_payloads}
            ),
            "score_semantics": (
                dict(SB_SCORE_SEMANTICS) if scorer_version == SB_SCORER_VERSION else None
            ),
            "git_commit": git_commit,
            "threshold": None,
            "isolation_invariant_sha256": isolation_invariant_sha256,
            "predictions": item_payloads,
        }
        content_bytes = canonical_json(content)
        artifact_sha = hashlib.sha256(content_bytes).hexdigest()
        artifact_id = uuid4()
        document = {
            "artifact_id": str(artifact_id),
            "schema_version": PREDICTION_ARTIFACT_V2_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "computed_at": computed_at,
            "artifact_sha256": artifact_sha,
            "content": content,
        }
        self._store.write_atomic(Path(destination), canonical_json(document))

        post = self.verify_artifact_v2(
            Path(destination),
            target_manifest_path=Path(target_manifest_path),
            reference_snapshot_path=Path(reference_snapshot_path),
        )
        if not post.ok:
            raise ValidationError(f"post-publish verification failed: {post}")
        return PredictionArtifactV2Result(
            artifact_id=artifact_id,
            artifact_path=Path(destination),
            artifact_sha256=artifact_sha,
            prediction_source=prediction_source,
            entry_count=len(item_payloads),
            cluster_count=len({e["cluster_id"] for e in item_payloads}),
        )

    def _read_attestation(
        self,
        attestation_path: Path,
        manifest_document: TargetManifestDocument,
        snapshot_document,
    ) -> tuple[dict, str]:
        if not self._store.path_exists(attestation_path):
            raise ValidationError(
                "ERR-IDENTITY-MISMATCH: isolation attestation file missing"
            )
        try:
            document = json.loads(
                self._store.read_bytes(attestation_path).decode("utf-8")
            )
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValidationError(
                f"ERR-HASH-MISMATCH: attestation unparseable ({exc})"
            ) from None
        if document.get("schema_version") != ISOLATION_ATTESTATION_SCHEMA_VERSION:
            raise ValidationError("ERR-HASH-MISMATCH: attestation schema unsupported")
        content = document.get("content") or {}
        recomputed = hashlib.sha256(canonical_json(content)).hexdigest()
        if document.get("isolation_invariant_sha256") != recomputed:
            raise ValidationError("ERR-HASH-MISMATCH: attestation integrity failure")
        if str(content.get("target_manifest_id")) != str(manifest_document.manifest_id) or (
            self._manifests.manifest_sha256(manifest_document)
            != content.get("target_manifest_sha256")
        ):
            raise ValidationError(
                "ERR-IDENTITY-MISMATCH: attestation bound to a different manifest"
            )
        if str(content.get("reference_snapshot_id")) != str(
            snapshot_document.snapshot_id
        ) or (
            hashlib.sha256(canonical_json(snapshot_document.content)).hexdigest()
            != content.get("reference_snapshot_sha256")
        ):
            raise ValidationError(
                "ERR-IDENTITY-MISMATCH: attestation bound to a different snapshot"
            )
        return document, str(document["isolation_invariant_sha256"])

    # ------------------------------------------------------- evidence (ORD-2)

    def _derive_evidence(
        self,
        *,
        top1_person_id: UUID | None,
        top1_score: float | None,
        observation_id: UUID,
        photo_id: UUID,
        snapshot_document,
    ) -> tuple[str | None, str]:
        """确定性 winning reference（ORD-2；builder 生成与 verifier 重验证共用）.

        规则：
        * source-aware：``top1_person_id`` 或 ``top1_score`` 为 NULL ⇒ 无分数证据
          ⇒ ``(None, "none")``（不得凭空推导）；
        * 候选 = 快照中 ``person_id == top1_person_id`` 的全部 entry；
          候选为空 ⇒ ``(None, "none")``；
        * 每个候选与目标观测的余弦按**现有内核**（L2 归一化 + 6 位小数量化）
          计算；量化网格上的严格相等即并列判据；
        * 并列 ⇒ 取规范化 ``observation_id`` 字符串序（Unicode 码点）最小者；
        * 任一所需 embedding 不可读 / 与 entry 记录的 ``embedding_sha256`` 不符
          （漂移）/ 维度不一致 ⇒ ``(None, "unprovable")``——不得猜测。
        """
        if top1_person_id is None or top1_score is None:
            return None, _EVIDENCE_NONE
        candidates = [
            entry
            for entry in snapshot_document.entries
            if str(entry["person_id"]) == str(top1_person_id)
        ]
        if not candidates:
            return None, _EVIDENCE_NONE
        target_vector = self._find_observation_vector(photo_id, observation_id)
        if target_vector is None:
            return None, _EVIDENCE_UNPROVABLE
        candidate_vectors: list[tuple[str, tuple[float, ...]]] = []
        for entry in candidates:
            vector = self._find_observation_vector(
                UUID(str(entry["photo_id"])), UUID(str(entry["observation_id"]))
            )
            if vector is None:
                return None, _EVIDENCE_UNPROVABLE
            if embedding_sha256(vector) != entry["embedding_sha256"]:
                return None, _EVIDENCE_UNPROVABLE  # 漂移：冻结证据不成立
            candidate_vectors.append((str(entry["observation_id"]), vector))
        try:
            lookup = self._similarity.build(
                [FaceEmbedding(vector=target_vector)]
                + [FaceEmbedding(vector=v) for _, v in candidate_vectors]
            )
        except ValueError:
            return None, _EVIDENCE_UNPROVABLE  # 维度不一致等
        cosines = [
            lookup.similarity(0, index + 1)
            for index in range(len(candidate_vectors))
        ]
        max_value = max(cosines)
        winners = [
            candidate_vectors[index][0]
            for index, cosine in enumerate(cosines)
            if cosine == max_value  # 现成内核的量化网格上严格相等
        ]
        return min(winners), _EVIDENCE_DETERMINED  # 字符串序（Unicode 码点）最小者

    def _find_observation_vector(
        self, photo_id: UUID, observation_id: UUID
    ) -> tuple[float, ...] | None:
        try:
            observations = self._observations.list_by_photo(photo_id)
        except ValidationError:
            return None
        for observation in observations:
            if observation.id == observation_id:
                return observation.embedding.vector
        return None

    def _verify_evidence(
        self, items: list[dict], snapshot_document
    ) -> tuple[str, list[str]]:
        """verifier 独立重验证（B/C）：硬约束 + 与 builder 同 derivation 的 winning 重推导.

        单向契约（R3 §5.2.1）：evidence 为 NULL = 合法省略（跳过）；
        非 NULL ⇒ 必须可解析 ∈ Reference Snapshot、person == top1_person_id，
        且等于独立重推导的 winning reference。
        重推导不可建立（漂移/不可读/不适用）⇒ ``unprovable``（不得予过）。
        """
        entries_by_observation = {
            str(entry["observation_id"]): entry
            for entry in snapshot_document.entries
        }
        statuses: list[str] = []
        reasons: list[str] = []
        for item in items:
            evidence = item.get("evidence_winning_reference_observation_id")
            if evidence is None:
                continue
            try:
                top1_person_id = _uuid_or_none(item.get("top1_person_id"))
                observation_id = UUID(str(item["observation_id"]))
                photo_id = UUID(str(item["photo_id"]))
                evidence_uuid = UUID(str(evidence))
            except (KeyError, ValueError, TypeError):
                statuses.append(_RESULT_FAIL)
                reasons.append(
                    f"ERR-CONTRACT-FIELDS: evidence/identity fields unparseable ({evidence!r})"
                )
                continue
            entry = entries_by_observation.get(str(evidence_uuid))
            if entry is None:
                statuses.append(_RESULT_FAIL)
                reasons.append(
                    "ERR-CONTRACT-FIELDS: evidence is not a Reference Snapshot entry "
                    f"({evidence})"
                )
                continue
            if str(entry["person_id"]) != str(item.get("top1_person_id")):
                statuses.append(_RESULT_FAIL)
                reasons.append(
                    "ERR-CONTRACT-FIELDS: evidence person_id != top1_person_id"
                )
                continue
            derived, derived_status = self._derive_evidence(
                top1_person_id=top1_person_id,
                top1_score=item.get("top1_score"),
                observation_id=observation_id,
                photo_id=photo_id,
                snapshot_document=snapshot_document,
            )
            if derived_status == _EVIDENCE_UNPROVABLE:
                statuses.append(_RESULT_UNPROVABLE)
                reasons.append(
                    "ERR-UNPROVABLE: evidence winning-check indeterminate "
                    "(drifted or unreadable reference embeddings)"
                )
                continue
            if derived_status == _EVIDENCE_NONE or derived != str(evidence_uuid):
                statuses.append(_RESULT_FAIL)
                reasons.append(
                    f"ERR-CONTRACT-FIELDS: evidence {evidence} is not the derived "
                    f"winning reference (derived={derived})"
                )
                continue
        if not statuses:
            return _RESULT_PASS, []
        if _RESULT_FAIL in statuses:
            return _RESULT_FAIL, reasons
        return _RESULT_UNPROVABLE, reasons

    # ------------------------------------------------------------------ read

    def classify(self, artifact_path: Path) -> str:
        """Gate 0：输入分类（v2 / v1 / unknown）——文件缺失/不可读 → unknown."""
        path = Path(artifact_path)
        if not self._store.path_exists(path):
            return INPUT_CLASS_UNKNOWN
        try:
            document = json.loads(self._store.read_bytes(path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return INPUT_CLASS_UNKNOWN
        schema = document.get("schema_version")
        if schema == PREDICTION_ARTIFACT_V2_SCHEMA_VERSION:
            return INPUT_CLASS_V2
        if schema == PREDICTION_ARTIFACT_V1_SCHEMA_VERSION:
            return INPUT_CLASS_V1
        return INPUT_CLASS_UNKNOWN

    def read_content(self, artifact_path: Path) -> dict:
        """读取 v2 工件 content（schema 校验；消费者只读入口）."""
        path = Path(artifact_path)
        if not self._store.path_exists(path):
            raise ValidationError(f"artifact file missing: {path}")
        try:
            document = json.loads(self._store.read_bytes(path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValidationError(f"artifact file unparseable: {exc}") from None
        if document.get("schema_version") != PREDICTION_ARTIFACT_V2_SCHEMA_VERSION:
            raise ValidationError(
                "ERR-V1-INPUT: not a prediction-artifact-v2 document "
                f"(schema={document.get('schema_version')!r})"
            )
        return document["content"]

    # ---------------------------------------------------------------- verify

    def verify_artifact_v2(
        self,
        artifact_path: Path,
        *,
        target_manifest_path: Path | None = None,
        reference_snapshot_path: Path | None = None,
    ) -> PredictionArtifactV2Verification:
        path = Path(artifact_path)
        if not self._store.path_exists(path):
            return PredictionArtifactV2Verification(
                file_exists=False,
                input_class=INPUT_CLASS_UNKNOWN,
                schema_version_valid=False,
                hash_matches=False,
                keys_valid=False,
                binding_consistent=False,
                manifest_binding_matches=None,
                snapshot_binding_matches=None,
                bijection=None,
                contracts_valid=None,
            )
        try:
            document = json.loads(self._store.read_bytes(path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return PredictionArtifactV2Verification(
                file_exists=True,
                input_class=INPUT_CLASS_UNKNOWN,
                schema_version_valid=False,
                hash_matches=False,
                keys_valid=False,
                binding_consistent=False,
                manifest_binding_matches=None,
                snapshot_binding_matches=None,
                bijection=None,
                contracts_valid=None,
            )
        schema = document.get("schema_version")
        input_class = (
            INPUT_CLASS_V2
            if schema == PREDICTION_ARTIFACT_V2_SCHEMA_VERSION
            else (
                INPUT_CLASS_V1
                if schema == PREDICTION_ARTIFACT_V1_SCHEMA_VERSION
                else INPUT_CLASS_UNKNOWN
            )
        )
        content = document.get("content") or {}
        recomputed = hashlib.sha256(canonical_json(content)).hexdigest()
        hash_ok = document.get("artifact_sha256") == recomputed
        schema_ok = schema == PREDICTION_ARTIFACT_V2_SCHEMA_VERSION
        if not schema_ok:
            return PredictionArtifactV2Verification(
                file_exists=True,
                input_class=input_class,
                schema_version_valid=False,
                hash_matches=hash_ok,
                keys_valid=False,
                binding_consistent=False,
                manifest_binding_matches=None,
                snapshot_binding_matches=None,
                bijection=None,
                contracts_valid=None,
            )
        keys_ok = set(content.keys()) == set(ARTIFACT_V2_CONTENT_KEYS) and all(
            isinstance(e, dict) and set(e.keys()) == set(ARTIFACT_V2_ITEM_KEYS)
            for e in content.get("predictions") or []
        )
        binding_consistent = all(
            content.get(k) is not None
            for k in (
                "reference_snapshot_id",
                "reference_snapshot_sha256",
                "target_manifest_id",
                "target_manifest_sha256",
                "isolation_invariant_sha256",
            )
        ) and content.get("threshold", "missing") is None
        source = str(content.get("prediction_source"))
        contracts_ok: bool
        if source in PREDICTION_SOURCES:
            try:
                contracts_ok = self._contract_items_valid(
                    content.get("predictions") or [], source
                )
            except ValidationError:
                contracts_ok = False
        else:
            contracts_ok = False
        manifest_binding: bool | None = None
        snapshot_binding: bool | None = None
        bijection: bool | None = None
        snapshot_document: SnapshotDocument | None = None
        if target_manifest_path is not None:
            try:
                manifest_document = self._manifests.read_document(
                    Path(target_manifest_path)
                )
                manifest_binding = (
                    str(manifest_document.manifest_id)
                    == str(content.get("target_manifest_id"))
                    and self._manifests.manifest_sha256(manifest_document)
                    == content.get("target_manifest_sha256")
                    and str(manifest_document.content["dataset_id"])
                    == str(content.get("dataset_id"))
                    and str(manifest_document.content["dataset_version"])
                    == str(content.get("dataset_version"))
                    and int(manifest_document.content["entry_count"])
                    == int(content.get("entry_count", -1))
                    and int(manifest_document.content["cluster_count"])
                    == int(content.get("cluster_count", -1))
                )
                manifest_keys = {
                    (str(e["cluster_id"]), str(e["observation_id"])): str(e["photo_id"])
                    for e in manifest_document.content["entries"]
                }
                item_keys = [
                    (str(e.get("cluster_id")), str(e.get("observation_id")))
                    for e in content.get("predictions") or []
                ]
                bijection = (
                    len(item_keys) == len(set(item_keys))
                    and set(item_keys) == set(manifest_keys)
                    and all(
                        manifest_keys.get(k) == str(e.get("photo_id"))
                        for k, e in zip(
                            item_keys, content.get("predictions") or []
                        )
                    )
                )
            except ValidationError:
                manifest_binding = False
                bijection = False
        if reference_snapshot_path is not None:
            try:
                snapshot_document = self._snapshots.read_document(
                    Path(reference_snapshot_path)
                )
                snapshot_binding = (
                    str(snapshot_document.snapshot_id)
                    == str(content.get("reference_snapshot_id"))
                    and hashlib.sha256(
                        canonical_json(snapshot_document.content)
                    ).hexdigest()
                    == content.get("reference_snapshot_sha256")
                )
            except ValidationError:
                snapshot_binding = False
                snapshot_document = None
        evidence_verification = "not-run"
        if reference_snapshot_path is not None:
            if snapshot_document is not None:
                evidence_verification, _evidence_reasons = self._verify_evidence(
                    content.get("predictions") or [], snapshot_document
                )
            else:
                evidence_verification = _RESULT_UNPROVABLE
            if evidence_verification != _RESULT_PASS:
                contracts_ok = False
        return PredictionArtifactV2Verification(
            file_exists=True,
            input_class=input_class,
            schema_version_valid=True,
            hash_matches=hash_ok,
            keys_valid=keys_ok,
            binding_consistent=binding_consistent,
            manifest_binding_matches=manifest_binding,
            snapshot_binding_matches=snapshot_binding,
            bijection=bijection,
            contracts_valid=contracts_ok,
            evidence_verification=evidence_verification,
        )

    def _contract_items_valid(self, items: list[dict], source: str) -> bool:
        """重派生 + R3 §5.2.4 契约（含 top2 成对/唯一性；ORD-8 批准）."""
        try:
            for item in items:
                top1_person = _uuid_or_none(item.get("top1_person_id"))
                top1_score = item.get("top1_score")
                top2_person = _uuid_or_none(item.get("top2_person_id"))
                top2_score = item.get("top2_score")
                record = PredictionRecordV2(
                    cluster_run_id=UUID(str(item["cluster_run_id"])),
                    cluster_id=UUID(str(item["cluster_id"])),
                    observation_id=UUID(str(item["observation_id"])),
                    photo_id=UUID(str(item["photo_id"])),
                    top1_person_id=top1_person,
                    top1_score=top1_score,
                    top2_person_id=top2_person,
                    top2_score=top2_score,
                )
                validate_prediction_record_v2(record, source)
                expected = prediction_item_payload(record)
                if item.get("prediction_id") != expected["prediction_id"]:
                    return False
                if item.get("prediction_type") != expected["prediction_type"]:
                    return False
                if item.get("rank") != derive_rank(
                    expected["prediction_type"], top1_score
                ):
                    return False
                if item.get("margin") != derive_margin(top1_score, top2_score):
                    return False
                expected_type = derive_prediction_type(top1_person)
                if item.get("prediction_type") != expected_type:
                    return False
                if source == PREDICTION_SOURCE_SB and (
                    top1_person is not None and top1_score is None
                ):
                    return False
                if (
                    item.get("prediction_type") == PREDICTION_TYPE_NO_CANDIDATE
                    and any(
                        item.get(k) is not None
                        for k in (
                            "top1_score",
                            "top2_person_id",
                            "top2_score",
                            "rank",
                            "margin",
                        )
                    )
                ):
                    return False
                if item.get("prediction_type") == PREDICTION_TYPE_PREDICTED and (
                    top1_person is None
                ):
                    return False
                if top2_score is not None and top2_person is None:
                    return False
                if (
                    source == PREDICTION_SOURCE_SB
                    and top2_person is not None
                    and top2_score is None
                ):
                    return False
                if (
                    top2_person is not None
                    and top1_person is not None
                    and top2_person == top1_person
                ):
                    return False
        except (KeyError, ValueError, TypeError, ValidationError):
            return False
        return True


def _uuid_or_none(value) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None
