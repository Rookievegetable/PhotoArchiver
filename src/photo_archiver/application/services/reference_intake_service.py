"""S-B Reference Photo Intake isolation guard（S-B-2 补强版）.

Owner 裁决 D-SB-1…D-SB-12（``docs/decisions/S4B2-sb-reference-design-decisions.md``）
下的 S-B 参考数据链隔离守卫与受守卫保护的确认入口。核心语义：

* 隔离不变量**只能是 photo_id**——同一物理脸跨 recognition run 会复制出
  不同的 observation_id（S-B 设计评审实证：2 runs × 1441 obs 覆盖同 472
  照片），observation_id / 文件路径 / 文件名 / folder_id 都不可作判据。
* **二级守卫**：photo_id 之外，对参考照片实算 SHA-256 并与
  EvalPhotoContentHashSet 比对，拦截"同字节、新路径、新 photo_id"的评估
  照片副本（D-SB-8；content hash 是辅助证据，不替代 photo_id 主守卫）。
* ``EvalPhotoSet`` **动态重建**：Frozen GT → cluster → member → observation
  → photo_id；不硬编码任何数量，数据集版本打错时 fail-closed。
* **分层保护**（D-SB 设计冻结）：普通业务确认在评估照片上沉淀业务样本
  是**合法**的（业务样本 ≠ Evaluation Reference）；本服务只保护
  **Reference 写入链**——:meth:`ReferenceIntakeService.confirm_reference_cluster`
  把守卫内建为不可遗漏的一环（先对**全部**簇做守卫，再委托既有业务确认
  路径写 Assignment + PFE），调用方无法"忘记先 verify"。
  Reference Snapshot（S-B-4）与 Evaluation Start 复验（S-B-4）是后续两道
  独立防线。

写入语义：守卫全程只读；守卫失败发生在任何写入之前（零部分写入）。
委托 :class:`~photo_archiver.application.services.pairing_workbench_service.\
PairingWorkbenchService` 后，沿用其既有事务语义（人工确认经
``assign_person``，manual 来源、D-1 语义、Assignment SSOT 不变）。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from photo_archiver.application.commands.pairing import AssignClusterPersonCommand
from photo_archiver.application.ports import PhotoContentHasher
from photo_archiver.application.services.pairing_workbench_service import (
    PairingOperationResult,
    PairingWorkbenchService,
)
from photo_archiver.domain import PhotoRepository
from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR
from photo_archiver.domain.entities.face_cluster import FaceCluster
from photo_archiver.domain.exceptions import (
    ReferenceIsolationViolationError,
    ValidationError,
)
from photo_archiver.domain.repositories.calibration_annotation_repository import (
    CalibrationAnnotationRepository,
)
from photo_archiver.domain.repositories.face_cluster_repository import (
    FaceClusterRepository,
)
from photo_archiver.domain.repositories.face_observation_repository import (
    FaceObservationRepository,
)


def _as_uuid(value: UUID | str) -> UUID:
    """Normalize str/UUID inputs (S-B-2 driver lesson: string ids compared
    against entity UUIDs silently mismatch — coerce at every entry point;
    unparseable input fails closed as ValueError)."""
    return value if isinstance(value, UUID) else UUID(str(value))


@dataclass(frozen=True, slots=True)
class ReferenceIsolationReport:
    """Successful isolation verification summary（只报计数，不外泄 id 清单）."""

    evaluation_photo_count: int
    reference_photo_count: int


class ReferenceIntakeService:
    """Fail-closed isolation guard + guarded reference confirmation path."""

    def __init__(
        self,
        calibration_repository: CalibrationAnnotationRepository,
        cluster_repository: FaceClusterRepository,
        observation_repository: FaceObservationRepository,
        photo_repository: PhotoRepository,
        content_hasher: PhotoContentHasher,
        pairing_workbench: PairingWorkbenchService,
    ) -> None:
        """Store the read-only repositories plus the guarded delegate."""
        self._calibration = calibration_repository
        self._clusters = cluster_repository
        self._observations = observation_repository
        self._photos = photo_repository
        self._hasher = content_hasher
        self._workbench = pairing_workbench

    def build_evaluation_photo_set(
        self, dataset_id: UUID, dataset_version: str
    ) -> frozenset[UUID]:
        """Dynamically rebuild EvalPhotoSet for one frozen dataset version."""
        photos, _ = self._evaluation_membership(dataset_id, dataset_version)
        return photos

    def evaluation_content_hashes(
        self, dataset_id: UUID, dataset_version: str
    ) -> frozenset[str]:
        """Rebuild EvalPhotoContentHashSet (S-B-3 eligibility reuses this —
        E-05: isolation rules are inherited from the guard, never reinvented).
        Stored ``metadata_content_hash`` is the fast path; photos without a
        stored hash are hashed live (never allow-on-missing)."""
        evaluation_photos, _ = self._evaluation_membership(
            _as_uuid(dataset_id), dataset_version
        )
        return self.evaluation_content_hashes_via_photos(evaluation_photos)

    def evaluation_member_observations(
        self, dataset_id: UUID, dataset_version: str
    ) -> frozenset[UUID]:
        """Rebuild the evaluation cluster member observation set (S-B-3 reuse
        of the S-B-2 same-cluster rule)."""
        _, evaluation_observations = self._evaluation_membership(
            _as_uuid(dataset_id), dataset_version
        )
        return evaluation_observations

    def evaluation_content_hashes_via_photos(
        self, evaluation_photos: frozenset[UUID]
    ) -> frozenset[str]:
        """Content-hash set for a prebuilt EvalPhotoSet (no re-derivation)."""
        hashes: set[str] = set()
        for photo_id in evaluation_photos:
            photo = self._photos.find_by_id(photo_id)
            if photo is None:
                raise ValidationError(f"evaluation photo {photo_id} does not exist")
            stored = (
                photo.metadata.content_hash if photo.metadata is not None else None
            )
            if stored is not None:
                hashes.add(stored)
            else:
                hashes.add(self._hasher.calculate(photo.path.raw_path))
        return frozenset(hashes)

    def verify_reference_photos(
        self,
        reference_photo_ids: frozenset[UUID] | set[UUID],
        dataset_id: UUID,
        dataset_version: str,
    ) -> ReferenceIsolationReport:
        """Phase C hard guard: ``ReferencePhotoSet ∩ EvalPhotoSet = ∅`` + bytes.

        Raises:
            ValidationError: empty reference set, or the frozen dataset
                cannot be resolved (wrong id/version, dangling clusters).
            ReferenceIsolationViolationError: any reference photo_id is a
                frozen evaluation photo, or any reference file is a
                byte-identical copy of an evaluation photo — the intake
                must stop before any recognition/clustering/sample work.
        """
        evaluation_photos, _ = self._evaluation_membership(
            _as_uuid(dataset_id), dataset_version
        )
        reference = frozenset(reference_photo_ids)
        if not reference:
            raise ValidationError("reference photo set is empty")
        violations = reference & evaluation_photos
        if violations:
            raise ReferenceIsolationViolationError(
                "reference photos intersect the frozen evaluation photo set "
                f"({len(violations)} photo_id): {sorted(str(v) for v in violations)}"
            )
        self._verify_content_hashes(reference, evaluation_photos)
        return ReferenceIsolationReport(
            evaluation_photo_count=len(evaluation_photos),
            reference_photo_count=len(reference),
        )

    def verify_reference_cluster_samples(
        self,
        cluster_run_id: UUID,
        cluster_ids: frozenset[UUID] | set[UUID],
        dataset_id: UUID,
        dataset_version: str,
    ) -> None:
        """Pre-deposit guard（§17/§18）: every member observation is clean.

        For each cluster about to be confirmed, every member observation
        must (a) exist, (b) not belong to any evaluation cluster, (c) live
        on a photo outside EvalPhotoSet, and (d) its photo must not be a
        byte-identical copy of any evaluation photo. Check (c)/(d) subsume
        cross-run same-photo leakage: the same physical face under a
        different recognition run still resolves to the same photo bytes.

        Raises:
            ValidationError: empty cluster set, unknown cluster, cluster
                from another cluster run, unknown photo, or dangling member
                observation.
            ReferenceIsolationViolationError: same-cluster, photo-level or
                byte-level leakage — the confirmation (and its sample
                deposit) must not run at all.
        """
        evaluation_photos, evaluation_observations = self._evaluation_membership(
            _as_uuid(dataset_id), dataset_version
        )
        cluster_run_id = _as_uuid(cluster_run_id)
        wanted = frozenset(cluster_ids)
        if not wanted:
            raise ValidationError("reference cluster set is empty")
        clusters: dict[UUID, FaceCluster] = {}
        for cluster_id in wanted:
            cluster = self._clusters.get_cluster(cluster_id)
            if cluster is None:
                raise ValidationError(f"cluster {cluster_id} does not exist")
            if cluster.cluster_run_id != cluster_run_id:
                raise ValidationError(
                    f"cluster {cluster_id} does not belong to cluster run {cluster_run_id}"
                )
            clusters[cluster_id] = cluster
        photos_by_observation = self._photos_by_run(
            {cluster.run_id for cluster in clusters.values()}
        )
        member_observations: list[UUID] = []
        for member_run_id in {cluster.cluster_run_id for cluster in clusters.values()}:
            for member in self._clusters.list_members(member_run_id):
                if member.cluster_id in wanted:
                    member_observations.append(member.observation_id)
        member_photos: list[UUID] = []
        for observation_id in member_observations:
            if observation_id not in photos_by_observation:
                raise ValidationError(
                    f"cluster member references unknown observation {observation_id}"
                )
            if observation_id in evaluation_observations:
                raise ReferenceIsolationViolationError(
                    "reference sample source observation "
                    f"{observation_id} belongs to an evaluation cluster"
                )
            photo_id = photos_by_observation[observation_id]
            if photo_id in evaluation_photos:
                raise ReferenceIsolationViolationError(
                    f"reference sample source observation {observation_id} "
                    f"lives on evaluation photo {photo_id}"
                )
            member_photos.append(photo_id)
        self._verify_content_hashes(frozenset(member_photos), evaluation_photos)

    def confirm_reference_cluster(
        self,
        cluster_run_id: UUID,
        cluster_ids: frozenset[UUID] | set[UUID],
        person_id: UUID,
        dataset_id: UUID,
        dataset_version: str,
    ) -> list[PairingOperationResult]:
        """Guarded reference confirmation: guard is part of the write chain.

        S-B-2 的结构性补强：Reference 语义的确认**必须**走本入口——守卫
        （photo_id + same-cluster + 悬挂 + 字节级哈希）在**任何写入之前**对
        **全部**簇一次性执行；违例即抛错、零部分写入。守卫通过后按序委托
        既有业务确认 ``PairingWorkbenchService.assign_person``（manual 来源，
        D-1 语义；person 由工作台先行校验，未知 person 在写入前失败）。

        普通业务确认不经过本入口（业务样本 ≠ Evaluation Reference）：在评估
        照片上做业务确认沉淀业务样本是合法行为，由 S-B-4 Snapshot 资格检查
        与 Evaluation Start 复验兜底。

        Returns:
            每个 cluster 的 :class:`PairingOperationResult` 列表（委托顺序
            与输入集合的排序一致）。

        Raises:
            ValidationError / ReferenceIsolationViolationError: 守卫或 person
                校验失败——此时尚未发生任何写入。
        """
        self.verify_reference_cluster_samples(
            cluster_run_id, cluster_ids, dataset_id, dataset_version
        )
        results: list[PairingOperationResult] = []
        for cluster_id in sorted(cluster_ids, key=str):
            results.append(
                self._workbench.assign_person(
                    AssignClusterPersonCommand(
                        cluster_id=cluster_id, person_id=person_id
                    ),
                    actor=HUMAN_ACTOR,
                )
            )
        return results

    def _evaluation_membership(
        self, dataset_id: UUID, dataset_version: str
    ) -> tuple[frozenset[UUID], frozenset[UUID]]:
        """Rebuild (EvalPhotoSet, EvalObservationSet) from the frozen GT."""
        ground_truth = self._calibration.list_ground_truth(
            dataset_id=dataset_id, dataset_version=dataset_version
        )
        cluster_ids = {row.cluster_id for row in ground_truth}
        if not cluster_ids:
            raise ValidationError(
                f"no ground truth rows for dataset {dataset_id} "
                f"version {dataset_version!r}"
            )
        clusters: dict[UUID, FaceCluster] = {}
        for cluster_id in cluster_ids:
            cluster = self._clusters.get_cluster(cluster_id)
            if cluster is None:
                raise ValidationError(
                    f"ground truth cluster {cluster_id} does not exist"
                )
            clusters[cluster_id] = cluster
        photos_by_observation = self._photos_by_run(
            {cluster.run_id for cluster in clusters.values()}
        )
        member_observations: set[UUID] = set()
        for member_run_id in {cluster.cluster_run_id for cluster in clusters.values()}:
            for member in self._clusters.list_members(member_run_id):
                if member.cluster_id in clusters:
                    member_observations.add(member.observation_id)
        dangling = member_observations - photos_by_observation.keys()
        if dangling:
            raise ValidationError(
                "evaluation cluster members reference unknown observations: "
                f"{sorted(str(v) for v in dangling)}"
            )
        evaluation_photos = frozenset(
            photos_by_observation[observation_id]
            for observation_id in member_observations
        )
        return evaluation_photos, frozenset(member_observations)

    def _verify_content_hashes(
        self, photo_ids: frozenset[UUID], evaluation_photos: frozenset[UUID]
    ) -> None:
        """D-SB-8 secondary guard: raw-byte SHA-256 vs evaluation photo bytes.

        EvalPhotoContentHashSet 优先取存储的 ``metadata_content_hash``（历史
        照片已 backfill），缺失时对该照片实算。参考照片一律实算——扫描注册
        不计算内容哈希（审计实证 metadata_content_hash 为 NULL），存储值只
        作评估侧加速，不作为参考侧判据。
        """
        eval_hashes = self.evaluation_content_hashes_via_photos(evaluation_photos)
        for photo_id in photo_ids:
            photo = self._photos.find_by_id(photo_id)
            if photo is None:
                raise ValidationError(f"reference photo {photo_id} does not exist")
            digest = self._hasher.calculate(photo.path.raw_path)
            if digest in eval_hashes:
                raise ReferenceIsolationViolationError(
                    f"reference photo {photo_id} is a byte-identical copy "
                    f"of an evaluation photo (sha256 {digest[:16]}…)"
                )

    def _photos_by_run(self, run_ids: set[UUID]) -> dict[UUID, UUID]:
        """Map observation_id → photo_id across the given recognition runs."""
        photos_by_observation: dict[UUID, UUID] = {}
        for run_id in run_ids:
            for observation in self._observations.list_by_run(run_id):
                photos_by_observation[observation.id] = observation.photo_id
        return photos_by_observation
