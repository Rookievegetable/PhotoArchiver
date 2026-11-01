"""批次级删除（识别运行锚点）— 真实 SQLite 集成测试.

级联语义的唯一裁判是真实 SQLite（ADR-034 §4.4）：本文件验证

- 删除运行照片 → 识别/归档/观测/成员/样本/其它运行快照逐级级联消失，
  簇计数回写、空簇有效决策迁为 unassigned（B1）；purge 时代际与决策行
  一并消失（B2）；
- 删除运行人员 → 决策行跨代际级联、识别/归档/GT 归属置空（A3）；
  仅解除匹配保留人员（A1）；
- 硬阻断（D5）：归档记录 / GT 裁定 / 样本任一非空即拒绝执行。

全部使用 tmp_path 隔离数据库；不触碰生产库。
"""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands.deletion import (
    RUN_PEOPLE_MODE_DELETE,
    RUN_PEOPLE_MODE_UNASSIGN,
    DeleteRunPeopleCommand,
    DeleteRunPhotosCommand,
    DeleteRunRecordCommand,
)
from photo_archiver.application.services import (
    DeleteRunPeopleService,
    DeleteRunPhotosService,
    DeleteRunRecordService,
)
from photo_archiver.domain import (
    ArchiveRecord,
    ArchiveStatus,
    FaceBox,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceEmbedding,
    FaceObservation,
    Person,
    PersonFaceSample,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionResult,
    RecognitionRun,
    RunPhotoSnapshot,
)
from photo_archiver.domain.entities.calibration_annotation import (
    CalibrationGroundTruth,
)
from photo_archiver.domain.entities.cluster_assignment import (
    ASSIGNMENT_SOURCE_MANUAL,
    ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
    ClusterPersonAssignment,
)
from photo_archiver.domain.exceptions import ValidationError

_BASE = datetime(2026, 1, 1, 8, 0, 0)


def _world(tmp_path: Path, *, with_samples: bool = True):
    """两个运行共享一张照片；两簇各指一人；样本/识别记录各留痕.

    run1: photo_0, photo_1（观测各一，簇 c1/c2 各一成员，决策行两条，
          识别记录两条；with_samples 时再留样本两条）
    run2: 快照引用 photo_0（用于验证其它运行快照的级联）

    样本会触发 D5 硬阻断，所以照片侧测试用 ``with_samples=False``。
    """
    repos = build_sqlite_repositories(tmp_path / "run_delete.sqlite3")
    run1 = RecognitionRun(parameters={})
    run2 = RecognitionRun(parameters={})
    repos.recognition_runs.add_run(run1)
    repos.recognition_runs.add_run(run2)

    person_a = Person(name="人员甲", roster_order=1)
    person_b = Person(name="人员乙", roster_order=2)
    repos.people.add(person_a)
    repos.people.add(person_b)

    cluster_run = FaceClusterRun(recognition_run_id=run1.id, algorithm_version="v1")
    repos.face_clusters.add_cluster_run(cluster_run)

    photos = []
    observations = []
    clusters = []
    people = (person_a, person_b)
    for index in range(2):
        photo = Photo(
            path=PhotoPath(
                tmp_path / f"photo_{index}.jpg", PhotoPathBase.ABSOLUTE,
            ),
            captured_at=_BASE,
        )
        repos.photos.add(photo)
        photos.append(photo)
        observation = FaceObservation(
            run_id=run1.id, photo_id=photo.id, face_index=0, photo_face_count=1,
            det_score=0.9, box=FaceBox(0, 0, 10, 10),
            embedding=FaceEmbedding((1.0, float(index), 0.0)),
            scope_verdict="in_selected_scope", quality_score=0.9,
        )
        repos.face_observations.add_many([observation])
        observations.append(observation)
        cluster = FaceCluster(
            cluster_run_id=cluster_run.id, run_id=run1.id, ordinal=index,
            member_count=1, sort_key=f"k|g0{index}|000000{index}",
            first_captured_at=_BASE,
        )
        repos.face_clusters.add_clusters([cluster])
        clusters.append(cluster)
        repos.face_clusters.add_members([
            FaceClusterMember(cluster_id=cluster.id, observation_id=observation.id),
        ])
        if index == 0:
            repos.cluster_assignments.add_assignments([ClusterPersonAssignment(
                cluster_id=cluster.id, person_id=person_a.id,
                status="confirmed", source=ASSIGNMENT_SOURCE_MANUAL,
            )])
        else:
            decision = ClusterPersonAssignment(
                cluster_id=cluster.id, person_id=person_b.id,
                source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
            )
            decision.auto_confirm({"auto_confirmed_at": _BASE.isoformat()})
            repos.cluster_assignments.add_assignments([decision])
        if with_samples:
            repos.person_face_samples.add_samples([PersonFaceSample(
                person_id=people[index].id, observation_id=observation.id,
                embedding=observation.embedding, quality_score=0.9,
            )])
        repos.recognition.add(RecognitionResult(
            photo_id=photo.id, confidence=0.8, person_id=people[index].id,
        ))

    # 运行快照：run1 引用两张照片，run2 共享 photo_0 —— 验证"其它运行快照"的
    # 级联与披露。
    repos.recognition_runs.add_run_photos(run1.id, [
        RunPhotoSnapshot(
            run_id=run1.id, photo_id=photo.id, raw_path=f"p{index}.jpg",
            captured_at=_BASE,
        )
        for index, photo in enumerate(photos)
    ])
    repos.recognition_runs.add_run_photos(run2.id, [RunPhotoSnapshot(
        run_id=run2.id, photo_id=photos[0].id, raw_path="p0.jpg",
        captured_at=_BASE,
    )])
    return repos, run1, run2, photos, clusters, person_a, person_b


def _people_service(repos, *, with_pairing: bool = False) -> DeleteRunPeopleService:
    from photo_archiver.application.services import (
        DeletePersonService,
        PairingWorkbenchService,
    )

    delete_person = DeletePersonService(
        repos.people, repos.photos, repos.recognition, repos.face_embeddings,
        assignment_repository=repos.cluster_assignments,
        sample_repository=repos.person_face_samples,
    )
    pairing = (
        PairingWorkbenchService(
            repos.cluster_assignments,
            repos.face_clusters,
            repos.face_observations,
            repos.people,
            repos.recognition,
            repos.person_face_samples,
            # 事务边界由 DeleteRunPeopleService 的 UoW 承担——这里绝不传
            # transaction_runner（SQLite 不支持嵌套事务）。
        )
        if with_pairing else None
    )
    return DeleteRunPeopleService(
        repos.recognition_runs,
        repos.face_clusters,
        repos.cluster_assignments,
        repos.people,
        delete_person,
        repos.archive_records,
        repos.calibration_annotations,
        pairing_service=pairing,
    )


def _photos_service(repos) -> DeleteRunPhotosService:
    return DeleteRunPhotosService(
        repos.recognition_runs,
        repos.photos,
        repos.recognition,
        repos.archive_records,
        repos.face_observations,
        repos.person_face_samples,
        repos.face_clusters,
        repos.cluster_assignments,
        repos.calibration_annotations,
    )


def _record_service(repos) -> DeleteRunRecordService:
    return DeleteRunRecordService(
        repos.recognition_runs,
        repos.face_observations,
        repos.face_clusters,
        repos.cluster_assignments,
        repos.calibration_annotations,
    )


# ── B：删除运行照片 ──────────────────────────────────────────────────────


def test_delete_run_photos_cascades_recounts_and_migrates(tmp_path: Path) -> None:
    """B1：照片登记删除 → 级联消失 + 簇计数回写 + 空簇决策迁 unassigned。"""
    repos, run1, run2, photos, clusters, person_a, person_b = _world(
        tmp_path, with_samples=False,
    )
    service = _photos_service(repos)

    preview = service.preview(run1.id)
    assert preview.run_found is True
    assert preview.photo_count == 2
    assert preview.recognition_count == 2
    assert preview.observation_count == 2
    assert preview.member_count == 2
    assert preview.sample_count == 0  # with_samples=False：无样本即无阻断
    assert preview.other_run_snapshot_count == 1  # run2 的 photo_0 快照
    assert preview.decision_count == 2
    assert preview.is_blocked is False

    result = service.execute(DeleteRunPhotosCommand(run_id=run1.id))

    assert result.removed == 2
    assert result.missing == 0
    # 照片登记与全部级联行消失
    for photo in photos:
        assert repos.photos.find_by_id(photo.id) is None
    assert repos.recognition.list_by_photo_ids([p.id for p in photos]) == []
    assert repos.person_face_samples.list_by_observation_ids(
        [o.id for o in _observations_of(repos, run1)],
    ) == []
    # 簇与代际保留，但计数被回写为实际成员数 0
    assert repos.face_clusters.list_cluster_runs(run1.id) != []
    for cluster in clusters:
        assert repos.face_clusters.get_cluster(cluster.id).member_count == 0
    # 空簇的有效决策迁为 unassigned（决策行保留，不物理删除）
    for cluster, person in zip(clusters, (person_a, person_b)):
        latest = repos.cluster_assignments.list_latest_decision(cluster.id)
        assert latest is not None
        assert latest.status == "unassigned"
        assert latest.person_id == person.id  # 历史行保留
    # 其它运行的快照行一并级联消失
    assert repos.recognition_runs.list_run_photos(run2.id) == []


def test_delete_run_photos_purge_removes_generations_and_decisions(
    tmp_path: Path,
) -> None:
    """B2：同时清理聚类代际 → 簇与决策行级联删除。"""
    repos, run1, _run2, _photos, clusters, person_a, _person_b = _world(
        tmp_path, with_samples=False,
    )
    service = _photos_service(repos)

    result = service.execute(DeleteRunPhotosCommand(
        run_id=run1.id, purge_cluster_generations=True,
    ))

    assert result.generations_purged == 1
    assert result.clusters_recounted == 0  # purge 模式不做计数回写
    assert result.unassigned_decisions == 0
    assert repos.face_clusters.list_cluster_runs(run1.id) == []
    for cluster in clusters:
        assert repos.face_clusters.get_cluster(cluster.id) is None
        assert repos.cluster_assignments.list_by_cluster(cluster.id) == []
    assert repos.cluster_assignments.count_by_person(person_a.id) == 0


def test_delete_run_photos_blocked_by_archive_record(tmp_path: Path) -> None:
    """D5 硬阻断：目标照片存在归档记录 → 拒绝执行且零副作用。"""
    repos, run1, _run2, photos, _clusters, _a, _b = _world(
        tmp_path, with_samples=False,
    )
    repos.archive_records.add(ArchiveRecord(
        photo_id=photos[0].id,
        target_archive_root="E:/archive",
        target_person_name="人员甲",
        target_event_or_date="2026-01-01",
        target_original_name="photo_0.jpg",
        status=ArchiveStatus.ARCHIVED,
    ))
    service = _photos_service(repos)

    preview = service.preview(run1.id)
    assert preview.is_blocked is True
    with pytest.raises(ValidationError):
        service.execute(DeleteRunPhotosCommand(run_id=run1.id))
    assert repos.photos.find_by_id(photos[0].id) is not None  # 零副作用


def test_delete_run_photos_unknown_run_rejected(tmp_path: Path) -> None:
    """不存在的运行 → 明确报错（不静默 no-op）。"""
    repos, *_ = _world(tmp_path)
    service = _photos_service(repos)
    with pytest.raises(ValidationError):
        service.execute(DeleteRunPhotosCommand(run_id=uuid4()))


# ── A：删除运行名单 ──────────────────────────────────────────────────────


def test_delete_run_people_removes_people_and_cascades_decisions(
    tmp_path: Path,
) -> None:
    """A3：人员删除 → 决策行级联、识别/归档/GT 归属置空（行保留）。"""
    repos, run1, _run2, photos, clusters, person_a, person_b = _world(
        tmp_path, with_samples=False,
    )
    service = _people_service(repos)

    preview = service.preview(run1.id)
    assert preview.run_found is True
    assert preview.person_count == 2
    assert preview.assignment_count == 2
    assert preview.sample_count == 0
    assert preview.recognition_count == 2
    assert preview.is_blocked is False

    result = service.execute(DeleteRunPeopleCommand(
        run_id=run1.id, mode=RUN_PEOPLE_MODE_DELETE,
    ))

    assert result.removed == 2
    assert result.missing == 0
    assert result.assignment_cascade == 2
    assert result.sample_cascade == 0
    # 人员消失，决策行级联消失
    assert repos.people.find_by_id(person_a.id) is None
    assert repos.people.find_by_id(person_b.id) is None
    assert repos.cluster_assignments.count_by_person(person_a.id) == 0
    assert repos.cluster_assignments.count_by_person(person_b.id) == 0
    # 照片、观测、成员、代际全部保留（D2：人员是归属维度）
    for photo in photos:
        assert repos.photos.find_by_id(photo.id) is not None
    for cluster in clusters:
        assert repos.face_clusters.get_cluster(cluster.id) is not None
    # 识别记录行保留但归属置空
    remaining = repos.recognition.list_by_photo_ids([p.id for p in photos])
    assert len(remaining) == 2
    assert all(row.person_id is None for row in remaining)


def test_delete_run_people_unassign_keeps_people_and_records(
    tmp_path: Path,
) -> None:
    """A1：仅解除匹配 → 人员与记录保留，有效行迁为 unassigned。"""
    repos, run1, _run2, photos, clusters, person_a, _person_b = _world(
        tmp_path, with_samples=False,
    )
    service = _people_service(repos, with_pairing=True)

    result = service.execute(DeleteRunPeopleCommand(
        run_id=run1.id, mode=RUN_PEOPLE_MODE_UNASSIGN,
    ))

    assert result.unassigned == 2
    assert result.removed == 0
    # 人员保留
    assert repos.people.find_by_id(person_a.id) is not None
    # 有效行迁为 unassigned（决策行保留，不物理删除）
    for cluster in clusters:
        latest = repos.cluster_assignments.list_latest_decision(cluster.id)
        assert latest is not None
        assert latest.status == "unassigned"
    # 照片与识别记录保留
    for photo in photos:
        assert repos.photos.find_by_id(photo.id) is not None
    assert len(repos.recognition.list_by_photo_ids([p.id for p in photos])) == 2


def test_delete_run_people_blocked_by_ground_truth(tmp_path: Path) -> None:
    """D5 硬阻断：GT 裁定引用该批人员 → 拒绝执行且零副作用。"""
    repos, run1, _run2, _photos, clusters, person_a, _person_b = _world(tmp_path)
    repos.calibration_annotations.add_ground_truth(CalibrationGroundTruth(
        cluster_id=clusters[0].id,
        verdict="person",
        resolution="expert",
        source_annotation_ids=(uuid4(),),
        annotator_count=1,
        person_id=person_a.id,
    ))
    service = _people_service(repos)

    preview = service.preview(run1.id)
    assert preview.is_blocked is True
    assert preview.ground_truth_count == 1
    with pytest.raises(ValidationError):
        service.execute(DeleteRunPeopleCommand(run_id=run1.id))
    assert repos.people.find_by_id(person_a.id) is not None  # 零副作用


def test_delete_run_people_blocked_by_samples(tmp_path: Path) -> None:
    """D5 硬阻断：样本库非空 → 拒绝执行且零副作用。"""
    repos, run1, _run2, _photos, _clusters, person_a, _person_b = _world(tmp_path)
    service = _people_service(repos)

    preview = service.preview(run1.id)
    assert preview.is_blocked is True
    assert preview.sample_count == 2
    with pytest.raises(ValidationError):
        service.execute(DeleteRunPeopleCommand(run_id=run1.id))
    assert repos.people.find_by_id(person_a.id) is not None  # 零副作用


def test_delete_run_photos_blocked_by_samples(tmp_path: Path) -> None:
    """D5 硬阻断：观测沉淀的样本随照片级联消失 → 拒绝执行。"""
    repos, run1, _run2, photos, *_ = _world(tmp_path)
    service = _photos_service(repos)

    preview = service.preview(run1.id)
    assert preview.is_blocked is True
    assert preview.sample_count == 2
    with pytest.raises(ValidationError):
        service.execute(DeleteRunPhotosCommand(run_id=run1.id))
    assert repos.photos.find_by_id(photos[0].id) is not None  # 零副作用


def test_delete_run_people_unknown_run_rejected(tmp_path: Path) -> None:
    """不存在的运行 → 明确报错（不静默 no-op）。"""
    repos, *_ = _world(tmp_path)
    service = _people_service(repos)
    with pytest.raises(ValidationError):
        service.execute(DeleteRunPeopleCommand(run_id=uuid4()))


def test_delete_run_people_unknown_mode_rejected(tmp_path: Path) -> None:
    """未知 mode → ValidationError（契约防误用）。"""
    repos, run1, *_ = _world(tmp_path)
    service = _people_service(repos)
    with pytest.raises(ValidationError):
        service.execute(DeleteRunPeopleCommand(run_id=run1.id, mode="bogus"))


# ── 辅助 ────────────────────────────────────────────────────────────────


def _observations_of(repos, run) -> list:
    return repos.face_observations.list_by_run(run.id)


def _cluster_run_id(repos, run):
    return repos.face_clusters.list_cluster_runs(run.id)[0].id


# ── C：删除运行记录（功能 C，追加轮 21）─────────────────────────────────


def test_delete_run_photos_combined_removes_photos_and_record(
    tmp_path: Path,
) -> None:
    """追加轮 22：B+C 合并命令——照片级联+代际清理+运行行删除单事务完成。"""
    repos, run1, run2, photos, _clusters, _person_a, _person_b = _world(
        tmp_path, with_samples=False,
    )
    result = _photos_service(repos).execute(DeleteRunPhotosCommand(
        run_id=run1.id,
        purge_cluster_generations=False,  # 显式 False——delete_run_record 隐含
        delete_run_record=True,
    ))
    assert result.removed == 2
    assert result.generations_purged == 1
    assert result.run_removed == 1
    assert repos.recognition_runs.get_run(run1.id) is None
    assert repos.face_clusters.list_cluster_runs(run1.id) == []
    assert repos.face_observations.list_by_run(run1.id) == []
    assert repos.recognition_runs.get_run(run2.id) is not None
    assert repos.photos.find_by_id(photos[1].id) is None


def test_delete_run_record_blocked_while_photos_registered(tmp_path: Path) -> None:
    """照片仍在登记 → 硬阻断（照片有专门的披露级联入口），执行零副作用。"""
    repos, run1, _run2, _photos, _clusters, _person_a, _person_b = _world(
        tmp_path, with_samples=False,
    )
    service = _record_service(repos)

    preview = service.preview(run1.id)
    assert preview.is_blocked is True
    assert preview.photo_count == 2
    assert "删除该运行照片" in preview.blocked_reasons[0]
    with pytest.raises(ValidationError):
        service.execute(DeleteRunRecordCommand(run_id=run1.id))
    assert repos.recognition_runs.get_run(run1.id) is not None  # 零副作用


def test_delete_run_record_blocked_by_ground_truth(tmp_path: Path) -> None:
    """D5 一致：残留代际簇上有 GT 裁定 → 拒绝执行且零副作用。"""
    repos, run1, _run2, _photos, clusters, person_a, _person_b = _world(
        tmp_path, with_samples=False,
    )
    repos.calibration_annotations.add_ground_truth(CalibrationGroundTruth(
        cluster_id=clusters[0].id,
        verdict="person",
        resolution="expert",
        source_annotation_ids=(uuid4(),),
        annotator_count=1,
        person_id=person_a.id,
    ))
    service = _record_service(repos)

    preview = service.preview(run1.id)
    assert preview.is_blocked is True
    assert preview.ground_truth_count == 1
    with pytest.raises(ValidationError):
        service.execute(DeleteRunRecordCommand(run_id=run1.id))
    assert repos.recognition_runs.get_run(run1.id) is not None  # 零副作用


def test_delete_run_record_removes_run_and_residuals(tmp_path: Path) -> None:
    """A1+B 删完后的残留运行：记录清理带走代际/未指派决策/运行行。"""
    repos, run1, run2, photos, _clusters, person_a, person_b = _world(
        tmp_path, with_samples=False,
    )
    # A1（解除匹配保留人员）+ B（照片删除，B1 默认保留代际）→ 残留：
    # 空代际 + 未指派决策行 + 运行行。照片仍在 → 记录清理先被硬阻断。
    _people_service(repos, with_pairing=True).execute(DeleteRunPeopleCommand(
        run_id=run1.id, mode=RUN_PEOPLE_MODE_UNASSIGN,
    ))
    _photos_service(repos).execute(DeleteRunPhotosCommand(run_id=run1.id))
    assert repos.recognition_runs.get_run(run1.id) is not None  # 运行仍残留

    service = _record_service(repos)
    preview = service.preview(run1.id)
    assert preview.is_blocked is False
    assert preview.photo_count == 0
    assert preview.generation_count == 1
    assert preview.cluster_count == 2
    assert preview.decision_count == 2  # D6 迁为未指派的决策行（历史保留）
    assert preview.observation_count == 0  # 观测已随照片级联清空
    assert preview.snapshot_count == 0

    result = service.execute(DeleteRunRecordCommand(run_id=run1.id))
    assert result.run_removed == 1
    assert result.generations_purged == 1
    assert result.decision_cascade == 2
    assert result.observation_cascade == 0
    assert result.snapshot_cascade == 0

    assert repos.recognition_runs.get_run(run1.id) is None
    assert repos.face_clusters.list_cluster_runs(run1.id) == []
    assert repos.face_observations.list_by_run(run1.id) == []
    # 其它运行（run2）与其照片不受影响
    assert repos.recognition_runs.get_run(run2.id) is not None
    assert repos.photos.find_by_id(photos[0].id) is None  # 已随 B 删除
    assert person_a.id and person_b.id  # A1 保留人员
