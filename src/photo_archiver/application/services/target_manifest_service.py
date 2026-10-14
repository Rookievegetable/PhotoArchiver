"""S-B-6 Target Manifest（``target-manifest-v1``）builder + verifier.

依据 R3 §5.1：Frozen Dataset 唯一决定 Target Cluster Set；``cluster_run_id``
仅为世代锚；Run 额外 Cluster 不得导致失败（仅构建报告）；Manifest Cluster Set
与 Dataset Cluster Set **严格相等**；成员完整性五类校验 fail-closed；
``entry_count`` 与 ``source_member_count`` 分别计算、均入 canonical payload
与哈希域；Layer A 计数一致 ≠ 源成员完整（Layer B 重读源）。

零业务写入；发布复用不可变文件层（原子 + 拒绝覆盖）。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from photo_archiver.application.ports import SnapshotStore
from photo_archiver.application.services.reference_snapshot_service import (
    canonical_json,
)
from photo_archiver.application.services.sb6_contract import (
    TARGET_MANIFEST_CONTENT_KEYS,
    TARGET_MANIFEST_ENTRY_KEYS,
    TARGET_MANIFEST_SCHEMA_VERSION,
    _as_uuid,
)
from photo_archiver.domain import PhotoRepository
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.repositories.calibration_annotation_repository import (
    CalibrationAnnotationRepository,
)
from photo_archiver.domain.repositories.face_cluster_repository import (
    FaceClusterRepository,
)
from photo_archiver.domain.repositories.face_observation_repository import (
    FaceObservationRepository,
)
from photo_archiver.domain.entities.face_cluster import FaceCluster


@dataclass(frozen=True, slots=True)
class TargetManifestEntry:
    """One frozen target member（身份三元组 + 目标照片）."""

    cluster_id: UUID
    observation_id: UUID
    photo_id: UUID

    def to_content_dict(self) -> dict:
        return {
            "cluster_id": str(self.cluster_id),
            "observation_id": str(self.observation_id),
            "photo_id": str(self.photo_id),
        }


@dataclass(frozen=True, slots=True)
class TargetManifestDocument:
    """A parsed manifest file（不可变视图）."""

    manifest_id: UUID
    schema_version: str
    created_at: str
    manifest_sha256: str
    content: dict


@dataclass(frozen=True, slots=True)
class ManifestCreationResult:
    """Builder outcome（含构建报告：Run 额外 Cluster 为信息项，不入 Manifest）."""

    manifest_id: UUID
    manifest_path: Path
    manifest_sha256: str
    cluster_count: int
    entry_count: int
    source_member_count: int
    run_extra_cluster_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ManifestVerification:
    """Verifier outcome：Layer A（离线内部）与 Layer B（源成员完整性）分离."""

    file_exists: bool
    schema_version_valid: bool
    hash_matches: bool
    counts_consistent: bool
    identity_unique: bool
    cluster_set_equal: bool
    keys_valid: bool
    layer_a: str  # pass / fail / not-run
    layer_b: str  # pass / fail / not-run / unprovable
    source_detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.file_exists and self.layer_a == "pass"


class TargetManifestService:
    """Build + verify immutable Target Manifest files（零业务写入）."""

    def __init__(
        self,
        calibration_repository: CalibrationAnnotationRepository,
        cluster_repository: FaceClusterRepository,
        observation_repository: FaceObservationRepository,
        photo_repository: PhotoRepository,
        manifest_store: SnapshotStore,
    ) -> None:
        self._calibration = calibration_repository
        self._clusters = cluster_repository
        self._observations = observation_repository
        self._photos = photo_repository
        self._store = manifest_store

    # ------------------------------------------------------------------ build

    def build_manifest(
        self,
        dataset_id: UUID | str,
        dataset_version: str,
        cluster_run_id: UUID | str,
        destination: Path,
    ) -> ManifestCreationResult:
        dataset_uuid = _as_uuid(dataset_id)
        run_uuid = _as_uuid(cluster_run_id)

        dataset_cluster_ids = self._dataset_cluster_ids(dataset_uuid, dataset_version)
        dataset_set = frozenset(dataset_cluster_ids)
        run_clusters = self._clusters.list_clusters(run_uuid)
        run_cluster_ids = {c.id for c in run_clusters if c.id is not None}
        missing = dataset_set - run_cluster_ids
        if missing:
            raise ValidationError(
                "ERR-SET-EQUALITY: dataset cluster(s) missing from cluster run "
                f"{run_uuid}: {sorted(str(v) for v in missing)}"
            )
        run_extra = tuple(sorted(run_cluster_ids - dataset_set, key=str))

        entries, source_member_count = self._read_source_members(
            run_uuid, dataset_set, run_clusters
        )
        cluster_count = len({e.cluster_id for e in entries})
        if cluster_count != len(dataset_cluster_ids):
            raise ValidationError(
                "ERR-SET-EQUALITY: manifest cluster set != dataset cluster set "
                f"({cluster_count} != {len(dataset_cluster_ids)})"
            )

        content = {
            "schema_version": TARGET_MANIFEST_SCHEMA_VERSION,
            "dataset_id": str(dataset_uuid),
            "dataset_version": dataset_version,
            "cluster_run_id": str(run_uuid),
            "dataset_cluster_ids": [str(c) for c in dataset_cluster_ids],
            "cluster_count": cluster_count,
            "entry_count": len(entries),
            "source_member_count": source_member_count,
            "entries": [e.to_content_dict() for e in entries],
        }
        content_bytes = canonical_json(content)
        manifest_sha = hashlib.sha256(content_bytes).hexdigest()
        manifest_id = uuid4()
        document = {
            "manifest_id": str(manifest_id),
            "schema_version": TARGET_MANIFEST_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "manifest_sha256": manifest_sha,
            "content": content,
        }
        self._store.write_atomic(Path(destination), canonical_json(document))
        verification = self.verify_manifest(Path(destination), source_check=False)
        if not verification.ok:
            raise ValidationError(f"post-publish verification failed: {verification}")
        return ManifestCreationResult(
            manifest_id=manifest_id,
            manifest_path=Path(destination),
            manifest_sha256=manifest_sha,
            cluster_count=cluster_count,
            entry_count=len(entries),
            source_member_count=source_member_count,
            run_extra_cluster_ids=run_extra,
        )

    def _dataset_cluster_ids(
        self, dataset_id: UUID, dataset_version: str
    ) -> list[UUID]:
        rows = self._calibration.list_ground_truth(
            dataset_id=dataset_id, dataset_version=dataset_version
        )
        cluster_ids = sorted({row.cluster_id for row in rows}, key=str)
        if not cluster_ids:
            raise ValidationError(
                "ERR-SET-EQUALITY: dataset has no ground truth clusters "
                f"({dataset_id} / {dataset_version!r})"
            )
        return cluster_ids

    def _read_source_members(
        self,
        run_uuid: UUID,
        dataset_set: frozenset[UUID],
        run_clusters: list[FaceCluster],
    ) -> tuple[list[TargetManifestEntry], int]:
        clusters_by_id = {c.id: c for c in run_clusters if c.id is not None}
        source_run_ids = {
            clusters_by_id[cid].run_id
            for cid in dataset_set
            if cid in clusters_by_id
        }
        photo_by_observation: dict[UUID, UUID] = {}
        for run_id in source_run_ids:
            for observation in self._observations.list_by_run(run_id):
                photo_by_observation[observation.id] = observation.photo_id

        member_rows = [
            m
            for m in self._clusters.list_members(run_uuid)
            if m.cluster_id in dataset_set
        ]
        source_member_count = len(member_rows)
        seen: set[tuple[UUID, UUID]] = set()
        entries: list[TargetManifestEntry] = []
        for member in member_rows:
            key = (member.cluster_id, member.observation_id)
            if key in seen:
                raise ValidationError(
                    f"ERR-MEMBER-CLASS: duplicate member identity {key}"
                )
            seen.add(key)
            photo_id = photo_by_observation.get(member.observation_id)
            if photo_id is None:
                raise ValidationError(
                    "ERR-MEMBER-CLASS: member observation "
                    f"{member.observation_id} is not resolvable in source runs"
                )
            entries.append(
                TargetManifestEntry(
                    cluster_id=member.cluster_id,
                    observation_id=member.observation_id,
                    photo_id=photo_id,
                )
            )
        entries.sort(key=lambda e: (str(e.cluster_id), str(e.observation_id)))
        return entries, source_member_count

    # ------------------------------------------------------------------- read

    def read_document(self, manifest_path: Path) -> TargetManifestDocument:
        path = Path(manifest_path)
        if not self._store.path_exists(path):
            raise ValidationError(f"manifest file missing: {path}")
        try:
            document = json.loads(self._store.read_bytes(path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValidationError(f"manifest file unparseable: {exc}") from None
        if document.get("schema_version") != TARGET_MANIFEST_SCHEMA_VERSION:
            raise ValidationError(
                "unsupported manifest schema version: "
                f"{document.get('schema_version')!r}"
            )
        return TargetManifestDocument(
            manifest_id=UUID(document["manifest_id"]),
            schema_version=document["schema_version"],
            created_at=document["created_at"],
            manifest_sha256=document["manifest_sha256"],
            content=document["content"],
        )

    @staticmethod
    def manifest_sha256(document: TargetManifestDocument) -> str:
        return hashlib.sha256(canonical_json(document.content)).hexdigest()

    # ----------------------------------------------------------------- verify

    def verify_manifest(
        self, manifest_path: Path, source_check: bool = False
    ) -> ManifestVerification:
        """Layer A 永远执行；``source_check=True`` 时加执行 Layer B（重读源）."""
        path = Path(manifest_path)
        if not self._store.path_exists(path):
            return ManifestVerification(
                file_exists=False,
                schema_version_valid=False,
                hash_matches=False,
                counts_consistent=False,
                identity_unique=False,
                cluster_set_equal=False,
                keys_valid=False,
                layer_a="not-run",
                layer_b="not-run",
            )
        try:
            document = json.loads(self._store.read_bytes(path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return ManifestVerification(
                file_exists=True,
                schema_version_valid=False,
                hash_matches=False,
                counts_consistent=False,
                identity_unique=False,
                cluster_set_equal=False,
                keys_valid=False,
                layer_a="fail",
                layer_b="not-run",
            )
        schema_ok = document.get("schema_version") == TARGET_MANIFEST_SCHEMA_VERSION
        content = document.get("content") or {}
        recomputed = hashlib.sha256(canonical_json(content)).hexdigest()
        hash_ok = document.get("manifest_sha256") == recomputed
        entries = content.get("entries") or []
        dataset_cluster_ids = content.get("dataset_cluster_ids") or []
        keys_ok = set(content.keys()) == set(TARGET_MANIFEST_CONTENT_KEYS) and all(
            isinstance(e, dict) and set(e.keys()) == set(TARGET_MANIFEST_ENTRY_KEYS)
            for e in entries
        )
        entry_clusters = [str(e.get("cluster_id")) for e in entries]
        counts_ok = (
            content.get("entry_count") == len(entries)
            and content.get("source_member_count") == len(entries)
            and content.get("cluster_count") == len(set(entry_clusters))
            and content.get("cluster_count") == len(dataset_cluster_ids)
        )
        identities = [
            (str(e.get("cluster_id")), str(e.get("observation_id"))) for e in entries
        ]
        identity_unique = len(identities) == len(set(identities))
        cluster_set_equal = set(entry_clusters) == set(str(c) for c in dataset_cluster_ids)

        layer_a_ok = (
            schema_ok and hash_ok and keys_ok and counts_ok and identity_unique
            and cluster_set_equal
        )
        layer_a = "pass" if layer_a_ok else "fail"
        layer_b, source_detail = (
            self._verify_source_membership(content) if source_check else ("not-run", None)
        )
        return ManifestVerification(
            file_exists=True,
            schema_version_valid=schema_ok,
            hash_matches=hash_ok,
            counts_consistent=counts_ok,
            identity_unique=identity_unique,
            cluster_set_equal=cluster_set_equal,
            keys_valid=keys_ok,
            layer_a=layer_a,
            layer_b=layer_b,
            source_detail=source_detail,
        )

    def _verify_source_membership(self, content: dict) -> tuple[str, str | None]:
        """Layer B：重读钉定 Run ∩ Dataset Cluster Set 的全部源成员，五类比对."""
        try:
            dataset_uuid = UUID(str(content["dataset_id"]))
            run_uuid = UUID(str(content["cluster_run_id"]))
            dataset_version = str(content["dataset_version"])
            dataset_cluster_ids = {UUID(str(c)) for c in content["dataset_cluster_ids"]}
            entries = content.get("entries") or []
        except (KeyError, ValueError, TypeError) as exc:
            return ("fail", f"ERR-SET-EQUALITY: manifest content unreadable ({exc})")
        try:
            gt_rows = self._calibration.list_ground_truth(
                dataset_id=dataset_uuid, dataset_version=dataset_version
            )
            run_clusters = self._clusters.list_clusters(run_uuid)
        except ValidationError as exc:
            return ("unprovable", f"ERR-UNPROVABLE: source unresolvable ({exc})")
        dataset_set = {row.cluster_id for row in gt_rows}
        if dataset_set != dataset_cluster_ids:
            return (
                "fail",
                "ERR-SET-EQUALITY: GT cluster set != manifest dataset_cluster_ids",
            )
        run_set = {c.id for c in run_clusters if c.id is not None}
        if not dataset_set <= run_set:
            return (
                "fail",
                "ERR-SET-EQUALITY: dataset cluster(s) missing from pinned run",
            )
        clusters_by_id = {c.id: c for c in run_clusters if c.id is not None}
        source_run_ids = {
            clusters_by_id[cid].run_id for cid in dataset_set if cid in clusters_by_id
        }
        photo_by_observation: dict[UUID, UUID] = {}
        try:
            for run_id in source_run_ids:
                for observation in self._observations.list_by_run(run_id):
                    photo_by_observation[observation.id] = observation.photo_id
        except ValidationError as exc:
            return ("unprovable", f"ERR-UNPROVABLE: observations unreadable ({exc})")
        member_rows = [
            m
            for m in self._clusters.list_members(run_uuid)
            if m.cluster_id in dataset_set
        ]
        source_pairs = Counter(
            (m.cluster_id, m.observation_id) for m in member_rows
        )
        manifest_pairs = Counter(
            (UUID(str(e["cluster_id"])), UUID(str(e["observation_id"]))) for e in entries
        )
        missing = source_pairs - manifest_pairs
        extra = manifest_pairs - source_pairs
        duplicated_source = [k for k, v in source_pairs.items() if v > 1]
        duplicated_manifest = [k for k, v in manifest_pairs.items() if v > 1]
        photo_mismatches = []
        for e in entries:
            key = (UUID(str(e["cluster_id"])), UUID(str(e["observation_id"])))
            source_photo = photo_by_observation.get(key[1])
            if source_photo is None or str(source_photo) != str(e.get("photo_id")):
                photo_mismatches.append(key)
        violations = (
            len(missing) + len(extra) + len(duplicated_source)
            + len(duplicated_manifest) + len(photo_mismatches)
        )
        if violations:
            return (
                "fail",
                "ERR-MEMBER-CLASS: missing=%d extra=%d dup_source=%d "
                "dup_manifest=%d photo_mismatch=%d"
                % (
                    len(missing),
                    len(extra),
                    len(duplicated_source),
                    len(duplicated_manifest),
                    len(photo_mismatches),
                ),
            )
        return ("pass", None)
