"""照片库「指定人员归档」服务测试（追加轮 29，Owner）.

全部走**真实 SQLite**（schema/FK/mapper 与生产一致）：

- 新建批次 + 新建人员：合成 PENDING 行 → 身份批准唯一链 → 照片归属该人
  （approved + 投影），人员挂靠新批次（confirmed 态）。
- 已导入批次同名人员**复用**（归到对应人名下，不新建第二人）。
- 多人脸照片 / 未聚类照片：诚实拒绝（部分成功语义，不中断整批）。
"""

from datetime import datetime
from pathlib import Path


from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.services.manual_attribution_service import (
    ManualAttributionCommand,
    ManualAttributionService,
)
from photo_archiver.application.services.review_recognition_service import (
    ReviewRecognitionService,
)
from photo_archiver.domain import (
    MatchStatus,
    Person,
    Photo,
    PhotoPath,
    PhotoPathBase,
)
from photo_archiver.domain.entities.import_batch import (
    BATCH_STATUS_CONFIRMED,
    ImportBatch,
)
from photo_archiver.domain.entities.face_cluster import (
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
)
from photo_archiver.domain.entities.face_observation import FaceObservation
from photo_archiver.domain.entities.recognition_run import RecognitionRun
from photo_archiver.domain.value_objects.face_box import FaceBox
from photo_archiver.domain.value_objects.face_embedding import FaceEmbedding
from photo_archiver.application.services.identity_decision_service import (
    IdentityDecisionService,
)
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
)


def _add_photo(repos, tmp_path: Path, name: str) -> Photo:
    photo = Photo(
        path=PhotoPath(tmp_path / name, base=PhotoPathBase.ABSOLUTE),
        original_name=name,
        captured_at=datetime(2026, 5, 1),
    )
    repos.photos.add(photo)
    return photo


def _cluster_photo(repos, photo: Photo, *, faces: int = 1):
    """为照片播种已聚类观测（faces=1 单脸；faces=2 多脸场景）。"""
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="test")
    repos.face_clusters.add_cluster_run(cluster_run)
    cluster = FaceCluster(
        cluster_run_id=cluster_run.id, run_id=run.id,
        ordinal=0, member_count=faces, sort_key="k|000000",
    )
    repos.face_clusters.add_clusters([cluster])
    observations = []
    for index in range(faces):
        observation = FaceObservation(
            run_id=run.id, photo_id=photo.id, face_index=index,
            photo_face_count=faces, det_score=0.9, box=FaceBox(0, 0, 10, 10),
            embedding=FaceEmbedding((1.0, float(index))),
            scope_verdict="in_selected_scope",
        )
        repos.face_observations.add_many([observation])
        observations.append(observation)
    repos.face_clusters.add_members([
        FaceClusterMember(cluster_id=cluster.id, observation_id=o.id)
        for o in observations
    ])
    return observations


def _service(repos) -> ManualAttributionService:
    reconciler = ProjectionReconciler(
        recognition_repository=repos.recognition,
        assignment_repository=repos.cluster_assignments,
        cluster_repository=repos.face_clusters,
        observation_repository=repos.face_observations,
    )
    decisions = IdentityDecisionService(
        recognition_repository=repos.recognition,
        assignment_repository=repos.cluster_assignments,
        cluster_repository=repos.face_clusters,
        observation_repository=repos.face_observations,
        person_repository=repos.people,
        sample_repository=repos.person_face_samples,
        reconciler=reconciler,
        transaction_runner=repos._connection_provider.run_immediate,
    )
    review = ReviewRecognitionService(
        repos.recognition, identity_decision_service=decisions,
    )
    return ManualAttributionService(
        repos.photos,
        repos.face_observations,
        repos.recognition,
        review,
        repos.people,
        repos.import_batches,
        run_repository=repos.recognition_runs,
    )


def test_new_batch_new_person_attributes_photo(tmp_path: Path) -> None:
    repos = build_sqlite_repositories(tmp_path / "manual.db")
    photo = _add_photo(repos, tmp_path, "a.jpg")
    _cluster_photo(repos, photo, faces=1)

    result = _service(repos).execute(ManualAttributionCommand(
        photo_ids=(photo.id,), person_name="王小明",
        new_batch_name="春游批次",
    ))

    assert result.assigned == 1
    assert result.outcomes[0].ok
    assert result.person_name == "王小明"
    assert result.batch_name == "春游批次"
    # 人员挂靠新批次，批次为 confirmed 态
    batch = repos.import_batches.get_batch(result.batch_id)
    assert batch is not None and batch.status == BATCH_STATUS_CONFIRMED
    people = [
        p for p in repos.people.list_all()
        if p.source_batch_id == result.batch_id
    ]
    assert [p.name for p in people] == ["王小明"]
    # 识别结果走身份批准链：approved + 归属该人
    row = repos.recognition.list_first_by_photo_ids([photo.id])[photo.id]
    assert row.status is MatchStatus.APPROVED
    assert row.person_id == result.person_id


def test_existing_batch_reuses_same_name_person(tmp_path: Path) -> None:
    repos = build_sqlite_repositories(tmp_path / "manual2.db")
    photo_a = _add_photo(repos, tmp_path, "a.jpg")
    _cluster_photo(repos, photo_a, faces=1)
    batch = ImportBatch(
        file_name="已有名单.txt", file_hash="h1", source_type="txt",
        status="confirmed",
    )
    repos.import_batches.add_batch(batch)
    existing = Person(name="张三", source_batch_id=batch.id)
    repos.people.add(existing)

    result = _service(repos).execute(ManualAttributionCommand(
        photo_ids=(photo_a.id,), person_name="张三",
        existing_batch_id=batch.id,
    ))

    assert result.assigned == 1
    assert result.person_id == existing.id  # 复用，不新建
    names = [
        p.name for p in repos.people.list_all()
        if p.source_batch_id == batch.id and p.name == "张三"
    ]
    assert names == ["张三"]  # 批次内仍只有一人
    row = repos.recognition.list_first_by_photo_ids([photo_a.id])[photo_a.id]
    assert row.status is MatchStatus.APPROVED
    assert row.person_id == existing.id


def test_multi_face_photo_is_rejected(tmp_path: Path) -> None:
    repos = build_sqlite_repositories(tmp_path / "manual3.db")
    multi = _add_photo(repos, tmp_path, "multi.jpg")
    _cluster_photo(repos, multi, faces=2)
    single = _add_photo(repos, tmp_path, "single.jpg")
    _cluster_photo(repos, single, faces=1)

    result = _service(repos).execute(ManualAttributionCommand(
        photo_ids=(multi.id, single.id), person_name="李四",
        new_batch_name="批次B",
    ))

    assert result.assigned == 1  # 单脸照片成功
    assert result.outcomes[0].ok is False
    assert "2 张人脸" in result.outcomes[0].reason
    assert result.outcomes[1].ok is True


def test_unclustered_photo_is_rejected(tmp_path: Path) -> None:
    repos = build_sqlite_repositories(tmp_path / "manual4.db")
    photo = _add_photo(repos, tmp_path, "loose.jpg")
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    observation = FaceObservation(
        run_id=run.id, photo_id=photo.id, face_index=0, photo_face_count=1,
        det_score=0.9, box=FaceBox(0, 0, 10, 10),
        embedding=FaceEmbedding((1.0, 0.0)), scope_verdict="in_selected_scope",
    )
    repos.face_observations.add_many([observation])  # 有观测但未入簇

    result = _service(repos).execute(ManualAttributionCommand(
        photo_ids=(photo.id,), person_name="王五", new_batch_name="批次C",
    ))

    assert result.assigned == 0
    assert result.outcomes[0].ok is False


def test_preview_reports_eligibility_without_side_effects(tmp_path: Path) -> None:
    repos = build_sqlite_repositories(tmp_path / "manual5.db")
    photo = _add_photo(repos, tmp_path, "a.jpg")
    _cluster_photo(repos, photo, faces=1)

    preview = _service(repos).preview((photo.id,))

    assert preview[photo.id] == ""  # 可归档
    assert repos.recognition.list_first_by_photo_ids([photo.id]).get(photo.id) is None
