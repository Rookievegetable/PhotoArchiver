"""Traceable face clustering service（阶段 D 第一阶段）.

编排一次聚类执行：读取 Stage C 的 ``FaceObservation`` → 构建相似度
kernel（numpy 实现经端口注入，本层零 numpy）→ 调用领域纯算法（两段式，
owner 裁决）→ 以方案 §D-3 排序键落库 Cluster/Member → 记录统计与终态。

硬约束落点：

- 输入只来自已有 Observation（不重新扫描/检测）；默认只取
  ``in_selected_scope`` 且嵌入有效的观测（任务书默认，规格 §5.2“全部”
  未明确范围裁定，``scope_filter`` 记入参数快照可追溯）。
- 重跑 = 新 ``FaceClusterRun`` 新组，旧组不动；绝不因已有 Cluster 跳过。
- 取消协作式：算法在候选/合并轮询间检查；取消前已落库的 cluster 保留。
- 失败隔离：算法纯函数不落库；持久化异常将 cluster run 置 failed 后抛出。
"""

from datetime import datetime, timezone
from threading import Event
from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.cluster_faces import StartClusteringRunCommand
from photo_archiver.application.ports.similarity_kernel import SimilarityKernelFactory
from photo_archiver.application.use_cases.cluster_faces import ClusterFacesUseCase
from photo_archiver.domain import (
    ALGORITHM_VERSION,
    ClusteringCancelled,
    ClusteringItem,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRepository,
    FaceClusterRun,
    FaceObservationRepository,
    RecognitionRunRepository,
    RunPhotoSnapshot,
    ValidationError,
    build_sort_key,
    cluster_items,
    order_cluster_keys,
)
from photo_archiver.domain.entities.face_observation import (
    SCOPE_VERDICT_IN_SELECTED_SCOPE,
)


class ClusterFacesService(ClusterFacesUseCase):
    """Run one clustering execution over a recognition run's face observations."""

    def __init__(
        self,
        recognition_run_repository: RecognitionRunRepository,
        face_observation_repository: FaceObservationRepository,
        face_cluster_repository: FaceClusterRepository,
        similarity_factory: SimilarityKernelFactory,
        progress_reporter=None,
    ) -> None:
        self._run_repository = recognition_run_repository
        self._observation_repository = face_observation_repository
        self._cluster_repository = face_cluster_repository
        self._similarity_factory = similarity_factory
        self._progress_reporter = progress_reporter
        self._cancel_event = Event()

    def cancel(self) -> None:
        """Request cooperative cancellation of the in-flight clustering."""
        self._cancel_event.set()

    def execute(self, command: StartClusteringRunCommand) -> FaceClusterRun:
        """Execute a new cluster run; reruns always insert a new cluster set."""
        self._cancel_event.clear()
        recognition_run = self._run_repository.get_run(command.recognition_run_id)
        if recognition_run is None:
            raise ValidationError(
                f"RecognitionRun {command.recognition_run_id} does not exist"
            )
        cluster_run = FaceClusterRun(
            recognition_run_id=command.recognition_run_id,
            algorithm_version=ALGORITHM_VERSION,
            parameters=command.parameters(),
        )
        if cluster_run.id is None:
            raise RuntimeError("FaceClusterRun did not generate an id")
        self._cluster_repository.add_cluster_run(cluster_run)
        cluster_run.start()
        self._cluster_repository.update_cluster_run(cluster_run)
        try:
            counts = self._cluster_all(cluster_run.id, command)
            if self._cancel_event.is_set():
                cluster_run.cancel(*counts)
            else:
                cluster_run.complete(*counts)
            self._cluster_repository.update_cluster_run(cluster_run)
            return cluster_run
        except ClusteringCancelled:
            # 算法阶段取消：无任何 cluster 落库，统计保持 0。
            cluster_run.cancel()
            self._cluster_repository.update_cluster_run(cluster_run)
            return cluster_run
        except Exception as exc:
            cluster_run.fail(str(exc))
            self._cluster_repository.update_cluster_run(cluster_run)
            raise

    def _cluster_all(
        self, cluster_run_id: UUID, command: StartClusteringRunCommand,
    ) -> tuple[int, int, int]:
        """Cluster, persist and report; returns (cluster, member, excluded) counts."""
        observations = self._observation_repository.list_by_run(command.recognition_run_id)
        participating = _select_participating(observations)
        excluded_count = len(observations) - len(participating)
        if not participating:
            self._report(0, 0, "No observations to cluster")
            return 0, 0, excluded_count
        # 确定性输入序：det_score 降序 → bbox 字典序 → observation id（对齐
        # Stage C face_index 语义；id 兜底保证全序）。
        participating.sort(key=_deterministic_order)
        items = [
            ClusteringItem(observation_id=observation.id, quality_score=observation.quality_score)
            for observation in participating
        ]
        self._report(0, len(items), "Building similarity kernel")
        lookup = self._similarity_factory.build(
            [observation.embedding for observation in participating],
        )
        self._report(0, len(items), "Clustering face observations")
        assignments = cluster_items(
            items,
            lookup,
            cluster_sim_threshold=command.cluster_sim_threshold,
            consistency_threshold=command.consistency_threshold,
            low_quality_threshold=command.low_quality_threshold,
            should_cancel=self._cancel_event.is_set,
        )
        self._report(len(items), len(items), "Persisting clusters")
        self._persist(cluster_run_id, command.recognition_run_id, participating, assignments)
        logger.info(
            "ClusterFacesService: run {} clustered {} observation(s) into {} cluster(s) "
            "({} excluded)",
            command.recognition_run_id, len(participating), len(assignments), excluded_count,
        )
        return len(assignments), len(participating), excluded_count

    def _persist(
        self,
        cluster_run_id: UUID,
        recognition_run_id: UUID,
        participating,
        assignments,
    ) -> None:
        """Persist clusters in §D-3 sort order with their membership evidence."""
        photo_meta: dict[UUID, RunPhotoSnapshot] = {
            snapshot.photo_id: snapshot
            for snapshot in self._run_repository.list_run_photos(recognition_run_id)
        }
        # 每簇一次扫描同时得到排序键部件与 first_captured_at（datetime 值比较；
        # 同簇内混入 aware 等异型时间时比较抛 TypeError → run=failed、零簇落库）。
        decorated: list[tuple[str | None, str, int, datetime | None]] = []
        for creation_index, assignment in enumerate(assignments):
            earliest_iso, path_key, earliest_dt = self._earliest_capture(
                participating, photo_meta, assignment,
            )
            decorated.append((earliest_iso, path_key, creation_index, earliest_dt))
        ordinals = {
            position: rank
            for rank, position in enumerate(
                order_cluster_keys(
                    [(iso, path_key, index) for iso, path_key, index, _ in decorated],
                ),
            )
        }
        clusters: list[FaceCluster] = []
        members: list[FaceClusterMember] = []
        for position, assignment in enumerate(assignments):
            earliest_iso, path_key, tiebreak, earliest_dt = decorated[position]
            cluster = FaceCluster(
                cluster_run_id=cluster_run_id,
                run_id=recognition_run_id,
                ordinal=ordinals[position],
                member_count=len(assignment.members),
                sort_key=build_sort_key(earliest_iso, path_key, tiebreak),
                first_captured_at=earliest_dt,
            )
            clusters.append(cluster)
            if cluster.id is None:  # pragma: no cover - entity always generates an id
                raise RuntimeError("FaceCluster did not generate an id")
            for member_position, item_index in enumerate(assignment.members):
                observation = participating[item_index]
                members.append(FaceClusterMember(
                    cluster_id=cluster.id,
                    observation_id=observation.id,
                    confidence=assignment.confidences[member_position],
                ))
        self._cluster_repository.add_clusters(clusters)
        self._cluster_repository.add_members(members)

    @staticmethod
    def _earliest_capture(
        participating, photo_meta, assignment,
    ) -> tuple[str | None, str, datetime | None]:
        """(earliest captured_at ISO, stable path key, earliest datetime) per cluster.

        最早时间取成员照片（run_photos 快照）中非空 captured_at 的最小
        datetime 值（直接值比较，表达方案 §D-3 时间序；同簇内 naive/aware
        混型比较抛 TypeError——契约外输入 fail-closed，不做类型归一）；
        同刻多照片取路径字典序最小者；全簇无时间 → (None, "~", None)，
        不得用照片注册时间替代（方案 §D-3）。ISO 文本恒为六位微秒精度
        （timespec=microseconds）：同代际内时间段定宽，文本序==时间序。
        aware 时间的排序文本统一为 UTC 绝对表示（astimezone(utc)）：不同
        偏移的同一瞬间得到相同时间分量，同刻路径决胜对跨偏移表述成立；
        naive 保持原文本与语义，不假设其时区。
        """
        earliest_dt: datetime | None = None
        earliest_paths: list[str] = []
        for item_index in assignment.members:
            snapshot = photo_meta.get(participating[item_index].photo_id)
            if snapshot is None or snapshot.captured_at is None:
                continue
            captured_at = snapshot.captured_at
            if earliest_dt is None or captured_at < earliest_dt:
                earliest_dt = captured_at
                earliest_paths = [snapshot.raw_path]
            elif captured_at == earliest_dt:
                earliest_paths.append(snapshot.raw_path)
        path_key = min(earliest_paths) if earliest_paths else "~"
        return (
            (
                earliest_dt.astimezone(timezone.utc).isoformat(
                    timespec="microseconds"
                )
                if earliest_dt.tzinfo is not None
                else earliest_dt.isoformat(timespec="microseconds")
            )
            if earliest_dt is not None
            else None,
            path_key,
            earliest_dt,
        )

    def _report(self, current: int, total: int, message: str) -> None:
        if self._progress_reporter is not None:
            self._progress_reporter.report(current, total, message)


def _select_participating(observations) -> list:
    """范围内且嵌入有效的观测（任务书默认；scope_filter 记入参数快照）。"""
    return [
        observation for observation in observations
        if observation.scope_verdict == SCOPE_VERDICT_IN_SELECTED_SCOPE
        and observation.embedding.vector
    ]


def _deterministic_order(observation) -> tuple:
    """det_score 降序 → bbox 字典序 → observation id 兜底全序。"""
    return (
        -observation.det_score,
        observation.box.x1, observation.box.y1,
        observation.box.x2, observation.box.y2,
        str(observation.id),
    )
