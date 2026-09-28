"""AUD-017 Option C closed loop over REAL SQLite（Stage 11B，任务书 §14 硬要求）.

证明链（全部真实仓储、真实 numpy kernel，零 stub）：

    真实数据库（build_sqlite_repositories）
    → 真实候选仓储（SQLitePersonFaceSampleRepository.list_enabled，enabled=1）
    → 真实相似度 kernel（NumpyCosineSimilarityFactory，量化 6 位）
    → 真实建议（suggest_pairings 规则① sample_match / 规则③ ordered_suggestion，
      全部落 suggested 层——K-3：绝不直接形成身份确认、不触碰兼容链）
    → 人工确认（PairingWorkbenchService.confirm）
    → 样本沉淀（person_face_embeddings，幂等）+ (person, photo) 兼容投影

冷启动（场景 A：零样本 → 仅 ordered_suggestion）与样本路径（场景 B：部分人有
样本 → sample_match 优先、无样本者仍走冷启动）双路径并存；disabled 样本不参与
候选；平分按确定性顺序 tie-break；维度不一致 fail-closed。
"""

from datetime import datetime
from pathlib import Path

import pytest

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands.pairing import (
    ConfirmAssignmentCommand,
    StartSuggestPairingsCommand,
    UnassignClusterCommand,
)
from photo_archiver.application.services import (
    PairingWorkbenchService,
    SuggestPairingsService,
)
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
    RunPhotoSnapshot,
)
from photo_archiver.domain.entities.face_cluster import CLUSTER_RUN_STATUS_COMPLETED
from photo_archiver.domain.entities.face_observation import (
    SCOPE_VERDICT_IN_SELECTED_SCOPE,
)
from photo_archiver.infrastructure.cosine_kernel import NumpyCosineSimilarityFactory


ALGORITHM = "aud017-integration-test"


def _photo(repos, name: str, captured: datetime) -> Photo:
    photo = Photo(
        path=PhotoPath(Path.cwd() / "src" / name, base=PhotoPathBase.ABSOLUTE),
        original_name=name,
        captured_at=captured,
    )
    repos.photos.add(photo)
    return photo


def _observation(run_id, photo_id, face_index, photo_face_count, vector):
    return FaceObservation(
        run_id=run_id,
        photo_id=photo_id,
        face_index=face_index,
        photo_face_count=photo_face_count,
        det_score=0.9,
        box=FaceBox(x1=0, y1=0, x2=10, y2=10),
        embedding=FaceEmbedding(vector=tuple(vector)),
        scope_verdict=SCOPE_VERDICT_IN_SELECTED_SCOPE,
    )


def _seed_run_and_observations(repos, photos_and_faces):
    """photos_and_faces: [(photo, [vector, ...]), ...] → (run, cluster_run, observations)."""
    run = RecognitionRun(parameters={})
    repos.recognition_runs.add_run(run)
    repos.recognition_runs.add_run_photos(run.id, [
        RunPhotoSnapshot(run.id, photo.id, photo.original_name or "x.jpg")
        for photo, _ in photos_and_faces
    ])
    observations = []
    for photo, vectors in photos_and_faces:
        for face_index, vector in enumerate(vectors):
            observations.append(_observation(
                run.id, photo.id, face_index, len(vectors), vector,
            ))
    repos.face_observations.add_many(observations)
    cluster_run = FaceClusterRun(
        recognition_run_id=run.id,
        algorithm_version=ALGORITHM,
        status=CLUSTER_RUN_STATUS_COMPLETED,
    )
    repos.face_clusters.add_cluster_run(cluster_run)
    return run, cluster_run


def _seed_cluster(repos, cluster_run, ordinal, sort_key, member_observations, captured):
    cluster = FaceCluster(
        cluster_run_id=cluster_run.id,
        run_id=cluster_run.recognition_run_id,
        ordinal=ordinal,
        member_count=len(member_observations),
        sort_key=sort_key,
        first_captured_at=captured,
    )
    repos.face_clusters.add_clusters([cluster])
    repos.face_clusters.add_members([
        FaceClusterMember(cluster_id=cluster.id, observation_id=observation.id)
        for observation in member_observations
    ])
    return cluster


def _suggested(repos, cluster):
    rows = [
        row for row in repos.cluster_assignments.list_by_cluster(cluster.id)
        if row.status == "suggested"
    ]
    assert len(rows) == 1, f"expected exactly one suggested row, got {rows}"
    return rows[0]


def test_sample_suggestion_closed_loop_with_disabled_exclusion_idempotent_confirm(tmp_path):
    """主闭环：enabled 样本 → sample_match 建议 → 人工确认 → 样本沉淀；

    disabled 样本不参与候选（更高分被排除）；K-3：建议本身零兼容写入，
    兼容 (person, photo) 行只经人工确认产生；解除→重建议→重复确认幂等。
    """
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    person_a = Person(name="张伟", roster_order=1)
    person_b = Person(name="李四", roster_order=2)
    person_c = Person(name="王五", roster_order=3)
    for person in (person_a, person_b, person_c):
        repos.people.add(person)

    p0 = _photo(repos, "pool.jpg", datetime(2026, 1, 1))    # 样本池照片（2 脸，不入簇）
    p1 = _photo(repos, "f1.jpg", datetime(2026, 1, 2))      # 簇 1 成员
    p2 = _photo(repos, "f3.jpg", datetime(2026, 2, 1))      # 簇 2 成员
    run, cluster_run = _seed_run_and_observations(repos, [
        (p0, [(0.6, 0.8, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)]),
        (p1, [(1.0, 0.0, 0.0, 0.0)]),
        (p2, [(0.0, 0.0, 1.0, 0.0)]),
    ])
    observations = repos.face_observations.list_by_run(run.id)
    o_pool_enabled = next(o for o in observations if o.photo_id == p0.id and o.face_index == 0)
    o_pool_disabled = next(o for o in observations if o.photo_id == p0.id and o.face_index == 1)
    o_f1 = next(o for o in observations if o.photo_id == p1.id)
    o_f3 = next(o for o in observations if o.photo_id == p2.id)

    cluster1 = _seed_cluster(
        repos, cluster_run, 0, "2026-01-02", [o_f1], datetime(2026, 1, 2),
    )
    cluster2 = _seed_cluster(
        repos, cluster_run, 1, "2026-02-01", [o_f3], datetime(2026, 2, 1),
    )
    # 张伟：enabled 样本对簇 1 余弦恰 0.6；disabled 样本若参与会把分数抬到 1.0。
    repos.person_face_samples.add_samples([
        PersonFaceSample(
            person_id=person_a.id, observation_id=o_pool_enabled.id,
            embedding=FaceEmbedding(vector=(0.6, 0.8, 0.0, 0.0)), enabled=True,
        ),
        PersonFaceSample(
            person_id=person_a.id, observation_id=o_pool_disabled.id,
            embedding=FaceEmbedding(vector=(1.0, 0.0, 0.0, 0.0)), enabled=False,
        ),
    ])

    suggest = SuggestPairingsService(
        repos.face_clusters, repos.face_observations, repos.people,
        repos.cluster_assignments, repos.person_face_samples,
        NumpyCosineSimilarityFactory(),
    )
    workbench = PairingWorkbenchService(
        repos.cluster_assignments, repos.face_clusters, repos.face_observations,
        repos.people, repos.recognition, repos.person_face_samples,
    )

    # ── 建议生成：双路径并存，disabled 被排除 ────────────────────────────
    summary = suggest.execute(StartSuggestPairingsCommand(cluster_run_id=cluster_run.id))
    assert (summary.suggestions, summary.sample_matched, summary.ordered) == (2, 1, 1)

    row1 = _suggested(repos, cluster1)
    assert row1.source == "sample_match"
    assert row1.person_id == person_a.id
    assert row1.score == pytest.approx(0.6, abs=1e-9)   # disabled 1.0 样本未参与

    row2 = _suggested(repos, cluster2)
    assert row2.source == "ordered_suggestion"          # 李四无样本 → 冷启动位次建议
    assert row2.person_id == person_b.id
    assert row2.score is None                            # 位次不是相似度证据

    # ── K-3：建议层零兼容写入、零身份确认 ───────────────────────────────
    counts = repos.recognition.read_workspace_counts()
    assert counts.pending_review_count == 0              # 兼容链未被样本匹配触碰
    assert counts.archivable_count == 0                  # 无人被自动确认
    all_rows = (
        repos.cluster_assignments.list_by_cluster(cluster1.id)
        + repos.cluster_assignments.list_by_cluster(cluster2.id)
    )
    assert all(row.status == "suggested" for row in all_rows)

    # ── 人工确认（sample_match 建议）→ 身份确认 + 样本沉淀 ──────────────
    result = workbench.confirm(ConfirmAssignmentCommand(assignment_id=row1.id))
    assert result.status == "confirmed"
    assert result.samples_written == 1                   # o_f1 沉淀为张伟样本
    assert result.compat_results_written == 1            # (张伟, f1.jpg) APPROVED 投影
    assert len(repos.person_face_samples.list_by_person(person_a.id)) == 3
    counts = repos.recognition.read_workspace_counts()
    assert counts.archivable_count == 1                  # 兼容归属只来自人工确认

    # ── 解除 → 重建议 → 重复确认：样本幂等，不制造重复沉淀 ──────────────
    workbench.unassign(UnassignClusterCommand(cluster_id=cluster1.id))
    assert len(repos.person_face_samples.list_by_person(person_a.id)) == 3  # 停用保留

    summary2 = suggest.execute(StartSuggestPairingsCommand(cluster_run_id=cluster_run.id))
    assert (summary2.suggestions, summary2.sample_matched, summary2.ordered) == (1, 1, 0)
    row_re = _suggested(repos, cluster1)
    assert row_re.source == "sample_match"

    result2 = workbench.confirm(ConfirmAssignmentCommand(assignment_id=row_re.id))
    assert result2.samples_written == 0                  # 观测已沉淀 → 零新增
    assert result2.compat_results_written == 1           # 兼容行按 (person, photo) 幂等重投影
    assert len(repos.person_face_samples.list_by_person(person_a.id)) == 3


def test_zero_samples_cold_start_yields_only_ordered_suggestions(tmp_path):
    """场景 A：完全无样本 → 仅冷启动 ordered_suggestion，无任何 similarity_suggestion。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    person_a = Person(name="张伟", roster_order=1)
    person_b = Person(name="李四", roster_order=2)
    person_c = Person(name="王五", roster_order=3)
    for person in (person_a, person_b, person_c):
        repos.people.add(person)

    p1 = _photo(repos, "f1.jpg", datetime(2026, 1, 2))
    p2 = _photo(repos, "f3.jpg", datetime(2026, 2, 1))
    run, cluster_run = _seed_run_and_observations(repos, [
        (p1, [(1.0, 0.0, 0.0, 0.0)]),
        (p2, [(0.0, 0.0, 1.0, 0.0)]),
    ])
    observations = repos.face_observations.list_by_run(run.id)
    o_f1 = next(o for o in observations if o.photo_id == p1.id)
    o_f3 = next(o for o in observations if o.photo_id == p2.id)
    cluster1 = _seed_cluster(repos, cluster_run, 0, "2026-01-02", [o_f1], datetime(2026, 1, 2))
    cluster2 = _seed_cluster(repos, cluster_run, 1, "2026-02-01", [o_f3], datetime(2026, 2, 1))

    summary = SuggestPairingsService(
        repos.face_clusters, repos.face_observations, repos.people,
        repos.cluster_assignments, repos.person_face_samples,
        NumpyCosineSimilarityFactory(),
    ).execute(StartSuggestPairingsCommand(cluster_run_id=cluster_run.id))

    assert (summary.suggestions, summary.sample_matched, summary.ordered) == (2, 0, 2)
    assert _suggested(repos, cluster1).person_id == person_a.id   # roster 首位
    assert _suggested(repos, cluster2).person_id == person_b.id
    assert summary.persons_without_cluster == 1                   # 王五无簇，不强配


def test_equal_score_tie_breaks_to_deterministic_sample_order(tmp_path):
    """场景 B 平分：两人样本同分 → 按候选序（person_id 序）确定性取首位。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    person_a = Person(name="甲", roster_order=1)
    person_b = Person(name="乙", roster_order=2)
    for person in (person_a, person_b):
        repos.people.add(person)

    p0 = _photo(repos, "pool.jpg", datetime(2026, 1, 1))
    p1 = _photo(repos, "f1.jpg", datetime(2026, 1, 2))
    run, cluster_run = _seed_run_and_observations(repos, [
        (p0, [(1.0, 0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)]),
        (p1, [(1.0, 0.0, 0.0, 0.0)]),
    ])
    observations = repos.face_observations.list_by_run(run.id)
    o_a = next(o for o in observations if o.photo_id == p0.id and o.face_index == 0)
    o_b = next(o for o in observations if o.photo_id == p0.id and o.face_index == 1)
    o_c = next(o for o in observations if o.photo_id == p1.id)
    cluster1 = _seed_cluster(repos, cluster_run, 0, "2026-01-02", [o_c], datetime(2026, 1, 2))
    repos.person_face_samples.add_samples([
        PersonFaceSample(person_id=person_a.id, observation_id=o_a.id,
                         embedding=FaceEmbedding(vector=(1.0, 0.0, 0.0, 0.0))),
        PersonFaceSample(person_id=person_b.id, observation_id=o_b.id,
                         embedding=FaceEmbedding(vector=(1.0, 0.0, 0.0, 0.0))),
    ])

    SuggestPairingsService(
        repos.face_clusters, repos.face_observations, repos.people,
        repos.cluster_assignments, repos.person_face_samples,
        NumpyCosineSimilarityFactory(),
    ).execute(StartSuggestPairingsCommand(cluster_run_id=cluster_run.id))

    row = _suggested(repos, cluster1)
    assert row.source == "sample_match"
    assert row.score == pytest.approx(1.0)
    winner = min((person_a.id, person_b.id), key=lambda u: str(u))
    assert row.person_id == winner   # list_enabled ORDER BY person_id + 规则①严格 > 首选


def test_dimension_mismatch_fails_closed(tmp_path):
    """维度不一致 → 建议 fail-closed（不产出错误建议、不静默跳过）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    person_a = Person(name="张伟", roster_order=1)
    repos.people.add(person_a)

    p0 = _photo(repos, "pool.jpg", datetime(2026, 1, 1))
    p1 = _photo(repos, "f1.jpg", datetime(2026, 1, 2))
    run, cluster_run = _seed_run_and_observations(repos, [
        (p0, [(1.0, 0.0, 0.0)]),          # 3 维样本（异物/损坏数据形态）
        (p1, [(1.0, 0.0, 0.0, 0.0)]),     # 4 维观测
    ])
    observations = repos.face_observations.list_by_run(run.id)
    o_pool = next(o for o in observations if o.photo_id == p0.id)
    o_f1 = next(o for o in observations if o.photo_id == p1.id)
    cluster1 = _seed_cluster(repos, cluster_run, 0, "2026-01-02", [o_f1], datetime(2026, 1, 2))
    repos.person_face_samples.add_samples([
        PersonFaceSample(person_id=person_a.id, observation_id=o_pool.id,
                         embedding=FaceEmbedding(vector=(1.0, 0.0, 0.0))),
    ])

    with pytest.raises(ValueError, match="same dimension"):
        SuggestPairingsService(
            repos.face_clusters, repos.face_observations, repos.people,
            repos.cluster_assignments, repos.person_face_samples,
            NumpyCosineSimilarityFactory(),
        ).execute(StartSuggestPairingsCommand(cluster_run_id=cluster_run.id))
    assert repos.cluster_assignments.list_by_cluster(cluster1.id) == []  # 未落任何建议
