"""按识别运行删除名单及记录（批次删除功能 A · D1/D2/D5）.

"批次"锚点 = **识别运行**（``recognition_runs``）——名单导入批次
（``import_batches``）与运行之间没有任何关联字段，照片只挂在运行下。

该运行的"名单" = 其各聚类代际的身份决策行中出现过的**人员**（执行时点重算，
绝不信任预览快照）。两种语义（D2）：

- **A3**（默认）：删除人员实体 → 外键 CASCADE 清掉其**跨所有代际**的身份决策
  行、人脸嵌入与多样本库；识别记录 / 归档记录 / GT 裁定**行保留但失去人员
  指向**（SET NULL）。
- **A1**：只解除该运行的匹配关系，保留人员与其余记录——以**状态迁移**实现
  （有效行 → unassigned），不物理删除决策行，守住"决策行只增改不删"不变量。

**硬阻断（D5）**：归档记录 / GT 裁定 / 样本库任一非空即拒绝执行——这些是
删掉后无法靠重新识别还原的证据。A1 不删除任何证据，不受阻断。

磁盘文件一律不动（D3）；全部动作落 loguru 审计行；单事务（SQLite 不支持
嵌套事务——本服务自己持有唯一 UnitOfWork，人员删除与计数都在其内完成）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.deletion import (
    RUN_PEOPLE_MODE_DELETE,
    RUN_PEOPLE_MODE_UNASSIGN,
    DeleteRunPeopleCommand,
)
from photo_archiver.application.dtos.deletion import (
    RunPeopleDeletionPreview,
    RunPeopleDeletionResult,
)
from photo_archiver.application.ports import UnitOfWork
from photo_archiver.application.use_cases.deletion import DeleteRunPeopleUseCase
from photo_archiver.domain.entities.cluster_assignment import (
    ACTIVE_ASSIGNMENT_STATUSES,
    HUMAN_ACTOR,
)
from photo_archiver.domain.exceptions import ValidationError

if TYPE_CHECKING:
    from photo_archiver.application.services.delete_person_service import (
        DeletePersonService,
    )
    from photo_archiver.application.services.pairing_workbench_service import (
        PairingWorkbenchService,
    )
    from photo_archiver.domain.entities.face_cluster import FaceCluster
    from photo_archiver.domain.repositories import (
        ArchiveRecordRepository,
        ClusterPersonAssignmentRepository,
        FaceClusterRepository,
        PersonRepository,
        RecognitionRunRepository,
    )
    from photo_archiver.domain.repositories.calibration_annotation_repository import (
        CalibrationAnnotationRepository,
    )


class DeleteRunPeopleService(DeleteRunPeopleUseCase):
    """Delete (or unassign) the people one recognition run points at."""

    def __init__(
        self,
        run_repository: "RecognitionRunRepository",
        cluster_repository: "FaceClusterRepository",
        assignment_repository: "ClusterPersonAssignmentRepository",
        person_repository: "PersonRepository",
        delete_person: "DeletePersonService",
        archive_record_repository: "ArchiveRecordRepository",
        calibration_repository: "CalibrationAnnotationRepository",
        pairing_service: "PairingWorkbenchService | None" = None,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize the service with its ports.

        Args:
            run_repository: 识别运行读取（运行标签、代际范围）。
            cluster_repository: 聚类代际与簇读取（按运行解析范围）。
            assignment_repository: 身份决策读取（人员集合、当前有效行）。
            person_repository: 人员删除写口。
            delete_person: 既有人员删除服务——**只用于复用级联计数口径**
                （嵌入 / 识别归属 / 决策行 / 样本），不在此调用其 ``execute``
                （那会开第二个事务）。
            archive_record_repository: 归档记录读取（硬阻断判定与披露）。
            calibration_repository: GT 裁定读取（硬阻断判定与披露）。
            pairing_service: 解除匹配用（状态迁移 + 投影回收 + 样本停用）；
                ``None`` 时 A1 模式不可用（执行时报错，绝不静默降级）。
            unit_of_work: 事务边界；``None`` 时裸跑（测试路径）。
        """
        self._runs = run_repository
        self._clusters = cluster_repository
        self._assignments = assignment_repository
        self._people = person_repository
        self._delete_person = delete_person
        self._archive_records = archive_record_repository
        self._calibration = calibration_repository
        self._pairing = pairing_service
        self._unit_of_work = unit_of_work

    # ── 范围解析 ──────────────────────────────────────────────────────

    def _scope(
        self, run_id: UUID,
    ) -> tuple[object | None, list, list, list, tuple[UUID, ...]]:
        """解析该运行的代际、簇、决策行与人员集合（执行时点重算）。"""
        run = self._runs.get_run(run_id)
        generations = self._clusters.list_cluster_runs(run_id)
        clusters: list[FaceCluster] = []
        decisions = []
        for generation in generations:
            if generation.id is None:  # pragma: no cover - 实体保证 id 存在
                continue
            clusters.extend(self._clusters.list_clusters(generation.id))
            decisions.extend(self._assignments.list_by_cluster_run(generation.id))
        person_ids = tuple(
            dict.fromkeys(
                decision.person_id
                for decision in decisions
                if decision.person_id is not None
            )
        )
        return run, generations, clusters, decisions, person_ids

    def _archive_count(self, person_ids: tuple[UUID, ...]) -> int:
        """该批人员名下的归档记录数（删除后这些行失去人员指向）。"""
        if not person_ids:
            return 0
        wanted = set(person_ids)
        return sum(
            1 for record in self._archive_records.list_all()
            if record.person_id in wanted
        )

    def _ground_truth_count(self, person_ids: tuple[UUID, ...]) -> int:
        """该批人员被引用的 GT 裁定行数（删除后这些行失去人员指向）。"""
        if not person_ids:
            return 0
        wanted = set(person_ids)
        return sum(
            1 for truth in self._calibration.list_ground_truth()
            if truth.person_id in wanted
        )

    # ── 预览 ──────────────────────────────────────────────────────────

    def preview(self, run_id: UUID) -> RunPeopleDeletionPreview:
        """返回该运行人员及其级联/失联的计数预览（无副作用）。"""
        run, generations, clusters, decisions, person_ids = self._scope(run_id)
        existing = tuple(
            person_id for person_id in person_ids
            if self._people.find_by_id(person_id) is not None
        )
        names = tuple(
            person.name
            for person in (self._people.find_by_id(pid) for pid in existing)
            if person is not None
        )
        base = self._delete_person.preview(existing)
        archive_count = self._archive_count(existing)
        ground_truth_count = self._ground_truth_count(existing)

        blocked: list[str] = []
        if archive_count:
            blocked.append(
                f"该批人员已有 {archive_count} 条归档记录——删除人员会让归档记录"
                "失去人员指向（归档文件仍在磁盘上）",
            )
        if ground_truth_count:
            blocked.append(
                f"该批人员被 {ground_truth_count} 条 GT 裁定引用——删除人员会让"
                "裁定失去人员指向，身份证据不可恢复",
            )
        if base.sample_count:
            blocked.append(
                f"该批人员的多样本库有 {base.sample_count} 行——删除人员会随外键"
                "级联清除，样本不可恢复",
            )

        return RunPeopleDeletionPreview(
            run_found=run is not None,
            run_created_at=getattr(run, "created_at", None),
            run_status=str(getattr(run, "status", "") or ""),
            cluster_count=len(clusters),
            decision_count=len(decisions),
            person_ids=existing,
            people_names=names,
            embedding_count=base.embedding_count,
            recognition_count=base.recognition_count,
            assignment_count=base.assignment_count,
            sample_count=base.sample_count,
            archive_count=archive_count,
            ground_truth_count=ground_truth_count,
            blocked_reasons=tuple(blocked),
        )

    # ── 执行 ──────────────────────────────────────────────────────────

    def execute(self, command: DeleteRunPeopleCommand) -> RunPeopleDeletionResult:
        """在单事务内删除该运行的人员（A3）或解除其匹配（A1）。"""
        if command.mode not in (RUN_PEOPLE_MODE_DELETE, RUN_PEOPLE_MODE_UNASSIGN):
            raise ValidationError(f"Unknown run-people deletion mode: {command.mode}")

        def _run() -> RunPeopleDeletionResult:
            run, _generations, clusters, _decisions, _person_ids = self._scope(
                command.run_id,
            )
            if run is None:
                raise ValidationError("识别运行不存在——无法按批次删除。")
            preview = self.preview(command.run_id)
            if command.mode == RUN_PEOPLE_MODE_UNASSIGN:
                return self._unassign(clusters, preview)
            if preview.is_blocked:
                raise ValidationError("；".join(preview.blocked_reasons))
            removed = 0
            for person_id in preview.person_ids:
                removed += self._people.remove(person_id)
            return RunPeopleDeletionResult(
                requested=preview.person_count,
                removed=removed,
                missing=preview.person_count - removed,
                unassigned=0,
                embedding_cascade=preview.embedding_count,
                recognition_orphaned=preview.recognition_count,
                assignment_cascade=preview.assignment_count,
                sample_cascade=preview.sample_count,
                archive_orphaned=preview.archive_count,
                ground_truth_orphaned=preview.ground_truth_count,
            )

        if self._unit_of_work is not None:
            with self._unit_of_work:
                result = _run()
        else:
            result = _run()
        logger.info(
            "AUDIT delete-run-people actor=local-user run={} mode={} removed={} "
            "unassigned={} assignment_cascade={} sample_cascade={} "
            "recognition_orphaned={} archive_orphaned={} ground_truth_orphaned={}",
            command.run_id, command.mode, result.removed, result.unassigned,
            result.assignment_cascade, result.sample_cascade,
            result.recognition_orphaned, result.archive_orphaned,
            result.ground_truth_orphaned,
        )
        return result

    def _unassign(
        self, clusters: list["FaceCluster"], preview: RunPeopleDeletionPreview,
    ) -> RunPeopleDeletionResult:
        """A1：只解除该运行的有效匹配（状态迁移，人员与记录保留）。"""
        if self._pairing is None:
            raise ValidationError(
                "解除匹配能力不可用——请改用「删除人员及其记录」模式。",
            )
        from photo_archiver.application.commands.pairing import UnassignClusterCommand

        targets: list[UUID] = []
        for cluster in clusters:
            if cluster.id is None:  # pragma: no cover - 实体保证 id 存在
                continue
            latest = self._assignments.list_latest_decision(cluster.id)
            if latest is None or latest.status not in ACTIVE_ASSIGNMENT_STATUSES:
                continue
            targets.append(cluster.id)
        for cluster_id in targets:
            self._pairing.unassign(
                UnassignClusterCommand(cluster_id=cluster_id), actor=HUMAN_ACTOR,
            )
        return RunPeopleDeletionResult(
            requested=len(targets),
            removed=0,
            missing=0,
            unassigned=len(targets),
            embedding_cascade=0,
            recognition_orphaned=0,
            assignment_cascade=0,
            sample_cascade=0,
            archive_orphaned=0,
            ground_truth_orphaned=0,
        )
