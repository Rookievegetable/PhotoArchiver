"""S-B-5 Prediction Artifact builder + verifier（评估/实验工件，非业务 SSOT）.

将一次 Prediction/Scoring 运行的**给定**输出 + Reference Snapshot 绑定 +
执行溯源冻结为不可变、可验证的 Artifact 文件。

**builder 不计算任何 score**——score/rank/margin 是调用方传入的**结果字段**
（S-B-5 不定义 how score is calculated）；本服务亦不实现 scorer/threshold/
evaluation。

结构（单文件 UTF-8 JSON 文档）::

    {
      "artifact_id": <uuid>,           # 身份 UUID，不入哈希域（§16）
      "schema_version": "prediction-artifact-v1",
      "created_at": <iso>,             # 不入哈希域
      "artifact_sha256": <hex>,        # = sha256(canonical_json(content))
      "content": {
        "schema_version", "prediction_source": "S-B"|"S-A"|"S-C",
        "prediction_method", "prediction_method_version",
        "reference_snapshot_id",        # S-B REQUIRED / S-A,S-C NULL（§7）
        "reference_snapshot_sha256",
        "input_population_scope",       # 冻结记录（§10），COVERAGE_ONLY 不改标
        "dataset_id", "dataset_version",
        "entry_count", "person_count",
        "git_commit",                   # 补充溯源（可选，不替代方法版本，§17）
        "score_semantics",              # 仅 sb-member-max-cosine-v1 的已批准架构元数据
        "threshold": None,              # §19：Owner 未批准前恒 NULL
        "predictions[]"
      }
    }

关键语义：

* **Snapshot 绑定（§8/§9）**：reference_snapshot_id = 身份标识、
  reference_snapshot_sha256 = 内容完整性证明，两者缺一不可；builder 重算
  快照哈希并与传入期望对比（ID/sha/schema 任一不符 fail-closed）；禁止
  path/filename/mtime/size 作绑定不变量。
* **预测 ↔ 快照 entry 双射（§22/§23）**：S-B 下每条预测经
  ``(person_id, observation_id)``（快照 entry 的稳定复合身份——等价于
  reference_snapshot_entry_id，photo 有多脸时 photo_id 单独不可靠）回溯；
  每条 entry 恰一条预测；禁止 orphan artifact。
* **NULL 预测（§25）**：``predicted_person_id=None ⇔ prediction_type=
  "no-candidate"（= S-B-2 已冻结的 accept/abstain 架构中的 abstain）⇔
  score/rank 同为 NULL``——与未来评估的弃权/Miss 语义兼容，不编码为
  "wrong person"。
* **确定性（§14/§15/§21）**：哈希域排除 artifact_id/created_at；固定键序
  + 预测序（person_id → observation_id → photo_id）+ LF；相同输入 → 相同
  content 哈希，artifact_id 可变。
* **不可变（§13）**：复用 S-B-4 的 ``SnapshotStore``（原子 + 拒绝覆盖 +
  .part）——Snapshot 与 Artifact 是不同 domain object 但共享同一不可变
  文件层；**S-B-4 NB-1 限制同样存在**（os.replace 后 post-verify 失败
  可能占用目标路径）——如实登记，不擅自改 unlink policy（§31）。
* **业务隔离（§26）**：零业务写入——Artifact 是 evaluation/experiment
  artifact，不写 Assignment/PFE/Archive/recognition_results。

本服务**不实现** scorer/threshold/margin policy/evaluation。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from photo_archiver.application.ports import SnapshotStore
from photo_archiver.application.services.reference_snapshot_service import (
    ReferenceSnapshotService,
    SnapshotDocument,
)
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.value_objects import FaceEmbedding  # noqa: F401

ARTIFACT_SCHEMA_VERSION = "prediction-artifact-v1"

PREDICTION_SOURCE_SB = "S-B"
PREDICTION_SOURCE_SA = "S-A"
PREDICTION_SOURCE_SC = "S-C"
PREDICTION_SOURCES = (PREDICTION_SOURCE_SB, PREDICTION_SOURCE_SA, PREDICTION_SOURCE_SC)

PREDICTION_TYPE_PREDICTED = "predicted"
PREDICTION_TYPE_NO_CANDIDATE = "no-candidate"

# §18：已批准的 S-B score architecture 元数据（描述性记录，非新授权）
SB_SCORE_SEMANTICS = {
    "method": "sb-member-max-cosine-v1",
    "domain": "[-1, 1]",
    "unit": "raw-cosine",
    "direction": "higher-is-better",
}


@dataclass(frozen=True, slots=True)
class PredictionRecord:
    """One GIVEN prediction outcome（builder 冻结它，不计算它）."""

    person_id: UUID
    observation_id: UUID
    photo_id: UUID
    predicted_person_id: UUID | None
    score: float | None
    rank: int | None
    margin: float | None = None
    prediction_id: UUID = field(default_factory=uuid4)

    @property
    def prediction_type(self) -> str:
        """§25：predicted_person_id IS NULL ⇔ no-candidate（= abstain）。"""
        return (PREDICTION_TYPE_PREDICTED if self.predicted_person_id is not None
                else PREDICTION_TYPE_NO_CANDIDATE)

    def to_content_dict(self, method: str, method_version: str) -> dict:
        """Fixed key order（canonical 序列化序，禁止字典遍历序依赖）."""
        return {
            "prediction_id": str(self.prediction_id),
            "prediction_type": self.prediction_type,
            "person_id": str(self.person_id),
            "observation_id": str(self.observation_id),
            "photo_id": str(self.photo_id),
            "predicted_person_id": (str(self.predicted_person_id)
                                    if self.predicted_person_id is not None else None),
            "score": self.score,
            "rank": self.rank,
            "margin": self.margin,
            "prediction_method": method,
            "prediction_method_version": method_version,
        }



@dataclass(frozen=True, slots=True)
class PredictionArtifactResult:
    """Builder outcome."""

    artifact_id: UUID
    artifact_path: Path
    artifact_sha256: str
    prediction_source: str
    entry_count: int
    person_count: int
    prediction_count: int


@dataclass(frozen=True, slots=True)
class PredictionArtifactVerification:
    """Verifier outcome（逐项 evidence）."""

    file_exists: bool
    schema_version_valid: bool
    hash_matches: bool
    binding_consistent: bool
    snapshot_verified: bool | None = None
    snapshot_id_matches: bool | None = None
    snapshot_sha_matches: bool | None = None
    scope_matches: bool | None = None
    entry_bijection: bool | None = None
    prediction_references_valid: bool | None = None

    @property
    def ok(self) -> bool:
        return all(
            v is True or v is None
            for v in (
                self.file_exists, self.schema_version_valid, self.hash_matches,
                self.binding_consistent, self.snapshot_verified,
                self.snapshot_id_matches, self.snapshot_sha_matches,
                self.scope_matches, self.entry_bijection,
                self.prediction_references_valid,
            )
        )


class PredictionArtifactService:
    """Build + verify immutable Prediction Artifact files（零业务写入）."""

    def __init__(
        self,
        snapshot_service: ReferenceSnapshotService,
        artifact_store: SnapshotStore,
    ) -> None:
        """Store read-only dependencies；Artifact 与 Snapshot 共享不可变文件层."""
        self._snapshots = snapshot_service
        self._store = artifact_store

    def build_artifact(
        self,
        prediction_source: str,
        prediction_method: str,
        prediction_method_version: str,
        predictions: list[PredictionRecord],
        reference_snapshot_path: Path | None = None,
        reference_snapshot_id: UUID | str | None = None,
        reference_snapshot_sha256: str | None = None,
        dataset_id: UUID | str | None = None,
        dataset_version: str | None = None,
        input_population_scope: str | None = None,
        entry_count: int | None = None,
        person_count: int | None = None,
        git_commit: str | None = None,
        destination: Path | None = None,
    ) -> PredictionArtifactResult:
        """Freeze GIVEN prediction outputs + snapshot binding into an artifact.

        §30 fail-closed：任何验证失败 → NO ARTIFACT PUBLISHED（旧 artifact
        不变，半成品不发布）。
        """
        if prediction_source not in PREDICTION_SOURCES:
            raise ValidationError(f"unknown prediction source: {prediction_source!r}")
        if not predictions:
            raise ValidationError(
                "no predictions given — S-B Prediction Artifact is NOT "
                "CREATABLE without snapshot-backed scoring output (§12); "
                "no fake empty prediction rows"
            )
        if destination is None:
            raise ValidationError("artifact destination path is required")

        snapshot: SnapshotDocument | None = None
        snapshot_id: UUID | None = None
        snapshot_sha: str | None = None
        scope: str | None = input_population_scope
        if prediction_source == PREDICTION_SOURCE_SB:
            # §7/§8：S-B 绑定 REQUIRED；ID + SHA256 双 fail-closed
            if reference_snapshot_path is None:
                raise ValidationError(
                    "S-B artifact requires a reference snapshot (§8) — "
                    "binding invariant missing"
                )
            if reference_snapshot_id is None or reference_snapshot_sha256 is None:
                raise ValidationError(
                    "S-B artifact requires reference_snapshot_id AND "
                    "reference_snapshot_sha256 (§9) — identity and content "
                    "integrity are both mandatory"
                )
            snapshot = self._snapshots.read_document(
                Path(reference_snapshot_path)
            )
            # Snapshot 内部完整性（篡改/损坏 → fail-closed，§28）
            verification = self._snapshots.verify_snapshot(
                Path(reference_snapshot_path))
            if not verification.ok:
                raise ValidationError(
                    f"reference snapshot failed verification: {verification}"
                )
            if snapshot.snapshot_id != UUID(str(reference_snapshot_id)):
                raise ValidationError(
                    "reference snapshot ID mismatch: artifact expects "
                    f"{reference_snapshot_id}, snapshot is {snapshot.snapshot_id}"
                )
            recomputed_sha = self._recompute_snapshot_sha(snapshot)
            if recomputed_sha != reference_snapshot_sha256:
                raise ValidationError(
                    "reference snapshot SHA256 mismatch: artifact expects "
                    f"{reference_snapshot_sha256}, snapshot content hashes to "
                    f"{recomputed_sha}"
                )
            snapshot_id = snapshot.snapshot_id
            snapshot_sha = snapshot.snapshot_sha256
            scope = snapshot.content["population_scope"]
            dataset_id = snapshot.content["dataset_id"]
            dataset_version = snapshot.content["dataset_version"]
            entry_count = int(snapshot.content["entry_count"])
            person_count = int(snapshot.content["person_count"])
            self._validate_sb_predictions(predictions, snapshot)
        else:
            # §7：S-A / S-C 不得携带 arbitrary snapshot id/hash
            if reference_snapshot_path is not None or reference_snapshot_id is not None \
                    or reference_snapshot_sha256 is not None:
                raise ValidationError(
                    f"{prediction_source} artifact must have NULL reference "
                    "snapshot binding (§7 architecture isolation)"
                )
            if entry_count is None or person_count is None:
                raise ValidationError(
                    f"{prediction_source} artifact requires caller-provided "
                    "entry_count and person_count"
                )
        if dataset_id is None or dataset_version is None:
            raise ValidationError("artifact requires dataset_id and dataset_version")
        if scope is None:
            raise ValidationError(
                "artifact requires input_population_scope (§10 — frozen record)"
            )

        method_version = prediction_method_version
        entries = [p.to_content_dict(prediction_method, method_version)
                   for p in predictions]
        entries = sorted(
            entries,
            key=lambda e: (e["person_id"], e["observation_id"], e["photo_id"]),
        )
        content = {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "prediction_source": prediction_source,
            "prediction_method": prediction_method,
            "prediction_method_version": method_version,
            "reference_snapshot_id": (str(snapshot_id) if snapshot_id is not None
                                      else None),
            "reference_snapshot_sha256": snapshot_sha,
            "input_population_scope": scope,
            "dataset_id": str(dataset_id) if not isinstance(dataset_id, str) else dataset_id,
            "dataset_version": dataset_version,
            "entry_count": entry_count,
            "person_count": person_count,
            "git_commit": git_commit,
            "score_semantics": (dict(SB_SCORE_SEMANTICS)
                                if prediction_method == SB_SCORE_SEMANTICS["method"]
                                else None),
            "threshold": None,
            "predictions": entries,
        }
        content_bytes = _canonical_json(content)
        artifact_sha = hashlib.sha256(content_bytes).hexdigest()
        artifact_id = uuid4()
        document = {
            "artifact_id": str(artifact_id),
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "artifact_sha256": artifact_sha,
            "content": content,
        }
        destination_path = Path(destination)
        self._store.write_atomic(destination_path, _canonical_json(document))

        post_verification: PredictionArtifactVerification = self.verify_artifact(
            destination_path,
            reference_snapshot_path=(reference_snapshot_path
                                     if prediction_source == PREDICTION_SOURCE_SB
                                     else None),
        )
        if not post_verification.ok:
            raise ValidationError(
                f"post-publish verification failed: {post_verification}"
            )
        return PredictionArtifactResult(
            artifact_id=artifact_id,
            artifact_path=Path(destination),
            artifact_sha256=artifact_sha,
            prediction_source=prediction_source,
            entry_count=entry_count,
            person_count=person_count,
            prediction_count=len(predictions),
        )

    def verify_artifact(
        self,
        artifact_path: Path,
        reference_snapshot_path: Path | None = None,
    ) -> PredictionArtifactVerification:
        """Read-only verification（§28）：hash/绑定一致性/快照交叉；Artifact ↔
        Snapshot 优先（§29）——不检查 current PFE（漂移属 source-state 观察）.
        """
        path = Path(artifact_path)
        if not self._store.path_exists(path):
            return PredictionArtifactVerification(
                file_exists=False, schema_version_valid=False, hash_matches=False,
                binding_consistent=False,
            )
        try:
            document = json.loads(self._store.read_bytes(path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return PredictionArtifactVerification(
                file_exists=True, schema_version_valid=False, hash_matches=False,
                binding_consistent=False,
            )
        schema_ok = document.get("schema_version") == ARTIFACT_SCHEMA_VERSION
        content = document.get("content") or {}
        recomputed = hashlib.sha256(_canonical_json(content)).hexdigest()
        hash_ok = document.get("artifact_sha256") == recomputed

        source = content.get("prediction_source")
        snap_id = content.get("reference_snapshot_id")
        snap_sha = content.get("reference_snapshot_sha256")
        if source == PREDICTION_SOURCE_SB:
            binding_ok = snap_id is not None and snap_sha is not None
        else:
            binding_ok = snap_id is None and snap_sha is None

        snapshot_ok = sid_matches = sha_matches = scope_matches = None
        bijection = references_ok = None
        predictions = content.get("predictions") or []
        if source == PREDICTION_SOURCE_SB and reference_snapshot_path is not None:
            try:
                snapshot = self._snapshots.read_document(reference_snapshot_path)
                inner = self._snapshots.verify_snapshot(reference_snapshot_path)
                snapshot_ok = inner.ok
                sid_matches = (str(snapshot.snapshot_id) == snap_id)
                sha_matches = (self._recompute_snapshot_sha(snapshot) == snap_sha)
                scope_matches = (
                    snapshot.content["population_scope"]
                    == content.get("input_population_scope")
                )
                snapshot_keys = {
                    (e["person_id"], e["observation_id"])
                    for e in snapshot.content["entries"]
                }
                prediction_keys = [
                    (e["person_id"], e["observation_id"]) for e in predictions
                ]
                bijection = (
                    len(prediction_keys) == len(set(prediction_keys))
                    and set(prediction_keys) == snapshot_keys
                    and content.get("entry_count") == len(snapshot.content["entries"])
                    and content.get("person_count") == snapshot.content["person_count"]
                )
                references_ok = all(
                    e.get("prediction_id") is not None
                    and e.get("prediction_method") is not None
                    and e.get("prediction_method_version") is not None
                    for e in predictions
                )
            except ValidationError:
                snapshot_ok = False
                sid_matches = False
                sha_matches = False
        return PredictionArtifactVerification(
            file_exists=True,
            schema_version_valid=schema_ok,
            hash_matches=hash_ok,
            binding_consistent=binding_ok,
            snapshot_verified=snapshot_ok,
            snapshot_id_matches=sid_matches,
            snapshot_sha_matches=sha_matches,
            scope_matches=scope_matches,
            entry_bijection=bijection,
            prediction_references_valid=references_ok,
        )

    def _validate_sb_predictions(
        self, predictions: list[PredictionRecord], snapshot: SnapshotDocument
    ) -> None:
        """§22/§23/§24：S-B 预测必须与快照 entry 双射且引用完整。"""
        snapshot_keys = {
            (UUID(e["person_id"]), UUID(e["observation_id"])): e
            for e in self._snapshot_entries(snapshot)
        }
        seen: set[tuple[UUID, UUID]] = set()
        for prediction in predictions:
            key = (prediction.person_id, prediction.observation_id)
            if key not in snapshot_keys:
                raise ValidationError(
                    f"prediction {prediction.prediction_id} references "
                    f"(person={key[0]}, observation={key[1]}) — not a snapshot "
                    "entry (orphan prediction)"
                )
            if key in seen:
                raise ValidationError(
                    f"prediction {prediction.prediction_id} duplicates the "
                    "snapshot entry prediction (each entry predicts once)"
                )
            seen.add(key)
            entry = snapshot_keys[key]
            if str(prediction.photo_id) != entry["photo_id"]:
                raise ValidationError(
                    f"prediction {prediction.prediction_id} photo_id does not "
                    "match its snapshot entry"
                )
            # §25：no-candidate ⇔ predicted_person_id/score/rank 全 NULL
            if prediction.predicted_person_id is None:
                if prediction.score is not None or prediction.rank is not None:
                    raise ValidationError(
                        f"prediction {prediction.prediction_id}: no-candidate "
                        "must carry NULL score/rank (§25)"
                    )
        if len(seen) != len(snapshot_keys):
            missing = len(snapshot_keys) - len(seen)
            raise ValidationError(
                f"{missing} snapshot entries have no prediction — S-B artifact "
                "requires entry-level bijection (§22)"
            )

    def _snapshot_entries(self, snapshot: SnapshotDocument) -> list[dict]:
        return snapshot.content["entries"]

    def _recompute_snapshot_sha(self, snapshot: SnapshotDocument) -> str:
        from photo_archiver.application.services.reference_snapshot_service import (
            canonical_json as _snapshot_canonical,
        )

        return hashlib.sha256(_snapshot_canonical(snapshot.content)).hexdigest()


def _canonical_json(obj) -> bytes:
    """Deterministic canonical JSON：UTF-8、紧凑分隔、固定键序（调用方构造）、LF."""
    return (
        json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
        + "\n"
    ).encode("utf-8")
