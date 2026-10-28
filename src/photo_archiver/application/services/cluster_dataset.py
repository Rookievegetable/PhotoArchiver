"""聚类数据集组装——全库最新特征（任务书 §3 A2）.

两种数据集口径，由 ``FaceClusterRun.parameters`` 的 ``dataset`` 键驱动：

- ``library``：跨**所有**识别运行的观测，按照片取**最新**运行的那份
  （latest wins）。多次扫描产生的增量运行由此合并为一份全库特征数据集；
  同照片因内容变化/重试产生的多份历史观测被该规则自然消解。
- ``single_run``（缺省/历史代际）：仅锚点运行（``recognition_run_id``）的
  观测——与 resolver 引入前的行为逐字段一致。

三个读取口径与成员展示/汇总共用同一套"照片归属运行"判定：

- 观测（成员→观测映射）：照片的特征归属于**拥有其观测的最新运行**——
  未完成（not_processed/cancelled）的运行不抢占既有有效特征；
- 成员快照（路径/首拍/状态展示）：与观测同运行，保证成员与其检测元数据
  同源；
- outcome 汇总（运行状态行）：按照片取**最新一次尝试**（含未成功），如实
  反映数据集内照片的最新处理状态。
"""

from __future__ import annotations

from uuid import UUID

from photo_archiver.application.commands.cluster_faces import DATASET_LIBRARY
from photo_archiver.domain import (
    FaceClusterRun,
    FaceObservation,
    RecognitionRunRepository,
    RunPhotoSnapshot,
)


def is_library_dataset(cluster_run: FaceClusterRun) -> bool:
    """Whether this generation reads the whole-library latest feature dataset."""
    parameters = getattr(cluster_run, "parameters", None) or {}
    return parameters.get("dataset") == DATASET_LIBRARY


def _latest_feature_run_by_photo(
    run_repository: RecognitionRunRepository,
    observation_repository,
) -> dict[UUID, UUID]:
    """photo_id → 拥有其观测的最新 run_id（runs 按 created_at 降序，首见即最新）。

    判定基于**观测存在**而非 run_photos 行——未产出观测的运行（取消/失败）
    不抢占该照片既有有效特征。
    """
    owner: dict[UUID, UUID] = {}
    for run in run_repository.list_runs():
        if run.id is None:  # pragma: no cover - 实体恒生成 id
            continue
        for observation in observation_repository.list_by_run(run.id):
            photo_id = observation.photo_id
            if photo_id is not None and photo_id not in owner:
                owner[photo_id] = run.id
    return owner


def _latest_snapshot_by_photo(
    run_repository: RecognitionRunRepository,
) -> dict[UUID, RunPhotoSnapshot]:
    """photo_id → 最新一次尝试的 run_photos 快照（含未成功 outcome）。"""
    latest: dict[UUID, RunPhotoSnapshot] = {}
    for run in run_repository.list_runs():
        if run.id is None:  # pragma: no cover - 实体恒生成 id
            continue
        for snapshot in run_repository.list_run_photos(run.id):
            if snapshot.photo_id is not None and snapshot.photo_id not in latest:
                latest[snapshot.photo_id] = snapshot
    return latest


def observations_for(
    cluster_run: FaceClusterRun,
    run_repository: RecognitionRunRepository,
    observation_repository,
) -> dict[UUID, FaceObservation]:
    """该代际可用的观测映射（observation id → 观测）。

    ``single_run`` 口径 = 锚点运行观测（历史行为）；``library`` 口径 =
    各照片归属运行（拥有其观测的最新运行）的观测合集——加载按运行进行、
    保留行按照片归属过滤，杜绝旧运行对同照片历史观测的混入。
    """
    if not is_library_dataset(cluster_run):
        return {
            observation.id: observation
            for observation in observation_repository.list_by_run(
                cluster_run.recognition_run_id,
            )
            if observation.id is not None
        }
    owner = _latest_feature_run_by_photo(run_repository, observation_repository)
    observations: dict[UUID, FaceObservation] = {}
    for run in run_repository.list_runs():
        if run.id is None:  # pragma: no cover - 实体恒生成 id
            continue
        owned_photos = {
            photo_id for photo_id, run_id in owner.items() if run_id == run.id
        }
        if not owned_photos:
            continue
        for observation in observation_repository.list_by_run(run.id):
            if observation.id is None:  # pragma: no cover - 实体恒生成 id
                continue
            if observation.photo_id in owned_photos:
                observations[observation.id] = observation
    return observations


def snapshots_for(
    cluster_run: FaceClusterRun,
    run_repository: RecognitionRunRepository,
    observation_repository,
) -> dict[UUID, RunPhotoSnapshot]:
    """成员展示用快照映射（photo_id → 快照）。

    ``single_run`` = 锚点运行快照；``library`` = 各照片**归属运行**（拥有其
    观测的最新运行）的快照——成员路径/首拍与其检测数据同源。
    """
    if not is_library_dataset(cluster_run):
        return {
            snapshot.photo_id: snapshot
            for snapshot in run_repository.list_run_photos(
                cluster_run.recognition_run_id,
            )
            if snapshot.photo_id is not None
        }
    owner = _latest_feature_run_by_photo(run_repository, observation_repository)
    latest = _latest_snapshot_by_photo(run_repository)
    snapshots: dict[UUID, RunPhotoSnapshot] = {}
    for run in run_repository.list_runs():
        if run.id is None:  # pragma: no cover - 实体恒生成 id
            continue
        for snapshot in run_repository.list_run_photos(run.id):
            if (
                snapshot.photo_id is not None
                and owner.get(snapshot.photo_id) == run.id
                and snapshot.photo_id not in snapshots
            ):
                snapshots[snapshot.photo_id] = snapshot
    # 归属运行无快照行（防御：观测在而快照行缺失）时退回最新快照。
    for photo_id in owner:
        if photo_id in snapshots:
            continue
        fallback = latest.get(photo_id)
        if fallback is not None:
            snapshots[photo_id] = fallback
    return snapshots


def outcome_summary_for(
    cluster_run: FaceClusterRun,
    run_repository: RecognitionRunRepository,
) -> dict[str, int]:
    """数据集内照片的**最新一次尝试** outcome 计数（运行状态行）。

    ``single_run`` = 锚点运行逐行计数（历史行为）；``library`` = 各照片
    最新快照 outcome 计数（latest attempt wins，未成功照实计入）。
    """
    summary = {
        "total": 0, "not_processed": 0, "faces": 0, "no_face": 0,
        "unreadable": 0, "error": 0, "unknown": 0,
    }
    if not is_library_dataset(cluster_run):
        rows = run_repository.list_run_photos(cluster_run.recognition_run_id)
    else:
        rows = list(_latest_snapshot_by_photo(run_repository).values())
    for snapshot in rows:
        summary["total"] += 1
        if snapshot.photo_outcome is None:
            summary["unknown"] += 1
        else:
            summary[snapshot.photo_outcome] = (
                summary.get(snapshot.photo_outcome, 0) + 1
            )
    return summary
