"""Roster cluster statistics read service — 界面优化 P4（人员页统计面板）.

与 ``ClusterResultsService`` 同模式的薄读用例：把人员页右侧统计面板需要的
四个数字从既有持久化数据中拼装出来，零业务决策、零 SQL、零写入、零 GUI。
展示层绝不直接触仓储（DEP-003/004）。

口径（任务书 §1.1，D2-A/D3-A 裁决）：
- 锚点 = 当前选中识别运行的**最新代际**（``list_cluster_runs`` newest-first
  首位）；批次筛选不联动统计（人员域与聚类域分离）。
- 照片数 = 锚点代际成员覆盖的去重照片数（成员行 → observation.photo_id）；
- 人脸数 = 锚点代际观测成员数（成员行总数）；
- 已匹配人物数 = 该代际 active 决策涉及的不同 person 数
  （复用既有 ``list_active_by_cluster_run`` 读取，无需扩展仓储 Protocol）；
- 未匹配人物数 = 名单总数 − 已匹配人物数（名单总数由调用方传入——roster
  属人员域，页面已经由 ``ManagePeopleService`` 装载）。

所需读取（``list_cluster_runs`` / ``list_members`` / ``list_by_run`` /
``list_active_by_cluster_run``）均为既有 Protocol 方法，SQLite 与 InMemory
双实现已存在——本用例零新增仓储方法。
"""

from uuid import UUID

from photo_archiver.application.dtos.cluster_results import RosterClusterStats
from photo_archiver.domain import (
    ClusterPersonAssignmentRepository,
    FaceClusterRepository,
    FaceClusterRun,
    FaceObservationRepository,
)


class RosterClusterStatsService:
    """Read the people-page statistics anchored to the latest generation."""

    def __init__(
        self,
        face_cluster_repository: FaceClusterRepository,
        face_observation_repository: FaceObservationRepository,
        assignment_repository: ClusterPersonAssignmentRepository | None = None,
    ) -> None:
        """Store the read-only ports (assignment port optional, mirroring
        ``ClusterResultsService``: ``None`` 时已匹配人物数恒 0）。"""
        self._cluster_repository = face_cluster_repository
        self._observation_repository = face_observation_repository
        self._assignment_repository = assignment_repository

    def anchor_generation(self, recognition_run_id: UUID) -> FaceClusterRun | None:
        """Return the run's latest clustering generation, or ``None``.

        锚点定义：``list_cluster_runs``（newest-first）首位；无代际时无锚点。
        """
        generations = self._cluster_repository.list_cluster_runs(recognition_run_id)
        return generations[0] if generations else None

    def matched_person_ids(self, recognition_run_id: UUID) -> set[UUID]:
        """Distinct persons among the anchor generation's active decisions.

        D3-A：人员行的「未匹配」标记按锚点（最新代际）判定——本集合即
        「已匹配」人员域；无锚点代际时返回空集（全部行视为无判定数据）。
        """
        anchor = self.anchor_generation(recognition_run_id)
        if anchor is None or anchor.id is None or self._assignment_repository is None:
            return set()
        return {
            assignment.person_id
            for assignment in self._assignment_repository.list_active_by_cluster_run(
                anchor.id,
            )
            if assignment.person_id is not None
        }

    def stats(
        self, recognition_run_id: UUID, roster_total: int,
    ) -> RosterClusterStats | None:
        """Assemble the panel's four numbers; ``None`` when the run has no
        generation（调用方据此展示空态文案）.

        ``roster_total``：名单总数（人员域读数，由调用方传入）。
        未匹配人物数做 ``max(0, …)`` 防御——正常 FK 级联保证已匹配 ⊆ 名单，
        防御只为不让异常数据把面板渲染成负数。
        """
        anchor = self.anchor_generation(recognition_run_id)
        if anchor is None or anchor.id is None:
            return None
        observations = {
            observation.id: observation
            for observation in self._observation_repository.list_by_run(
                anchor.recognition_run_id,
            )
        }
        members = self._cluster_repository.list_members(anchor.id)
        photo_ids = {
            observations[member.observation_id].photo_id
            for member in members
            if member.observation_id is not None
            and member.observation_id in observations
        }
        matched = len(self.matched_person_ids(recognition_run_id))
        return RosterClusterStats(
            cluster_run_id=anchor.id,
            anchor_created_at=anchor.created_at,
            photo_count=len(photo_ids),
            face_count=len(members),
            matched_person_count=matched,
            unmatched_person_count=max(0, roster_total - matched),
        )
