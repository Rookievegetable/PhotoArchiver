"""界面优化 P2 — 删除披露计数一致性（真实 SQLite 集成测试）.

验收锚（阶段 1 任务书 §1.1/§3.1）：``preview()`` 的 assignment/sample 计数
必须与真实外键级联结果一致——预览算出的数量 == 执行后实际消失的行数。

全部使用 tmp_path 隔离数据库；不触碰生产库。
"""

from datetime import datetime
from pathlib import Path

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands.deletion import (
    ClearAllPeopleCommand,
    DeletePersonCommand,
)
from photo_archiver.application.services import DeletePersonService
from photo_archiver.domain import (
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
    RecognitionRun,
)
from photo_archiver.domain.entities.cluster_assignment import (
    ASSIGNMENT_SOURCE_MANUAL,
    ClusterPersonAssignment,
)

_BASE = datetime(2026, 1, 1, 8, 0, 0)


def _world(tmp_path: Path):
    """一个人员 + 两张照片/两个观测/两个簇 + 两条决策行 + 两条样本。"""
    repos = build_sqlite_repositories(tmp_path / "disclosure.sqlite3")
    run = RecognitionRun(parameters={})
    repos.recognition_runs.add_run(run)

    person = Person(name="人员甲", roster_order=1)
    repos.people.add(person)

    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="v1")
    repos.face_clusters.add_cluster_run(cluster_run)

    for index in range(2):
        photo = Photo(
            path=PhotoPath(
                tmp_path / f"photo_{index}.jpg", PhotoPathBase.ABSOLUTE,
            ),
            captured_at=_BASE,
        )
        repos.photos.add(photo)
        observation = FaceObservation(
            run_id=run.id, photo_id=photo.id, face_index=0, photo_face_count=1,
            det_score=0.9, box=FaceBox(0, 0, 10, 10),
            embedding=FaceEmbedding((1.0, float(index), 0.0)),
            scope_verdict="in_selected_scope", quality_score=0.9,
        )
        repos.face_observations.add_many([observation])
        cluster = FaceCluster(
            cluster_run_id=cluster_run.id, run_id=run.id, ordinal=index,
            member_count=1, sort_key=f"k|g0{index}|000000{index}",
            first_captured_at=_BASE,
        )
        repos.face_clusters.add_clusters([cluster])
        repos.face_clusters.add_members([
            FaceClusterMember(cluster_id=cluster.id, observation_id=observation.id),
        ])
        repos.cluster_assignments.add_assignments([ClusterPersonAssignment(
            cluster_id=cluster.id, person_id=person.id,
            status="confirmed", source=ASSIGNMENT_SOURCE_MANUAL,
        )])
        repos.person_face_samples.add_samples([PersonFaceSample(
            person_id=person.id, observation_id=observation.id,
            embedding=observation.embedding, quality_score=0.9,
        )])
    return repos, person


def _service(repos, *, with_counts: bool = True) -> DeletePersonService:
    return DeletePersonService(
        repos.people, repos.photos, repos.recognition, repos.face_embeddings,
        assignment_repository=repos.cluster_assignments if with_counts else None,
        sample_repository=repos.person_face_samples if with_counts else None,
    )


def test_preview_counts_match_actual_cascade(tmp_path: Path) -> None:
    """预览计数 == 执行后实际级联消失的行数（决策行 + 样本）。"""
    repos, person = _world(tmp_path)
    service = _service(repos)

    preview = service.preview([person.id])
    assert preview.assignment_count == 2
    assert preview.sample_count == 2

    result = service.execute(DeletePersonCommand(person_ids=(person.id,)))
    assert result.removed == 1
    assert result.assignment_cascade == preview.assignment_count
    assert result.sample_cascade == preview.sample_count

    # 真实级联：两表对应该人员的行确实消失
    assert repos.cluster_assignments.count_by_person(person.id) == 0
    assert repos.person_face_samples.list_by_person(person.id) == []


def test_batch_and_clear_previews_carry_the_same_counts(tmp_path: Path) -> None:
    """批量/清空预览与单人预览同口径（三入口披露一致的数据侧）。"""
    repos, person = _world(tmp_path)
    service = _service(repos)

    clear = service.preview_clear_all()
    assert clear.assignment_count == 2
    assert clear.sample_count == 2

    result = service.execute_clear_all(ClearAllPeopleCommand())
    assert result.assignment_cascade == 2
    assert result.sample_cascade == 2
    assert repos.cluster_assignments.count_by_person(person.id) == 0
    assert repos.person_face_samples.list_by_person(person.id) == []


def test_counts_default_to_zero_without_ports(tmp_path: Path) -> None:
    """未注入计数端口时计数恒 0（旧构造兼容，不抛错）。"""
    repos, person = _world(tmp_path)
    service = _service(repos, with_counts=False)

    preview = service.preview([person.id])
    assert preview.assignment_count == 0
    assert preview.sample_count == 0
