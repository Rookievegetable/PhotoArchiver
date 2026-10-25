"""Cluster results read service — D-4 聚类结果展示的数据入口.

与 ``ListPersonsService``/``SearchPhotosService`` 同模式的薄读用例：把
持久化的 ``FaceClusterRun → FaceCluster → FaceClusterMember →
FaceObservation``（+ run_photos 快照）拼装成展示视图，零业务决策、零
SQL、零 GUI。展示层绝不直接触仓储（DEP-003/004），也绝不重算聚类。
"""

from uuid import UUID

from loguru import logger

from photo_archiver.application.dtos.cluster_results import (
    ClusterDetailView,
    ClusterMemberDetail,
    ClusterRunResults,
)
from photo_archiver.domain import (
    ClusterPersonAssignmentRepository,
    FaceClusterMember,
    FaceClusterRepository,
    FaceObservationRepository,
    FaceClusterRun,
    RecognitionRunRepository,
    RunPhotoSnapshot,
)


class ClusterResultsService:
    """Read persisted cluster generations and their member details."""

    def __init__(
        self,
        recognition_run_repository: RecognitionRunRepository,
        face_observation_repository: FaceObservationRepository,
        face_cluster_repository: FaceClusterRepository,
        assignment_repository: ClusterPersonAssignmentRepository | None = None,
        photo_ignore_repository=None,
    ) -> None:
        self._run_repository = recognition_run_repository
        self._observation_repository = face_observation_repository
        self._cluster_repository = face_cluster_repository
        self._assignment_repository = assignment_repository
        # 界面优化 §3.1：注入后可查询每代际的被忽略照片（展示标记用）。
        self._ignore_repository = photo_ignore_repository

    def ignored_photo_ids(self, cluster_run_id: UUID) -> set[UUID]:
        """Return the generation's ignored photo ids (empty when port absent)."""
        if self._ignore_repository is None:
            return set()
        return set(self._ignore_repository.list_photo_ids(cluster_run_id))

    def run_photo_outcome_summary(
        self, recognition_run_id: UUID,
    ) -> dict[str, int]:
        """Per-outcome photo counts of one recognition run（界面优化 §5.3）.

        返回键：total/not_processed/faces/no_face/unreadable/error/unknown；
        ``unknown`` 是历史 run 的 NULL 状态计数——展示为"未知"，绝不并入
        no_face。照片是否属于 run 由本计数（输入快照行）判断。
        """
        summary = {
            "total": 0, "not_processed": 0, "faces": 0, "no_face": 0,
            "unreadable": 0, "error": 0, "unknown": 0,
        }
        for snapshot in self._run_repository.list_run_photos(recognition_run_id):
            summary["total"] += 1
            if snapshot.photo_outcome is None:
                summary["unknown"] += 1
            else:
                summary[snapshot.photo_outcome] = (
                    summary.get(snapshot.photo_outcome, 0) + 1
                )
        return summary

    def active_person_ids(self, cluster_run_id: UUID) -> set[UUID]:
        """Distinct persons among the generation's active decisions（§5.3 口径）.

        口径固定为当前有效决策（suggested / auto_confirmed / confirmed）
        涉及的不同 ``person_id``——是"当前有效决策涉及的人物数"，不是视觉
        算法识别出的真实人数。
        """
        if self._assignment_repository is None:
            return set()
        return {
            assignment.person_id
            for assignment in self._assignment_repository.list_active_by_cluster_run(
                cluster_run_id,
            )
            if assignment.person_id is not None
        }

    def list_cluster_runs(self, recognition_run_id: UUID) -> list[FaceClusterRun]:
        """Return the recognition run's clustering generations, newest first."""
        return self._cluster_repository.list_cluster_runs(recognition_run_id)

    def assignments_active(self, cluster_run_id: UUID) -> list:
        """Return the generation's active (suggested/confirmed) decisions."""
        if self._assignment_repository is None:
            return []
        return self._assignment_repository.list_active_by_cluster_run(cluster_run_id)

    def results(self, cluster_run_id: UUID) -> ClusterRunResults | None:
        """Assemble one generation's clusters and members; ``None`` if absent."""
        cluster_run = self._cluster_repository.get_cluster_run(cluster_run_id)
        if cluster_run is None:
            return None
        observations = {
            observation.id: observation
            for observation in self._observation_repository.list_by_run(
                cluster_run.recognition_run_id,
            )
        }
        photo_meta: dict[UUID, RunPhotoSnapshot] = {
            snapshot.photo_id: snapshot
            for snapshot in self._run_repository.list_run_photos(
                cluster_run.recognition_run_id,
            )
        }
        members_by_cluster: dict[UUID, list[FaceClusterMember]] = {}
        for member in self._cluster_repository.list_members(cluster_run_id):
            members_by_cluster.setdefault(member.cluster_id, []).append(member)
        ignored_photo_ids = self.ignored_photo_ids(cluster_run_id)
        clusters: list[ClusterDetailView] = []
        for cluster in self._cluster_repository.list_clusters(cluster_run_id):
            if cluster.id is None:  # pragma: no cover - 实体恒生成 id
                continue
            clusters.append(self._detail(
                cluster, members_by_cluster.get(cluster.id, []), observations, photo_meta,
                ignored_photo_ids,
            ))
        return ClusterRunResults(cluster_run=cluster_run, clusters=tuple(clusters))

    @staticmethod
    def _detail(cluster, members, observations, photo_meta, ignored_photo_ids=frozenset(),
    ) -> ClusterDetailView:
        """Build one cluster's read view; members whose observation vanished
        （正常不会发生——FK 级联会同步删除成员行）被防御性跳过。"""
        members_out: list[ClusterMemberDetail] = []
        for member in members:
            if member.observation_id is None:  # pragma: no cover - 实体恒生成 id
                continue
            observation = observations.get(member.observation_id)
            if observation is None:
                logger.warning(
                    "ClusterResultsService: member {} references missing observation {}",
                    member.id, member.observation_id,
                )
                continue
            snapshot = photo_meta.get(observation.photo_id)
            members_out.append(ClusterMemberDetail(
                observation_id=observation.id,
                cluster_id=cluster.id,
                photo_id=observation.photo_id,
                photo_path=snapshot.raw_path if snapshot is not None else "",
                face_index=observation.face_index,
                det_score=observation.det_score,
                confidence=member.confidence,
                quality_score=observation.quality_score,
                captured_at=snapshot.captured_at if snapshot is not None else None,
                photo_face_count=observation.photo_face_count,
                photo_outcome=(
                    snapshot.photo_outcome if snapshot is not None else None
                ),
            ))
        # 展示顺序按（照片路径, 脸序号）确定性排序——仓储按成员 id 排序，
        # 直接透出会让成员行在两次刷新间随机换位。
        members_out.sort(key=lambda member: (member.photo_path, member.face_index))
        cluster_photo_ids = {
            member.photo_id for member in members_out if member.photo_id is not None
        }
        return ClusterDetailView(
            cluster_id=cluster.id,
            ordinal=cluster.ordinal,
            status=cluster.status,
            member_count=cluster.member_count,
            first_captured_at=cluster.first_captured_at,
            members=tuple(members_out),
            photo_count=len(cluster_photo_ids),
            ignored_photo_ids=tuple(sorted(
                cluster_photo_ids & set(ignored_photo_ids), key=str,
            )),
        )
