"""Per-run residual record deletion（批次删除功能 C，追加轮 21）.

名单侧（A）与照片侧（B）删完之后，识别运行记录本身（``recognition_runs``
行＋残留聚类代际＋残留观测/快照）没有删除口——运行在「特征数据」下拉里
永远残留（与 2026-11-01 修复的导入批次残留死锁同构）。本服务补上第三级：
**运行记录清理**。

硬阻断（与 D5 一致）：
- 照片仍在登记 → 必须先走照片入口（那里有归档/样本/GT 的披露级联）；
- 残留代际的簇上有 GT 裁定 → 裁定证据不可自动删除（校准侧无删除口，
  放行会制造不可恢复的证据损失）。

与 A/B 同范式：预览 → 级联披露 → 显式知悉（视图层）→ 单事务执行 →
如实回执；磁盘文件一律不动（D3）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from photo_archiver.application.commands.deletion import DeleteRunRecordCommand
from photo_archiver.application.dtos.deletion import (
    RunRecordDeletionPreview,
    RunRecordDeletionResult,
)
from photo_archiver.domain.exceptions import ValidationError

if TYPE_CHECKING:
    from uuid import UUID

    from photo_archiver.application.ports import UnitOfWork

    from photo_archiver.domain.repositories.calibration_annotation_repository import (
        CalibrationAnnotationRepository,
    )
    from photo_archiver.domain.repositories.cluster_assignment_repository import (
        ClusterPersonAssignmentRepository,
    )
    from photo_archiver.domain.repositories.face_cluster_repository import (
        FaceClusterRepository,
    )
    from photo_archiver.domain.repositories.face_observation_repository import (
        FaceObservationRepository,
    )
    from photo_archiver.domain.repositories.recognition_run_repository import (
        RecognitionRunRepository,
    )


class DeleteRunRecordService:
    """Delete one recognition run's residual record and the run row itself."""

    def __init__(
        self,
        run_repository: "RecognitionRunRepository",
        observation_repository: "FaceObservationRepository",
        cluster_repository: "FaceClusterRepository",
        assignment_repository: "ClusterPersonAssignmentRepository",
        calibration_repository: "CalibrationAnnotationRepository",
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize the service with its ports.

        Args:
            run_repository: 运行行与输入快照（残留读取、运行行删除）。
            observation_repository: 残留观测读取与扫尾删除。
            cluster_repository: 残留代际/簇读取与代际级联删除。
            assignment_repository: 残留决策行计数（随代际级联）。
            calibration_repository: GT 裁定读取（硬阻断判定）。
            unit_of_work: 事务边界；``None`` 时裸跑（测试路径）。
        """
        self._runs = run_repository
        self._observations = observation_repository
        self._clusters = cluster_repository
        self._assignments = assignment_repository
        self._calibration = calibration_repository
        self._unit_of_work = unit_of_work

    # ── 范围解析 ──────────────────────────────────────────────────────

    def _scope(self, run_id: UUID) -> dict:
        """解析该运行的残留代际、决策、观测与快照（执行时点重算）。"""
        run = self._runs.get_run(run_id)
        snapshots = self._runs.list_run_photos(run_id)
        photo_ids = tuple(dict.fromkeys(s.photo_id for s in snapshots))
        observations = self._observations.list_by_run(run_id)
        generations = self._clusters.list_cluster_runs(run_id)
        clusters = []
        decisions = []
        for generation in generations:
            if generation.id is None:  # pragma: no cover - 实体保证 id 存在
                continue
            clusters.extend(self._clusters.list_clusters(generation.id))
            decisions.extend(self._assignments.list_by_cluster_run(generation.id))
        ground_truth_count = 0
        if clusters:
            wanted = {c.id for c in clusters if c.id is not None}
            ground_truth_count = sum(
                1 for truth in self._calibration.list_ground_truth()
                if truth.cluster_id in wanted
            )
        return {
            "run": run,
            "photo_count": len(photo_ids),
            "observation_count": len(observations),
            "snapshot_count": len(snapshots),
            "generations": generations,
            "clusters": clusters,
            "decisions": decisions,
            "ground_truth_count": ground_truth_count,
        }

    # ── 预览 ──────────────────────────────────────────────────────────

    def preview(self, run_id: UUID) -> RunRecordDeletionPreview:
        """返回该运行残留记录及其级联计数的预览（无副作用）。"""
        scope = self._scope(run_id)
        run = scope["run"]

        blocked: list[str] = []
        if scope["photo_count"]:
            blocked.append(
                f"该运行仍有 {scope['photo_count']} 张照片登记——请先使用"
                "「删除该运行照片…」清理照片及其级联数据",
            )
        if scope["ground_truth_count"]:
            blocked.append(
                f"该运行簇上有 {scope['ground_truth_count']} 条 GT 裁定——"
                "记录删除会级联带走裁定行，证据不可恢复",
            )

        return RunRecordDeletionPreview(
            run_found=run is not None,
            run_created_at=getattr(run, "created_at", None),
            run_status=str(getattr(run, "status", "") or ""),
            photo_count=scope["photo_count"],
            generation_count=len(scope["generations"]),
            cluster_count=len(scope["clusters"]),
            decision_count=len(scope["decisions"]),
            ground_truth_count=scope["ground_truth_count"],
            observation_count=scope["observation_count"],
            snapshot_count=scope["snapshot_count"],
            blocked_reasons=tuple(blocked),
        )

    # ── 执行 ──────────────────────────────────────────────────────────

    def execute(self, command: DeleteRunRecordCommand) -> RunRecordDeletionResult:
        """在单事务内删除该运行的残留记录与运行行。"""
        def _run() -> RunRecordDeletionResult:
            scope = self._scope(command.run_id)
            if scope["run"] is None:
                raise ValidationError("识别运行不存在——无法删除运行记录。")
            preview = self.preview(command.run_id)
            if preview.is_blocked:
                raise ValidationError("；".join(preview.blocked_reasons))

            purged = 0
            for generation in scope["generations"]:
                purged += self._clusters.remove_cluster_run(generation.id)
            observation_cascade = self._observations.remove_by_run(command.run_id)
            snapshot_cascade = self._runs.remove_run_photos_snapshot(command.run_id)
            run_removed = self._runs.remove_run(command.run_id)
            return RunRecordDeletionResult(
                run_removed=run_removed,
                generations_purged=purged,
                decision_cascade=preview.decision_count,
                observation_cascade=observation_cascade,
                snapshot_cascade=snapshot_cascade,
            )

        if self._unit_of_work is not None:
            with self._unit_of_work:
                result = _run()
        else:
            result = _run()
        logger.info(
            "AUDIT delete-run-record actor=local-user run={} run_removed={} "
            "generations_purged={} decision_cascade={} observation_cascade={} "
            "snapshot_cascade={}",
            command.run_id, result.run_removed, result.generations_purged,
            result.decision_cascade, result.observation_cascade,
            result.snapshot_cascade,
        )
        return result
