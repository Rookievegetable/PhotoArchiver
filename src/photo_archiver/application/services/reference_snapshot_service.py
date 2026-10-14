"""S-B-4 Reference Snapshot builder + verifier（文件层强制，零迁移）.

将 S-B-3 Eligibility 判定的合法 Reference Sample 冻结为可审计、不可变、
可验证的 Snapshot 文件（D-SB-5/6/7）。

结构（单文件 UTF-8 JSON 文档）::

    {
      "snapshot_id": <uuid>,              # 身份 UUID，不入哈希域
      "schema_version": "reference-snapshot-v1",
      "created_at": <iso>,                # 不入哈希域
      "snapshot_sha256": <hex>,           # = sha256(canonical_json(content))
      "content": {                        # 哈希域：确定性规范化序列化
        "schema_version", "dataset_id", "dataset_version",
        "population_scope", "source_eligibility_version",
        "entry_count", "person_count",
        "entries": [ ... 确定性排序 + 逐字段定序 ... ]
      }
    }

关键语义：

* **确定性（§22）**：哈希域**排除** snapshot_id / created_at 等易变字段——
  相同冻结输入（同 eligible 样本、同 embedding、同 provenance、同 schema
  version）必须产生逐字节相同的 canonical bytes 与相同 snapshot_sha256；
  snapshot_id 每次构建可变。
* **逐样本 provenance（§3/§4，闭合 S-B-3 OWNER-GATE）**：每条 entry 保存
  assignment_ids / recognition_run_id / cluster_run_ids / eligibility
  decision ——可审计证据，而非 "source=reference" 裸标签（P-02）。
* **输入只来自 S-B-3（§6）**：builder 复用 ``ReferenceEligibilityService``
  的评估结果，不重新判断身份；population scope 显式参数并写入 metadata
  （§7/§19）：``eligible``（仅 ELIGIBLE）或 ``eligible-and-coverage-only``；
  Reference Snapshot Population ≠ Frozen Evaluation Population。
* **隔离（§20）**：候选构建 → 守卫复验（photo_id + 字节哈希，S-B-2 规则）
  → 写入 → 写后验证 → 哈希；任何失败 = NO SNAPSHOT。
* **原子创建（§21）**：canonical bytes 全量内存构建 → ``.part`` +
  ``os.replace``（拒绝覆盖）；失败时旧 snapshot 不变、半成品不发布。
* **不可变（§15/§17/§18）**：无 update/delete/mutate API；enabled 取
  snapshot 时刻状态；quality_score 只保存不判定（D-SB-10）。

本服务**不实现** Prediction Artifact / scoring / threshold / evaluation。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from photo_archiver.application.ports import SnapshotStore
from photo_archiver.application.services.reference_eligibility_service import (
    DECISION_COVERAGE_ONLY,
    DECISION_ELIGIBLE,
    ELIGIBILITY_MODEL_VERSION,
    ReferenceEligibilityService,
)
from photo_archiver.application.services.reference_intake_service import (
    ReferenceIntakeService,
    _as_uuid,
)
from photo_archiver.domain import PhotoRepository
from photo_archiver.domain.repositories.face_observation_repository import (
    FaceObservationRepository,
)
from photo_archiver.domain.exceptions import (
    ValidationError,
)

SNAPSHOT_SCHEMA_VERSION = "reference-snapshot-v1"
SCOPE_ELIGIBLE = "eligible"
SCOPE_ELIGIBLE_AND_COVERAGE_ONLY = "eligible-and-coverage-only"
_SCOPE_DECISIONS = {
    SCOPE_ELIGIBLE: (DECISION_ELIGIBLE,),
    SCOPE_ELIGIBLE_AND_COVERAGE_ONLY: (DECISION_ELIGIBLE, DECISION_COVERAGE_ONLY),
}

_HEX_DIGEST_LENGTH = 64


def canonical_json(obj) -> bytes:
    """Deterministic canonical JSON: UTF-8, compact separators, LF-terminated.

    键序由调用方以固定顺序构造 dict 保证（不依赖 sort_keys 的字典遍历语义
    之外的东西）；数字用 CPython repr（IEEE754 最短往返，跨平台稳定）。
    """
    return (
        json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
        + "\n"
    ).encode("utf-8")


def canonical_embedding_bytes(vector: tuple[float, ...]) -> bytes:
    """Canonical embedding representation for ``embedding_sha256``（§10/§11）."""
    return json.dumps([float(v) for v in vector], separators=(",", ":")).encode("utf-8")


def embedding_sha256(vector: tuple[float, ...]) -> str:
    """SHA-256 over the canonical embedding bytes."""
    return hashlib.sha256(canonical_embedding_bytes(vector)).hexdigest()


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    """One frozen reference sample（固定字段序 = canonical 序列化序）."""

    person_id: UUID
    observation_id: UUID
    photo_id: UUID
    embedding_sha256: str
    enabled: bool
    quality_score: float | None
    recognition_run_id: UUID
    cluster_run_ids: tuple[UUID, ...]
    assignment_ids: tuple[UUID, ...]
    eligibility_decision: str

    def to_content_dict(self) -> dict:
        """Fixed key order（canonical 序列化序，禁止字典遍历序依赖）."""
        return {
            "person_id": str(self.person_id),
            "observation_id": str(self.observation_id),
            "photo_id": str(self.photo_id),
            "embedding_sha256": self.embedding_sha256,
            "enabled": bool(self.enabled),
            "quality_score": self.quality_score,
            "provenance": {
                "recognition_run_id": str(self.recognition_run_id),
                "cluster_run_ids": [str(r) for r in self.cluster_run_ids],
                "assignment_ids": [str(a) for a in self.assignment_ids],
                "eligibility_decision": self.eligibility_decision,
            },
        }


@dataclass(frozen=True, slots=True)
class SnapshotDocument:
    """A parsed snapshot file（不可变视图）."""

    snapshot_id: UUID
    schema_version: str
    created_at: str
    snapshot_sha256: str
    content: dict

    @property
    def entries(self) -> list[dict]:
        return self.content["entries"]

    @property
    def population_scope(self) -> str:
        return self.content["population_scope"]


@dataclass(frozen=True, slots=True)
class SnapshotCreationResult:
    """Builder outcome（含发布路径与内容哈希）."""

    snapshot_id: UUID
    snapshot_path: Path
    snapshot_sha256: str
    entry_count: int
    person_count: int
    population_scope: str
    excluded_decision_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SnapshotVerificationResult:
    """Verifier outcome（逐项 evidence）."""

    file_exists: bool
    schema_version_valid: bool
    hash_matches: bool
    entry_count_matches: bool
    person_count_matches: bool
    entry_identity_unique: bool
    provenance_complete: bool
    embedding_hashes_wellformed: bool
    embedding_drift_free: bool | None = None
    isolation_valid: bool | None = None

    @property
    def ok(self) -> bool:
        return all(
            v is True or v is None
            for v in (
                self.file_exists, self.schema_version_valid, self.hash_matches,
                self.entry_count_matches, self.person_count_matches,
                self.entry_identity_unique, self.provenance_complete,
                self.embedding_hashes_wellformed, self.embedding_drift_free,
                self.isolation_valid,
            )
        )


class ReferenceSnapshotService:
    """Build + verify immutable Reference Snapshot files（零业务写入）."""

    def __init__(
        self,
        eligibility_service: ReferenceEligibilityService,
        reference_intake: ReferenceIntakeService,
        snapshot_store: SnapshotStore,
        observation_repository: FaceObservationRepository,
        photo_repository: PhotoRepository,
    ) -> None:
        """Store read-only dependencies; S-B-3 evaluation is reused, not recopied.

        ``observation_repository`` / ``photo_repository`` 支撑
        ``cross_check_current_state=True`` 的现状交叉验证（embedding 漂移 +
        photo_id 隔离），全部只读。
        """
        self._eligibility = eligibility_service
        self._intake = reference_intake
        self._store = snapshot_store
        self._observations = observation_repository
        self._photos = photo_repository

    def build_snapshot(
        self,
        dataset_id: UUID | str,
        dataset_version: str,
        reference_run_ids: frozenset[UUID] | set[UUID],
        reference_cluster_run_ids: frozenset[UUID] | set[UUID],
        population_scope: str = SCOPE_ELIGIBLE,
        destination: Path | None = None,
    ) -> SnapshotCreationResult:
        """Freeze S-B-3-eligible samples into an immutable snapshot file.

        Steps（§20/§21）: eligibility reuse → scope filter → per-entry
        provenance + embedding hash → isolation re-verification（S-B-2 守卫）
        → canonical bytes + hash → atomic publish → post-verify. 任何失败 =
        NO SNAPSHOT（旧 snapshot 不变，半成品不发布）。
        """
        if population_scope not in _SCOPE_DECISIONS:
            raise ValidationError(f"unknown population scope: {population_scope!r}")
        dataset_uuid = _as_uuid(dataset_id)
        run_ids = frozenset(_as_uuid(r) for r in reference_run_ids)
        cluster_run_ids = frozenset(_as_uuid(r) for r in reference_cluster_run_ids)

        samples, unreadable = self._eligibility.evaluate_samples(
            dataset_uuid, dataset_version, run_ids, cluster_run_ids
        )
        if unreadable:
            raise ValidationError(
                "unreadable (corrupt) sample rows exist — provenance/evidence "
                f"incomplete for persons {sorted(str(u) for u in unreadable)}; "
                "DO NOT SNAPSHOT (P-03)"
            )
        allowed = _SCOPE_DECISIONS[population_scope]
        candidates = [s for s in samples if s.decision in allowed]
        excluded_counts = dict(
            Counter(s.decision for s in samples if s.decision not in allowed)
        )
        if not candidates:
            raise ValidationError(
                f"no eligible snapshot candidates under scope {population_scope!r}"
            )
        entries: list[SnapshotEntry] = []
        for sample in candidates:
            if sample.photo_id is None or sample.recognition_run_id is None:
                raise ValidationError(
                    f"candidate {sample.pfe_id} has incomplete identity "
                    "provenance — DO NOT SNAPSHOT (P-03)"
                )
            if not sample.assignment_ids:
                raise ValidationError(
                    f"candidate {sample.pfe_id} has no assignment provenance — "
                    "DO NOT SNAPSHOT (P-02/P-03)"
                )
            entries.append(
                SnapshotEntry(
                    person_id=sample.person_id,
                    observation_id=sample.observation_id,
                    photo_id=sample.photo_id,
                    embedding_sha256=embedding_sha256(
                        self._embedding_vector(sample)
                    ),
                    enabled=True,
                    quality_score=self._embedding_quality(sample),
                    recognition_run_id=sample.recognition_run_id,
                    cluster_run_ids=tuple(sorted(sample.cluster_run_ids, key=str)),
                    assignment_ids=tuple(sorted(sample.assignment_ids, key=str)),
                    eligibility_decision=sample.decision,
                )
            )

        # §20 isolation re-verification（S-B-2 守卫；任何失败 = NO SNAPSHOT）
        candidate_photo_ids = frozenset(entry.photo_id for entry in entries)
        self._intake.verify_reference_photos(
            candidate_photo_ids, dataset_uuid, dataset_version
        )

        ordered = sorted(
            entries,
            key=lambda e: (str(e.person_id), str(e.photo_id), str(e.observation_id)),
        )
        entry_count = len(ordered)
        person_count = len({e.person_id for e in ordered})
        content = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "dataset_id": str(dataset_uuid),
            "dataset_version": dataset_version,
            "population_scope": population_scope,
            "source_eligibility_version": ELIGIBILITY_MODEL_VERSION,
            "entry_count": entry_count,
            "person_count": person_count,
            "entries": [entry.to_content_dict() for entry in ordered],
        }
        content_bytes = canonical_json(content)
        snapshot_sha = hashlib.sha256(content_bytes).hexdigest()
        snapshot_id = uuid4()
        document = {
            "snapshot_id": str(snapshot_id),
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "snapshot_sha256": snapshot_sha,
            "content": content,
        }
        if destination is None:
            raise ValidationError("snapshot destination path is required")
        destination = Path(destination)
        self._store.write_atomic(destination, canonical_json(document))

        verification = self.verify_snapshot(destination)
        if not verification.ok:
            raise ValidationError(
                f"post-publish verification failed: {verification}"
            )
        return SnapshotCreationResult(
            snapshot_id=snapshot_id,
            snapshot_path=destination,
            snapshot_sha256=snapshot_sha,
            entry_count=entry_count,
            person_count=person_count,
            population_scope=population_scope,
            excluded_decision_counts=excluded_counts,
        )

    def read_document(self, snapshot_path: Path) -> SnapshotDocument:
        """Read-only snapshot document reader（S-B-5 binding 复用）.

        Raises:
            ValidationError: file missing, unparseable, or schema version
                incompatible with ``reference-snapshot-v1``.
        """
        path = Path(snapshot_path)
        if not self._store.path_exists(path):
            raise ValidationError(f"snapshot file missing: {path}")
        try:
            document = json.loads(self._store.read_bytes(path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValidationError(f"snapshot file unparseable: {exc}") from None
        if document.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
            raise ValidationError(
                f"unsupported snapshot schema version: "
                f"{document.get('schema_version')!r}"
            )
        return SnapshotDocument(
            snapshot_id=UUID(document["snapshot_id"]),
            schema_version=document["schema_version"],
            created_at=document["created_at"],
            snapshot_sha256=document["snapshot_sha256"],
            content=document["content"],
        )

    def verify_snapshot(
        self,
        snapshot_path: Path,
        cross_check_current_state: bool = False,
    ) -> SnapshotVerificationResult:
        """Read-only verification（§23）：hash/counts/身份唯一/provenance 完整；
        ``cross_check_current_state=True`` 时加验 embedding 漂移与隔离现状
        （需要仓储上下文，经 S-B-2 守卫复用）。Verifier 不修改 Snapshot。
        """
        path = Path(snapshot_path)
        if not self._store.path_exists(path):
            return SnapshotVerificationResult(
                file_exists=False, schema_version_valid=False, hash_matches=False,
                entry_count_matches=False, person_count_matches=False,
                entry_identity_unique=False, provenance_complete=False,
                embedding_hashes_wellformed=False,
            )
        raw = self._store.read_bytes(path)
        try:
            document = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return SnapshotVerificationResult(
                file_exists=True, schema_version_valid=False, hash_matches=False,
                entry_count_matches=False, person_count_matches=False,
                entry_identity_unique=False, provenance_complete=False,
                embedding_hashes_wellformed=False,
            )
        schema_ok = document.get("schema_version") == SNAPSHOT_SCHEMA_VERSION
        content = document.get("content") or {}
        recomputed = hashlib.sha256(canonical_json(content)).hexdigest()
        hash_ok = document.get("snapshot_sha256") == recomputed
        entries = content.get("entries") or []
        entry_count_ok = content.get("entry_count") == len(entries)
        person_count_ok = content.get("person_count") == len({
            e.get("person_id") for e in entries
        })
        identities = [(e.get("person_id"), e.get("observation_id")) for e in entries]
        identity_unique = len(identities) == len(set(identities))
        provenance_complete = all(
            (e.get("provenance") or {}).get("assignment_ids")
            for e in entries
        )
        hex_ok = all(
            isinstance(e.get("embedding_sha256"), str)
            and len(e["embedding_sha256"]) == _HEX_DIGEST_LENGTH
            and all(c in "0123456789abcdef" for c in e["embedding_sha256"])
            for e in entries
        )
        drift_free = None
        isolation_valid = None
        if cross_check_current_state:
            drift_free = self._embedding_drift_free(entries)
            isolation_valid = self._isolation_valid(entries, content)
        return SnapshotVerificationResult(
            file_exists=True,
            schema_version_valid=schema_ok,
            hash_matches=hash_ok,
            entry_count_matches=entry_count_ok,
            person_count_matches=person_count_ok,
            entry_identity_unique=identity_unique,
            provenance_complete=provenance_complete,
            embedding_hashes_wellformed=hex_ok,
            embedding_drift_free=drift_free,
            isolation_valid=isolation_valid,
        )

    def _embedding_vector(self, sample):
        """The S-B-3 evidence's embedding（来自合法 PFE；P-02 证据内容）."""
        vector = sample.embedding
        if not vector:
            raise ValidationError(
                f"candidate {sample.pfe_id} carries no embedding — "
                "DO NOT SNAPSHOT (P-03)"
            )
        return vector

    def _embedding_quality(self, sample):
        return sample.quality_score

    def _embedding_drift_free(self, entries) -> bool:
        """Snapshot embedding hashes vs CURRENT observation embeddings
        （漂移检测：embedding 必须仍与 snapshot 时刻内容一致）."""
        for entry in entries:
            observation = self._find_observation(
                UUID(entry["observation_id"]),
                UUID(entry["photo_id"]),
            )
            if observation is None:
                return False
            current = embedding_sha256(observation.embedding.vector)
            if current != entry["embedding_sha256"]:
                return False
        return True

    def _find_observation(self, observation_id: UUID, photo_id: UUID):
        for observation in self._observations.list_by_photo(photo_id):
            if observation.id == observation_id:
                return observation
        return None

    def _isolation_valid(self, entries, content) -> bool:
        """Entry photos must still sit outside EvalPhotoSet（photo_id 主不变量）."""
        evaluation_photos = self._intake.build_evaluation_photo_set(
            UUID(content["dataset_id"]), content["dataset_version"]
        )
        return all(
            UUID(entry["photo_id"]) not in evaluation_photos
            for entry in entries
        )
