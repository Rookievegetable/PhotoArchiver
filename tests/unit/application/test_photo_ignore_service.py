"""照片级忽略/恢复 — 界面优化 §3.1/§3.2/§3.3 验收测试（真实 SQLite 仓储）.

全部走真实 SQLite（``build_sqlite_repositories``，迁移含 014），覆盖：

- 忽略创建作用域状态并同步撤销**目标照片**的既有投影（同簇其他照片、
  Assignment 历史不动）；
- 作用域 = FaceClusterRun + photo_id：其他代际/照片不受影响，跨代际
  支撑的投影走 retarget 保留；
- 忽略后同簇确认终审不为被忽略照片重建投影；
- 恢复只恢复参与资格——忽略状态删除、既有被撤销投影**不**自动恢复；
- 建议生成输入排除被忽略照片的全部观测（样本匹配向量层面验证）；
- 逐项提交：跳过（非本代际成员/已忽略/未忽略）与部分成功语义；
- 持久化：跨仓储实例（应用重启模拟）状态保留；
- 单项事务边界：UoW 注入时投影撤销与状态写入同事务。
"""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from photo_archiver.application.commands.pairing import (
    AssignClusterPersonCommand,
    StartSuggestPairingsCommand,
)
from photo_archiver.application.commands.photo_ignore import (
    IgnorePhotosCommand,
    RestorePhotosCommand,
)
from photo_archiver.application.dtos.photo_ignore import (
    OUTCOME_FAILED,
    OUTCOME_IGNORED,
    OUTCOME_RESTORED,
    OUTCOME_SKIPPED,
)
from photo_archiver.application.services import (
    PhotoIgnoreService,
    SuggestPairingsService,
)
from photo_archiver.application.services.pairing_workbench_service import (
    PairingWorkbenchService,
)
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
)
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.domain import (
    FaceEmbedding,
    MatchStatus,
    Person,
    PersonFaceSample,
    Photo,
    PhotoPath,
    PhotoPathBase,
)
from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR
from photo_archiver.domain.entities.face_cluster import (
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
)
from photo_archiver.domain.entities.face_observation import FaceObservation
from photo_archiver.domain.entities.recognition_run import RecognitionRun
from photo_archiver.domain.value_objects.face_box import FaceBox
from photo_archiver.infrastructure import NumpyCosineSimilarityFactory
from photo_archiver.infrastructure.database.sqlite_photo_ignore_state_repository import (
    SQLitePhotoIgnoreStateRepository,
)
from photo_archiver.infrastructure.database.sqlite_unit_of_work import SQLiteUnitOfWork


@pytest.fixture()
def repos(tmp_path: Path):
    return build_sqlite_repositories(tmp_path / "test.db")


# ── 世界构造助手 ─────────────────────────────────────────────────────────────


def _photo(repos, file_name: str, captured: datetime) -> Photo:
    photo = Photo(
        path=PhotoPath(Path.cwd() / "photos" / file_name, base=PhotoPathBase.ABSOLUTE),
        original_name=file_name,
        captured_at=captured,
    )
    repos.photos.add(photo)
    return photo


def _observation(run_id, photo_id, index: int, vector: tuple[float, float],
                 count: int = 1) -> FaceObservation:
    return FaceObservation(
        run_id=run_id, photo_id=photo_id, face_index=index, photo_face_count=count,
        det_score=0.9, box=FaceBox(0, index * 20, 10, 10 + index * 20),
        embedding=FaceEmbedding(vector), scope_verdict="in_selected_scope",
    )


def _add_generation(repos, run: RecognitionRun, photos_vectors: list) -> tuple[
    FaceClusterRun, FaceCluster, list,
]:
    """One cluster run with one cluster; each entry is (photo, embedding).

    Returns the cluster run, the cluster and the member observation ids in
    member order（供样本种子引用真实观测 id）。
    """
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="test")
    repos.face_clusters.add_cluster_run(cluster_run)
    cluster = FaceCluster(
        cluster_run_id=cluster_run.id, run_id=run.id,
        ordinal=0, member_count=len(photos_vectors), sort_key="k|000000",
        first_captured_at=min(photo.captured_at for photo, _ in photos_vectors),
    )
    repos.face_clusters.add_clusters([cluster])
    observation_ids: list = []
    for index, (photo, vector) in enumerate(photos_vectors):
        observation = _observation(run.id, photo.id, index, vector, count=len(photos_vectors))
        repos.face_observations.add_many([observation])
        repos.face_clusters.add_members([
            FaceClusterMember(cluster_id=cluster.id, observation_id=observation.id),
        ])
        observation_ids.append(observation.id)
    cluster_run.start()
    cluster_run.complete(1, len(photos_vectors), 0)
    return cluster_run, cluster, observation_ids


def _person(repos, name: str) -> Person:
    person = Person(name=name)
    repos.people.add(person)
    return person


def _reconciler(repos) -> ProjectionReconciler:
    return ProjectionReconciler(
        recognition_repository=repos.recognition,
        assignment_repository=repos.cluster_assignments,
        cluster_repository=repos.face_clusters,
        observation_repository=repos.face_observations,
        photo_ignore_repository=repos.photo_ignore_states,
    )


def _ignore_service(repos) -> PhotoIgnoreService:
    return PhotoIgnoreService(
        repos.photo_ignore_states,
        repos.face_clusters,
        repos.face_observations,
        repos.cluster_assignments,
        reconciler=_reconciler(repos),
        unit_of_work=SQLiteUnitOfWork(repos._connection_provider),  # noqa: SLF001
    )


def _ignore_service_no_uow(repos) -> PhotoIgnoreService:
    return PhotoIgnoreService(
        repos.photo_ignore_states,
        repos.face_clusters,
        repos.face_observations,
        repos.cluster_assignments,
        reconciler=_reconciler(repos),
    )


def _workbench(repos) -> PairingWorkbenchService:
    return PairingWorkbenchService(
        repos.cluster_assignments,
        repos.face_clusters,
        repos.face_observations,
        repos.people,
        repos.recognition,
        repos.person_face_samples,
        reconciler=_reconciler(repos),
    )


def _confirmed_pair(repos, cluster, person) -> None:
    """人工终审：manual confirmed 行 + 样本沉淀 + 簇照片投影。"""
    _workbench(repos).assign_person(
        AssignClusterPersonCommand(cluster_id=cluster.id, person_id=person.id),
        actor=HUMAN_ACTOR,
    )


def _projection_status(repos, photo, person) -> MatchStatus | None:
    """Status of the Assignment-derived projection row (audit rows included).

    ``find_projection`` 只返回 APPROVED 行；终结语义（approved→rejected）
    须经 ``list_by_photo`` 扫描同一行观察。
    """
    for row in repos.recognition.list_by_photo(photo.id):
        if row.person_id == person.id and row.assignment_id is not None:
            return row.status
    return None


# ── 忽略：状态 + 目标照片投影撤销 ────────────────────────────────────────────


def test_ignore_revokes_projection_of_target_photo_only(repos):
    photo_a = _photo(repos, "a.jpg", datetime(2026, 1, 1, 8, 0, 0))
    photo_b = _photo(repos, "b.jpg", datetime(2026, 1, 1, 8, 5, 0))
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run, cluster, _observation_ids = _add_generation(repos, run, [
        (photo_a, (1.0, 0.0)), (photo_b, (1.0, 0.0)),
    ])
    person = _person(repos, "张三")
    _confirmed_pair(repos, cluster, person)
    assert _projection_status(repos, photo_a, person) is MatchStatus.APPROVED

    result = _ignore_service(repos).ignore_photos(
        IgnorePhotosCommand(cluster_run_id=cluster_run.id, photo_ids=(photo_a.id,)),
    )

    assert result.succeeded_count == 1 and result.failed_count == 0
    item = result.outcomes[0]
    assert item.outcome == OUTCOME_IGNORED and item.photo_id == photo_a.id
    assert item.revoked_projections == 1
    # 目标照片投影终结（approved → rejected，审计行保留，物理行仍在）。
    assert _projection_status(repos, photo_a, person) is MatchStatus.REJECTED
    audit_rows = [
        row for row in repos.recognition.list_by_photo(photo_a.id)
        if row.person_id == person.id and row.assignment_id is not None
    ]
    assert len(audit_rows) == 1 and audit_rows[0].status is MatchStatus.REJECTED
    # 同簇其他照片投影不受影响。
    assert _projection_status(repos, photo_b, person) is MatchStatus.APPROVED
    # Assignment 决策历史不被改写（仍是 confirmed）。
    latest = repos.cluster_assignments.list_latest_decision(cluster.id)
    assert latest.status == "confirmed" and latest.person_id == person.id
    # 忽略状态落库于本代际作用域。
    assert repos.photo_ignore_states.list_photo_ids(cluster_run.id) == (photo_a.id,)


def test_ignore_scope_is_cluster_run_other_generation_unaffected(repos):
    photo_a = _photo(repos, "a.jpg", datetime(2026, 1, 1, 8, 0, 0))
    photo_b = _photo(repos, "b.jpg", datetime(2026, 1, 1, 8, 5, 0))
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    first_run, first_cluster, _ = _add_generation(repos, run, [
        (photo_a, (1.0, 0.0)), (photo_b, (1.0, 0.0)),
    ])
    person = _person(repos, "张三")
    _confirmed_pair(repos, first_cluster, person)
    # 第二代际：同 recognition run 重聚类，仅含 photo_a（外部支撑来源）。
    second_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="test")
    repos.face_clusters.add_cluster_run(second_run)
    second_cluster = FaceCluster(
        cluster_run_id=second_run.id, run_id=run.id,
        ordinal=0, member_count=1, sort_key="k|000001",
        first_captured_at=photo_a.captured_at,
    )
    repos.face_clusters.add_clusters([second_cluster])
    observation = _observation(run.id, photo_a.id, 1, (1.0, 0.0), count=2)
    repos.face_observations.add_many([observation])
    repos.face_clusters.add_members([
        FaceClusterMember(cluster_id=second_cluster.id, observation_id=observation.id),
    ])
    second_run.start()
    second_run.complete(1, 1, 0)
    _confirmed_pair(repos, second_cluster, person)
    # 确认后的支撑排序：最早确认优先——投影当前指向第一代际的决策行。
    assert repos.recognition.find_projection(
        photo_a.id, person.id,
    ).assignment_id == repos.cluster_assignments.list_latest_decision(
        first_cluster.id,
    ).id

    _ignore_service(repos).ignore_photos(
        IgnorePhotosCommand(cluster_run_id=first_run.id, photo_ids=(photo_a.id,)),
    )

    # 第一代际忽略 photo_a：其支撑失效，但第二代际支撑仍在 → 投影 retarget 保留。
    assert _projection_status(repos, photo_a, person) is MatchStatus.APPROVED
    projection = repos.recognition.find_projection(photo_a.id, person.id)
    assert projection.assignment_id == repos.cluster_assignments.list_latest_decision(
        second_cluster.id,
    ).id
    # 忽略状态只存在于第一代际。
    assert repos.photo_ignore_states.list_photo_ids(second_run.id) == ()
    # 同簇其他照片不受影响。
    assert _projection_status(repos, photo_b, person) is MatchStatus.APPROVED


def test_ignore_then_confirm_does_not_recreate_projection_for_ignored_photo(repos):
    """忽略后同簇的确认终审不得为被忽略照片重建投影（§3.2.2/§3.2.6）。"""
    photo_a = _photo(repos, "a.jpg", datetime(2026, 1, 1, 8, 0, 0))
    photo_b = _photo(repos, "b.jpg", datetime(2026, 1, 1, 8, 5, 0))
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run, cluster, _observation_ids = _add_generation(repos, run, [
        (photo_a, (1.0, 0.0)), (photo_b, (1.0, 0.0)),
    ])
    _ignore_service(repos).ignore_photos(
        IgnorePhotosCommand(cluster_run_id=cluster_run.id, photo_ids=(photo_a.id,)),
    )
    person = _person(repos, "李四")
    _confirmed_pair(repos, cluster, person)
    assert _projection_status(repos, photo_a, person) is None
    assert _projection_status(repos, photo_b, person) is MatchStatus.APPROVED


def test_ignore_persists_across_repository_instances(repos):
    """跨重启持久化：新仓储实例（同一数据库）读取既有状态。"""
    photo_a = _photo(repos, "a.jpg", datetime(2026, 1, 1, 8, 0, 0))
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run, _, _observation_ids = _add_generation(repos, run, [(photo_a, (1.0, 0.0))])
    _ignore_service(repos).ignore_photos(
        IgnorePhotosCommand(cluster_run_id=cluster_run.id, photo_ids=(photo_a.id,)),
    )
    reopened = SQLitePhotoIgnoreStateRepository(repos._connection_provider)  # noqa: SLF001
    assert reopened.find(cluster_run.id, photo_a.id) is not None
    assert reopened.list_photo_ids(cluster_run.id) == (photo_a.id,)


def test_multi_cluster_photo_revokes_each_persons_projection(repos):
    """同一照片的多张脸落入同代际两个簇且分别确认：两份投影都被处理（§3.2.6）。"""
    photo = _photo(repos, "group.jpg", datetime(2026, 1, 1, 8, 0, 0))
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="test")
    repos.face_clusters.add_cluster_run(cluster_run)
    clusters = []
    for ordinal in range(2):
        cluster = FaceCluster(
            cluster_run_id=cluster_run.id, run_id=run.id,
            ordinal=ordinal, member_count=1, sort_key=f"k|{ordinal:06d}",
            first_captured_at=photo.captured_at,
        )
        repos.face_clusters.add_clusters([cluster])
        observation = _observation(run.id, photo.id, ordinal, (1.0, 0.0), count=2)
        repos.face_observations.add_many([observation])
        repos.face_clusters.add_members([
            FaceClusterMember(cluster_id=cluster.id, observation_id=observation.id),
        ])
        clusters.append(cluster)
    cluster_run.start()
    cluster_run.complete(2, 2, 0)
    person_a = _person(repos, "甲")
    person_b = _person(repos, "乙")
    _confirmed_pair(repos, clusters[0], person_a)
    _confirmed_pair(repos, clusters[1], person_b)
    assert _projection_status(repos, photo, person_a) is MatchStatus.APPROVED
    assert _projection_status(repos, photo, person_b) is MatchStatus.APPROVED

    result = _ignore_service(repos).ignore_photos(
        IgnorePhotosCommand(cluster_run_id=cluster_run.id, photo_ids=(photo.id,)),
    )

    assert result.revoked_projections == 2
    assert _projection_status(repos, photo, person_a) is MatchStatus.REJECTED
    assert _projection_status(repos, photo, person_b) is MatchStatus.REJECTED


# ── 恢复：只恢复参与资格，不回溯投影 ────────────────────────────────────────


def test_restore_removes_state_but_not_revoked_projection(repos):
    photo_a = _photo(repos, "a.jpg", datetime(2026, 1, 1, 8, 0, 0))
    photo_b = _photo(repos, "b.jpg", datetime(2026, 1, 1, 8, 5, 0))
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run, cluster, _observation_ids = _add_generation(repos, run, [
        (photo_a, (1.0, 0.0)), (photo_b, (1.0, 0.0)),
    ])
    person = _person(repos, "张三")
    _confirmed_pair(repos, cluster, person)
    _ignore_service(repos).ignore_photos(
        IgnorePhotosCommand(cluster_run_id=cluster_run.id, photo_ids=(photo_a.id,)),
    )
    assert _projection_status(repos, photo_a, person) is MatchStatus.REJECTED

    result = _ignore_service(repos).restore_photos(
        RestorePhotosCommand(cluster_run_id=cluster_run.id, photo_ids=(photo_a.id,)),
    )

    assert result.outcomes[0].outcome == OUTCOME_RESTORED
    assert result.outcomes[0].revoked_projections == 0
    assert repos.photo_ignore_states.find(cluster_run.id, photo_a.id) is None
    # 恢复不自动恢复此前撤销的投影（§3.2.7）。
    assert _projection_status(repos, photo_a, person) is MatchStatus.REJECTED
    # 同簇其他照片不受影响。
    assert _projection_status(repos, photo_b, person) is MatchStatus.APPROVED


# ── 逐项语义：跳过与部分成功 ────────────────────────────────────────────────


def test_ignore_skips_non_member_and_duplicate_items(repos):
    photo_a = _photo(repos, "a.jpg", datetime(2026, 1, 1, 8, 0, 0))
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run, _, _observation_ids = _add_generation(repos, run, [(photo_a, (1.0, 0.0))])
    foreign = _photo(repos, "elsewhere.jpg", datetime(2026, 1, 2, 8, 0, 0))
    service = _ignore_service(repos)

    result = service.ignore_photos(IgnorePhotosCommand(
        cluster_run_id=cluster_run.id, photo_ids=(photo_a.id, foreign.id),
    ))
    # 第二项继续处理（部分成功），逐项报告。
    assert [item.outcome for item in result.outcomes] == [
        OUTCOME_IGNORED, OUTCOME_SKIPPED,
    ]
    assert result.skipped_count == 1

    again = service.ignore_photos(IgnorePhotosCommand(
        cluster_run_id=cluster_run.id, photo_ids=(photo_a.id,),
    ))
    assert again.outcomes[0].outcome == OUTCOME_SKIPPED
    assert "already ignored" in again.outcomes[0].reason


def test_restore_skips_when_not_ignored(repos):
    photo_a = _photo(repos, "a.jpg", datetime(2026, 1, 1, 8, 0, 0))
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run, _, _observation_ids = _add_generation(repos, run, [(photo_a, (1.0, 0.0))])
    result = _ignore_service(repos).restore_photos(
        RestorePhotosCommand(cluster_run_id=cluster_run.id, photo_ids=(photo_a.id,)),
    )
    assert result.outcomes[0].outcome == OUTCOME_SKIPPED
    assert result.outcomes[0].reason == "not ignored"


def test_unknown_cluster_run_fails_item(repos):
    """未知代际按项失败并携带原因，不影响其他项（逐项提交语义）。"""
    photo_a = _photo(repos, "a.jpg", datetime(2026, 1, 1, 8, 0, 0))
    result = _ignore_service_no_uow(repos).ignore_photos(
        IgnorePhotosCommand(cluster_run_id=uuid4(), photo_ids=(photo_a.id,)),
    )
    assert result.outcomes[0].outcome == OUTCOME_FAILED
    assert result.outcomes[0].reason is not None


# ── 建议生成输入排除（§3.1） ────────────────────────────────────────────────


def test_suggestion_input_excludes_ignored_photo_observations(repos):
    """被忽略照片的观测不进入样本匹配向量：忽略前命中、忽略后不命中。"""
    photo_a = _photo(repos, "a.jpg", datetime(2026, 1, 1, 8, 0, 0))
    photo_b = _photo(repos, "b.jpg", datetime(2026, 1, 1, 8, 5, 0))
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run, cluster, observation_ids = _add_generation(repos, run, [
        (photo_a, (1.0, 0.0)), (photo_b, (0.0, 1.0)),
    ])
    person = _person(repos, "王五")
    repos.person_face_samples.add_samples([
        PersonFaceSample(
            person_id=person.id,
            observation_id=observation_ids[0],
            embedding=FaceEmbedding((1.0, 0.0)),
        ),
    ])
    suggest = SuggestPairingsService(
        repos.face_clusters,
        repos.face_observations,
        repos.people,
        repos.cluster_assignments,
        repos.person_face_samples,
        NumpyCosineSimilarityFactory(),
        photo_ignore_repository=repos.photo_ignore_states,
    )

    summary_before = suggest.execute(StartSuggestPairingsCommand(cluster_run.id))
    assert summary_before.sample_matched == 1

    # 清掉第一轮建议行，忽略 photo_a 后再生成：其观测被排除，
    # 剩余向量（正交）不再命中样本匹配。
    with repos._connection_provider.connect() as connection:  # noqa: SLF001
        connection.execute("DELETE FROM cluster_person_assignments")
    _ignore_service(repos).ignore_photos(
        IgnorePhotosCommand(cluster_run_id=cluster_run.id, photo_ids=(photo_a.id,)),
    )
    summary_after = suggest.execute(StartSuggestPairingsCommand(cluster_run.id))
    assert summary_after.sample_matched == 0
