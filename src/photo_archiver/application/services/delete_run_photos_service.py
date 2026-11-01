"""按识别运行删除照片及记录（批次删除功能 B · D1/D4/D5/D6/D7）.

"批次"锚点 = **识别运行**（``recognition_runs``）——照片只挂在运行下。
照片范围 = 该运行的输入快照（``recognition_run_photos``）。

删除照片登记会按外键逐级级联：识别记录、归档记录、观测、簇成员、忽略标记、
多样本库，以及**其它运行引用同一批照片的快照行**（不可重建——重跑会产生新的
运行与 id）。磁盘原件一律不动（D3）。

三条配套处置：

- **D7 计数修正**：成员关系被级联抹掉后 ``face_clusters.member_count`` 会失真，
  删除后按实际成员数回写**受影响的代际**（只修本次操作弄坏的，不清扫历史欠账）。
- **D6 空簇残留**：簇已空但仍挂着 confirmed/auto_confirmed 决策时，名册的
  "匹配状态"会撒谎——把有效行迁为 ``unassigned``（**改状态而非删行**，守住
  "决策行只增改不删"不变量）。
- **D4 B2 可选**：同时删除该运行的聚类代际——级联带走该代际的身份决策行，
  必须在确认前披露。

**硬阻断（D5）**：归档记录 / GT 裁定 / 样本库任一非空即拒绝执行——这些是删掉
后无法靠重新识别还原的证据。
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING
from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.deletion import DeleteRunPhotosCommand
from photo_archiver.application.dtos.deletion import (
    RunPhotosDeletionPreview,
    RunPhotosDeletionResult,
)
from photo_archiver.application.ports import UnitOfWork
from photo_archiver.application.use_cases.deletion import DeleteRunPhotosUseCase
from photo_archiver.domain.entities.cluster_assignment import ACTIVE_ASSIGNMENT_STATUSES
from photo_archiver.domain.exceptions import ValidationError

if TYPE_CHECKING:
    from photo_archiver.domain.entities.face_cluster import FaceCluster
    from photo_archiver.domain.repositories import (
        ArchiveRecordRepository,
        ClusterPersonAssignmentRepository,
        FaceClusterRepository,
        FaceObservationRepository,
        PersonFaceSampleRepository,
        PhotoRepository,
        RecognitionRepository,
        RecognitionRunRepository,
    )
    from photo_archiver.domain.repositories.calibration_annotation_repository import (
        CalibrationAnnotationRepository,
    )


class DeleteRunPhotosService(DeleteRunPhotosUseCase):
    """Delete one recognition run's photo registrations and their cascaded rows."""

    def __init__(
        self,
        run_repository: "RecognitionRunRepository",
        photo_repository: "PhotoRepository",
        recognition_repository: "RecognitionRepository",
        archive_record_repository: "ArchiveRecordRepository",
        observation_repository: "FaceObservationRepository",
        sample_repository: "PersonFaceSampleRepository",
        cluster_repository: "FaceClusterRepository",
        assignment_repository: "ClusterPersonAssignmentRepository",
        calibration_repository: "CalibrationAnnotationRepository",
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize the service with its ports.

        Args:
            run_repository: 识别运行与输入快照读取（照片范围、跨运行重叠计数）。
            photo_repository: 照片登记删除写口。
            recognition_repository: 识别记录读取（级联计数）。
            archive_record_repository: 归档记录读取（级联计数与硬阻断）。
            observation_repository: 观测读取（级联计数与样本范围）。
            sample_repository: 多样本库读取（级联计数与硬阻断）。
            cluster_repository: 簇/代际/成员读取与计数修正写口。
            assignment_repository: 身份决策读取与空簇状态迁移写口。
            calibration_repository: GT 裁定读取（硬阻断判定与披露）。
            unit_of_work: 事务边界；``None`` 时裸跑（测试路径）。
        """
        self._runs = run_repository
        self._photos = photo_repository
        self._recognition = recognition_repository
        self._archive_records = archive_record_repository
        self._observations = observation_repository
        self._samples = sample_repository
        self._clusters = cluster_repository
        self._assignments = assignment_repository
        self._calibration = calibration_repository
        self._unit_of_work = unit_of_work

    # ── 范围解析 ──────────────────────────────────────────────────────

    def _scope(self, run_id: UUID) -> dict:
        """解析该运行的快照照片、观测、成员与簇（执行时点重算）。"""
        run = self._runs.get_run(run_id)
        snapshots = self._runs.list_run_photos(run_id)
        photo_ids = tuple(dict.fromkeys(snapshot.photo_id for snapshot in snapshots))

        observation_ids: set[UUID] = set()
        for photo_id in photo_ids:
            for observation in self._observations.list_by_photo(photo_id):
                observation_ids.add(observation.id)

        generations = self._clusters.list_cluster_runs(run_id)
        clusters: list[FaceCluster] = []
        decisions = []
        for generation in generations:
            if generation.id is None:  # pragma: no cover - 实体保证 id 存在
                continue
            clusters.extend(self._clusters.list_clusters(generation.id))
            decisions.extend(self._assignments.list_by_cluster_run(generation.id))

        # 受影响代际必须在**删除前**判定——删除后成员行已被级联清空，
        # 再扫就找不到谁被影响了。
        members_at_risk = 0
        affected_generation_ids: list[UUID] = []
        for generation in self._clusters.list_all_cluster_runs():
            if generation.id is None:  # pragma: no cover - 实体保证 id 存在
                continue
            generation_at_risk = 0
            for member in self._clusters.list_members(generation.id):
                if member.observation_id in observation_ids:
                    generation_at_risk += 1
            members_at_risk += generation_at_risk
            if generation_at_risk:
                affected_generation_ids.append(generation.id)

        return {
            "run": run,
            "photo_ids": photo_ids,
            "observation_ids": observation_ids,
            "generations": generations,
            "clusters": clusters,
            "decisions": decisions,
            "members_at_risk": members_at_risk,
            "affected_generation_ids": affected_generation_ids,
        }

    def _ground_truth_count(self, clusters: list) -> int:
        """该运行簇上的 GT 裁定行数（B1 保留但簇已空；B2 随簇级联删除）。"""
        if not clusters:
            return 0
        wanted = {cluster.id for cluster in clusters if cluster.id is not None}
        return sum(
            1 for truth in self._calibration.list_ground_truth()
            if truth.cluster_id in wanted
        )

    # ── 预览 ──────────────────────────────────────────────────────────

    def preview(self, run_id: UUID) -> RunPhotosDeletionPreview:
        """返回该运行照片及其级联计数的预览（无副作用）。"""
        scope = self._scope(run_id)
        photo_ids: tuple[UUID, ...] = scope["photo_ids"]
        observation_ids: set[UUID] = scope["observation_ids"]
        clusters = scope["clusters"]

        recognition_count = (
            len(self._recognition.list_by_photo_ids(photo_ids)) if photo_ids else 0
        )
        archive_count = (
            len(self._archive_records.list_by_photo_ids(photo_ids)) if photo_ids else 0
        )
        sample_count = (
            len(self._samples.list_by_observation_ids(tuple(observation_ids)))
            if observation_ids else 0
        )
        other_run_snapshot_count = (
            self._runs.count_other_run_snapshots(photo_ids, run_id)
            if photo_ids else 0
        )
        ground_truth_count = self._ground_truth_count(clusters)

        blocked: list[str] = []
        if archive_count:
            blocked.append(
                f"该批照片已有 {archive_count} 条归档记录——删除照片登记会让归档"
                "索引行一并消失（归档目录里的实体文件仍在）",
            )
        if ground_truth_count:
            blocked.append(
                f"该批照片的簇上有 {ground_truth_count} 条 GT 裁定——删除照片会让"
                "裁定失去照片支撑（若同时清理聚类代际，裁定行还会被级联删除）",
            )
        if sample_count:
            blocked.append(
                f"该批照片的多样本库有 {sample_count} 行——观测随照片级联删除后，"
                "样本不可恢复",
            )

        run = scope["run"]
        return RunPhotosDeletionPreview(
            run_found=run is not None,
            run_created_at=getattr(run, "created_at", None),
            run_status=str(getattr(run, "status", "") or ""),
            photo_count=len(photo_ids),
            recognition_count=recognition_count,
            archive_count=archive_count,
            observation_count=len(observation_ids),
            sample_count=sample_count,
            member_count=scope["members_at_risk"],
            other_run_snapshot_count=other_run_snapshot_count,
            cluster_count=len(clusters),
            decision_count=len(scope["decisions"]),
            ground_truth_count=ground_truth_count,
            blocked_reasons=tuple(blocked),
        )

    # ── 执行 ──────────────────────────────────────────────────────────

    def execute(self, command: DeleteRunPhotosCommand) -> RunPhotosDeletionResult:
        """在单事务内删除该运行的照片登记并完成配套处置。"""
        def _run() -> RunPhotosDeletionResult:
            scope = self._scope(command.run_id)
            run = scope["run"]
            if run is None:
                raise ValidationError("识别运行不存在——无法按批次删除照片。")
            preview = self.preview(command.run_id)
            if preview.is_blocked:
                raise ValidationError("；".join(preview.blocked_reasons))

            photo_ids: tuple[UUID, ...] = scope["photo_ids"]
            existing = tuple(
                photo_id for photo_id in photo_ids
                if self._photos.find_by_id(photo_id) is not None
            )
            removed = self._photos.remove(existing) if existing else 0

            recounted = 0
            unassigned = 0
            purged = 0
            # 追加轮 22：记录清理隐含代际清理——代际引用运行行，运行行删除前
            # 代际必须已消失（照片仍在时已硬阻断，此处不涉归档/样本/GT）。
            if command.purge_cluster_generations or command.delete_run_record:
                # B2：代际与其决策行即将整体删除——计数回写与空簇迁移都是
                # 无效功，跳过（结果里如实报 0）。
                purged = self._purge_generations(scope)
            else:
                recounted = self._recount_affected_generations(scope)
                unassigned = self._unassign_empty_clusters(scope)

            # 批次删除功能 C（追加轮 22 并入）：运行记录清理终口——残留观测
            # /快照兜底扫尾 + 运行行本身（正常路径观测/快照已随照片级联清空，
            # 扫尾计数如实报 0）。
            run_removed = 0
            if command.delete_run_record:
                self._observations.remove_by_run(command.run_id)
                self._runs.remove_run_photos_snapshot(command.run_id)
                run_removed = self._runs.remove_run(command.run_id)

            return RunPhotosDeletionResult(
                requested=preview.photo_count,
                removed=removed,
                missing=preview.photo_count - removed,
                recognition_cascade=preview.recognition_count,
                archive_cascade=preview.archive_count,
                observation_cascade=preview.observation_count,
                sample_cascade=preview.sample_count,
                member_cascade=preview.member_count,
                other_run_snapshot_cascade=preview.other_run_snapshot_count,
                unassigned_decisions=unassigned,
                clusters_recounted=recounted,
                generations_purged=purged,
                ground_truth_orphaned=preview.ground_truth_count,
                run_removed=run_removed,
            )

        if self._unit_of_work is not None:
            with self._unit_of_work:
                result = _run()
        else:
            result = _run()
        logger.info(
            "AUDIT delete-run-photos actor=local-user run={} removed={} "
            "recognition_cascade={} archive_cascade={} observation_cascade={} "
            "sample_cascade={} member_cascade={} other_run_snapshot_cascade={} "
            "unassigned_decisions={} clusters_recounted={} generations_purged={} "
            "run_removed={}",
            command.run_id, result.removed, result.recognition_cascade,
            result.archive_cascade, result.observation_cascade,
            result.sample_cascade, result.member_cascade,
            result.other_run_snapshot_cascade, result.unassigned_decisions,
            result.clusters_recounted, result.generations_purged,
            result.run_removed,
        )
        return result

    def _recount_affected_generations(self, scope: dict) -> int:
        """按实际成员数回写受影响代际的簇/代际计数（D7）。

        受影响代际在删除前已判定（``scope["affected_generation_ids"]``）——
        删除后成员行已消失，无法再从成员表反推谁受影响。
        """
        affected: list[UUID] = scope["affected_generation_ids"]
        if not affected:
            return 0
        recounted = 0
        for generation_id in affected:
            members = self._clusters.list_members(generation_id)
            counts = Counter(member.cluster_id for member in members)
            for cluster in self._clusters.list_clusters(generation_id):
                if cluster.id is None:  # pragma: no cover - 实体保证 id 存在
                    continue
                self._clusters.update_cluster_member_count(
                    cluster.id, counts.get(cluster.id, 0),
                )
            self._clusters.update_cluster_run_member_count(
                generation_id, len(members),
            )
            recounted += 1
        return recounted

    def _unassign_empty_clusters(self, scope: dict) -> int:
        """空簇的有效决策迁为 unassigned（D6：状态迁移，不删决策行）。"""
        unassigned = 0
        for generation_id in scope["affected_generation_ids"]:
            members = self._clusters.list_members(generation_id)
            counts = Counter(member.cluster_id for member in members)
            for cluster in self._clusters.list_clusters(generation_id):
                if cluster.id is None:  # pragma: no cover - 实体保证 id 存在
                    continue
                if counts.get(cluster.id, 0):
                    continue
                latest = self._assignments.list_latest_decision(cluster.id)
                if latest is None or latest.status not in ACTIVE_ASSIGNMENT_STATUSES:
                    continue
                latest.unassign()
                if self._assignments.update_assignment(latest) == 1:
                    unassigned += 1
        return unassigned

    def _purge_generations(self, scope: dict) -> int:
        """删除该运行的聚类代际（D4 B2：簇/成员/决策行随之级联删除）。"""
        purged = 0
        for generation in scope["generations"]:
            purged += self._clusters.remove_cluster_run(generation.id)
        return purged
