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
    ) -> None:
        self._run_repository = recognition_run_repository
        self._observation_repository = face_observation_repository
        self._cluster_repository = face_cluster_repository

    def list_cluster_runs(self, recognition_run_id: UUID) -> list[FaceClusterRun]:
        """Return the recognition run's clustering generations, newest first."""
        return self._cluster_repository.list_cluster_runs(recognition_run_id)

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
        clusters: list[ClusterDetailView] = []
        for cluster in self._cluster_repository.list_clusters(cluster_run_id):
            if cluster.id is None:  # pragma: no cover - 实体恒生成 id
                continue
            clusters.append(self._detail(
                cluster, members_by_cluster.get(cluster.id, []), observations, photo_meta,
            ))
        return ClusterRunResults(cluster_run=cluster_run, clusters=tuple(clusters))

    @staticmethod
    def _detail(cluster, members, observations, photo_meta) -> ClusterDetailView:
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
            ))
        # 展示顺序按（照片路径, 脸序号）确定性排序——仓储按成员 id 排序，
        # 直接透出会让成员行在两次刷新间随机换位。
        members_out.sort(key=lambda member: (member.photo_path, member.face_index))
        return ClusterDetailView(
            cluster_id=cluster.id,
            ordinal=cluster.ordinal,
            status=cluster.status,
            member_count=cluster.member_count,
            first_captured_at=cluster.first_captured_at,
            members=tuple(members_out),
        )
