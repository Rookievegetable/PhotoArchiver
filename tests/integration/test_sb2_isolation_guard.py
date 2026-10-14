"""S-B-2 Photo Isolation Guard acceptance tests（Guard-01…Guard-12）.

复用 S-B-1 测试基建（tests.integration.test_sb1_reference_intake）在隔离
SQLite 临时库上验证守卫化写入路径。生产库零接触。

映射：

    Guard-01 合法 Reference 经守卫路径确认        PASS
    Guard-02/03/06 评估照片/观察/簇 →             REJECT + 零写入
    Guard-04 跨 run 同照片 →                       REJECT + 零写入
    Guard-05 同字节新路径（新 photo_id）→          REJECT + 零写入（hash 二级守卫）
    Guard-07 悬挂观察 →                            REJECT + 零写入
    Guard-08 未解析 person →                       REJECT + 零写入
    Guard-09 空 embedding →                        域构造期 REJECT
    Guard-10 合法多脸参考照片 →                    PASS（整照不因多脸被拒）
    Guard-11 守卫失败零部分写入                    各拒绝测试内嵌断言
    Guard-12 评估照片上的普通业务样本 →            ALLOWED（分层证明：业务 ≠ Reference）
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from tests.integration.test_sb1_reference_intake import (
    DATASET_VERSION,
    V_C,
    V_D,
    _build_evaluation_side,
    _build_reference_side,
    _cluster,
    _evaluation_dataset_id,
    _make_image,
    _recognize,
    _workbench,
)

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application import ReferenceIntakeService
from photo_archiver.application.commands.scan_and_register_photos import (
    ScanAndRegisterPhotosCommand,
)
from photo_archiver.application.services.scan_and_register_photos_service import (
    ScanAndRegisterPhotosService,
)
from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR
from photo_archiver.domain.entities.face_cluster import (
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
)
from photo_archiver.domain.entities.face_observation import FaceObservation
from photo_archiver.domain.exceptions import (
    ReferenceIsolationViolationError,
    ValidationError,
)
from photo_archiver.domain.value_objects import FaceBox, FaceEmbedding
from photo_archiver.infrastructure import (
    LocalPhotoFileScanner,
    PillowPhotoMetadataReader,
)
from photo_archiver.infrastructure.image.content_hash_calculator import (
    ContentHashCalculator,
)


def _guard(repos) -> ReferenceIntakeService:
    return ReferenceIntakeService(
        repos.calibration_annotations,
        repos.face_clusters,
        repos.face_observations,
        repos.photos,
        ContentHashCalculator(),
        _workbench(repos),
    )


def _counts(db_path: Path) -> tuple[int, int, int]:
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    row = con.execute(
        "SELECT (SELECT COUNT(*) FROM cluster_person_assignments),"
        " (SELECT COUNT(*) FROM person_face_embeddings),"
        " (SELECT COUNT(*) FROM recognition_results WHERE status='approved')"
    ).fetchone()
    con.close()
    return row[0], row[1], row[2]


def _person_id(repos, name: str):
    for person in repos.people.list_all():
        if person.name == name:
            return person.id
    raise AssertionError(f"person {name} not found")


def _build_multi_face_reference(repos, tmp_path: Path):
    """One legit reference photo with TWO faces (V_C + V_D) -> 2 clusters."""
    ref_dir = tmp_path / "multi_face_ref"
    ref_dir.mkdir()
    _make_image(ref_dir, "group.jpg", __import__("datetime").datetime(2026, 5, 1, 12, 0, 0))
    known = {photo.id for photo in repos.photos.list_all()}
    ScanAndRegisterPhotosService(
        LocalPhotoFileScanner(),
        repos.folders,
        repos.photos,
        metadata_reader=PillowPhotoMetadataReader(),
    ).execute(ScanAndRegisterPhotosCommand(folder_path=ref_dir))
    photos = [p for p in repos.photos.list_all() if p.id not in known]
    from tests.integration.test_sb1_reference_intake import _FakeDetector

    run = _recognize(
        repos,
        _FakeDetector({"group.jpg": [(0.9, V_C), (0.9, V_D)]}),
        photos,
    )
    cluster_run = _cluster(repos, run)
    clusters = sorted(
        repos.face_clusters.list_clusters(cluster_run.id), key=lambda c: c.ordinal
    )
    return run, cluster_run, clusters


def test_guard_01_legitimate_reference_confirms_via_guarded_path(tmp_path):
    """Guard-01：合法 Reference 经 confirm_reference_cluster 正常确认并沉淀。"""
    db = tmp_path / "db.sqlite3"
    repos = build_sqlite_repositories(db)
    _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)
    dataset_id = _evaluation_dataset_id(repos)
    person_id = _person_id(repos, "张三")

    results = _guard(repos).confirm_reference_cluster(
        reference.cluster_run_id,
        {reference.cluster_ids[0]},
        person_id,
        dataset_id,
        DATASET_VERSION,
    )
    assert len(results) == 1
    assert results[0].status == "confirmed"
    samples = repos.person_face_samples.list_by_person(person_id)
    assert len(samples) >= 1
    assert all(s.enabled for s in samples)
    assignments = repos.cluster_assignments.list_active_by_cluster_run(
        reference.cluster_run_id
    )
    assert any(
        a.status == "confirmed" and a.person_id == person_id for a in assignments
    )


def test_guard_02_03_06_evaluation_cluster_rejected_zero_writes(tmp_path):
    """Guard-02/03/06：评估照片/观察/簇经守卫路径 → REJECT 且零写入。"""
    db = tmp_path / "db.sqlite3"
    repos = build_sqlite_repositories(db)
    evaluation = _build_evaluation_side(repos, tmp_path)
    dataset_id = _evaluation_dataset_id(repos)
    before = _counts(db)
    person_id = _person_id(repos, "张三")

    with pytest.raises(ReferenceIsolationViolationError, match="evaluation cluster"):
        _guard(repos).confirm_reference_cluster(
            evaluation.cluster_run_id,
            {evaluation.cluster_ids[0]},
            person_id,
            dataset_id,
            DATASET_VERSION,
        )
    assert _counts(db) == before


def test_guard_04_cross_run_same_photo_rejected_via_guarded_path(tmp_path):
    """Guard-04：同 photo_id 经另一 run 的 observation 不能绕过守卫路径。"""
    db = tmp_path / "db.sqlite3"
    repos = build_sqlite_repositories(db)
    evaluation = _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)
    dataset_id = _evaluation_dataset_id(repos)
    before = _counts(db)

    smuggled = FaceObservation(
        run_id=reference.run_id,
        photo_id=evaluation.photo_ids[0],
        face_index=0,
        photo_face_count=1,
        det_score=0.9,
        box=FaceBox(x1=0, y1=0, x2=8, y2=8, confidence=0.9),
        embedding=FaceEmbedding(vector=V_D),
        scope_verdict="in_selected_scope",
    )
    repos.face_observations.add_many([smuggled])
    smuggled_run = FaceClusterRun(
        recognition_run_id=reference.run_id, algorithm_version="test"
    )
    repos.face_clusters.add_cluster_run(smuggled_run)
    cluster = FaceCluster(
        cluster_run_id=smuggled_run.id,
        run_id=reference.run_id,
        ordinal=0,
        member_count=1,
        sort_key="~|~|0",
    )
    repos.face_clusters.add_clusters([cluster])
    repos.face_clusters.add_members(
        [FaceClusterMember(cluster_id=cluster.id, observation_id=smuggled.id)]
    )

    with pytest.raises(ReferenceIsolationViolationError, match="evaluation photo"):
        _guard(repos).confirm_reference_cluster(
            smuggled_run.id,
            {cluster.id},
            _person_id(repos, "张三"),
            dataset_id,
            DATASET_VERSION,
        )
    # 观察行/簇行是测试装置注入（守卫拒绝的是确认写入）——业务写入面零变化。
    assert _counts(db) == before


def test_guard_05_same_bytes_new_path_rejected(tmp_path):
    """Guard-05：评估照片同字节副本 + 新路径 + 新 photo_id → hash 守卫 REJECT。"""
    db = tmp_path / "db.sqlite3"
    repos = build_sqlite_repositories(db)
    evaluation = _build_evaluation_side(repos, tmp_path)
    dataset_id = _evaluation_dataset_id(repos)
    before = _counts(db)

    ref_dir = tmp_path / "copied_ref"
    ref_dir.mkdir()
    eval_photo = repos.photos.find_by_id(evaluation.photo_ids[0])
    shutil.copyfile(eval_photo.path.raw_path, ref_dir / "copied.jpg")
    known = {photo.id for photo in repos.photos.list_all()}
    ScanAndRegisterPhotosService(
        LocalPhotoFileScanner(),
        repos.folders,
        repos.photos,
        metadata_reader=PillowPhotoMetadataReader(),
    ).execute(ScanAndRegisterPhotosCommand(folder_path=ref_dir))
    photos = [p for p in repos.photos.list_all() if p.id not in known]
    assert len(photos) == 1  # 新路径 → 新 photo_id（photo_id 守卫放行）
    from tests.integration.test_sb1_reference_intake import _FakeDetector

    run = _recognize(repos, _FakeDetector({"copied.jpg": [(0.9, V_C)]}), photos)
    cluster_run = _cluster(repos, run)
    clusters = repos.face_clusters.list_clusters(cluster_run.id)
    assert len(clusters) == 1

    with pytest.raises(ReferenceIsolationViolationError, match="byte-identical"):
        _guard(repos).confirm_reference_cluster(
            cluster_run.id,
            {clusters[0].id},
            _person_id(repos, "张三"),
            dataset_id,
            DATASET_VERSION,
        )
    assert _counts(db) == before


def test_guard_07_unknown_observation_rejected_via_guarded_path(tmp_path):
    """Guard-07：悬挂观察经守卫路径 → REJECT 且零写入（应用层守卫独立于 FK）。"""

    class _DanglingClusterRepo:
        def __init__(self, inner, run_id, cluster_id, bogus_observation_id):
            self._inner = inner
            self._run_id = run_id
            self._cluster_id = cluster_id
            self._bogus = bogus_observation_id

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def list_members(self, cluster_run_id):
            members = list(self._inner.list_members(cluster_run_id))
            if cluster_run_id == self._run_id:
                members.append(
                    FaceClusterMember(
                        cluster_id=self._cluster_id, observation_id=self._bogus
                    )
                )
            return members

    db = tmp_path / "db.sqlite3"
    repos = build_sqlite_repositories(db)
    _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)
    dataset_id = _evaluation_dataset_id(repos)
    before = _counts(db)

    run_id = reference.cluster_run_id
    cluster_id = reference.cluster_ids[0]
    guarded = ReferenceIntakeService(
        repos.calibration_annotations,
        _DanglingClusterRepo(repos.face_clusters, run_id, cluster_id, uuid4()),
        repos.face_observations,
        repos.photos,
        ContentHashCalculator(),
        _workbench(repos),
    )
    with pytest.raises(ValidationError, match="unknown observation"):
        guarded.confirm_reference_cluster(
            run_id,
            {cluster_id},
            _person_id(repos, "张三"),
            dataset_id,
            DATASET_VERSION,
        )
    assert _counts(db) == before


def test_guard_08_unknown_person_rejected_zero_writes(tmp_path):
    """Guard-08：未解析 person 经守卫路径 → REJECT 且零写入。"""
    db = tmp_path / "db.sqlite3"
    repos = build_sqlite_repositories(db)
    _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)
    dataset_id = _evaluation_dataset_id(repos)
    before = _counts(db)

    with pytest.raises(ValidationError):
        _guard(repos).confirm_reference_cluster(
            reference.cluster_run_id,
            {reference.cluster_ids[0]},
            uuid4(),
            dataset_id,
            DATASET_VERSION,
        )
    assert _counts(db) == before


def test_guard_09_empty_embedding_rejected_at_domain_boundary(tmp_path):
    """Guard-09：空 embedding 在域构造期 REJECT——空嵌入参考样本结构性不可产生。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)
    with pytest.raises(ValidationError):
        FaceEmbedding(vector=())
    # 守卫路径确认后的样本全部非空（对照 Guard-01）。
    results = _guard(repos).confirm_reference_cluster(
        reference.cluster_run_id,
        {reference.cluster_ids[1]},
        _person_id(repos, "李四"),
        _evaluation_dataset_id(repos),
        DATASET_VERSION,
    )
    assert len(results) == 1
    for sample in repos.person_face_samples.list_by_person(_person_id(repos, "李四")):
        assert len(sample.embedding.vector) > 0


def test_guard_10_multi_face_reference_photo_allowed(tmp_path):
    """Guard-10：合法参考照片多脸多簇 → 守卫路径整批通过，不因多脸整照拒绝。"""
    db = tmp_path / "db.sqlite3"
    repos = build_sqlite_repositories(db)
    _build_evaluation_side(repos, tmp_path)
    run, cluster_run, clusters = _build_multi_face_reference(repos, tmp_path)
    assert len(clusters) == 2  # 一张照片的两张脸 → 两个簇

    results = _guard(repos).confirm_reference_cluster(
        cluster_run.id,
        {clusters[0].id, clusters[1].id},
        _person_id(repos, "张三"),
        _evaluation_dataset_id(repos),
        DATASET_VERSION,
    )
    assert len(results) == 2
    samples = repos.person_face_samples.list_by_person(_person_id(repos, "张三"))
    assert len(samples) == 2  # 两条合法 PFE（同 photo、不同 observation）


def test_guard_11_guard_failure_leaves_zero_partial_writes(tmp_path):
    """Guard-11：守卫失败零部分写入——批量守卫先于任何业务写入（多点合成证明）。"""
    db = tmp_path / "db.sqlite3"
    repos = build_sqlite_repositories(db)
    evaluation = _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)
    dataset_id = _evaluation_dataset_id(repos)
    before = _counts(db)
    guard = _guard(repos)
    person_id = _person_id(repos, "张三")

    # 失败形态一：评估簇。
    with pytest.raises(ReferenceIsolationViolationError):
        guard.confirm_reference_cluster(
            evaluation.cluster_run_id, {evaluation.cluster_ids[0]}, person_id,
            dataset_id, DATASET_VERSION,
        )
    # 失败形态二：同 run 内混合批次只要含一个脏簇，整批守卫先行拒绝
    #（batch-guard-first：守卫对全部簇完成后才允许任何写入）。
    smuggled = FaceObservation(
        run_id=reference.run_id,
        photo_id=evaluation.photo_ids[0],
        face_index=0,
        photo_face_count=1,
        det_score=0.9,
        box=FaceBox(x1=0, y1=0, x2=8, y2=8, confidence=0.9),
        embedding=FaceEmbedding(vector=V_D),
        scope_verdict="in_selected_scope",
    )
    repos.face_observations.add_many([smuggled])
    dirty_cluster = FaceCluster(
        cluster_run_id=reference.cluster_run_id,
        run_id=reference.run_id,
        ordinal=99,
        member_count=1,
        sort_key="~|~|99",
    )
    repos.face_clusters.add_clusters([dirty_cluster])
    repos.face_clusters.add_members(
        [FaceClusterMember(cluster_id=dirty_cluster.id, observation_id=smuggled.id)]
    )
    with pytest.raises(ReferenceIsolationViolationError):
        guard.confirm_reference_cluster(
            reference.cluster_run_id,
            {reference.cluster_ids[0], dirty_cluster.id},
            person_id,
            dataset_id,
            DATASET_VERSION,
        )
    assert _counts(db) == before


def test_guard_12_ordinary_business_sample_on_eval_photo_allowed(tmp_path):
    """Guard-12：评估照片上的普通业务确认沉淀业务样本=ALLOWED；Reference 路径=REJECTED。"""
    db = tmp_path / "db.sqlite3"
    repos = build_sqlite_repositories(db)
    evaluation = _build_evaluation_side(repos, tmp_path)
    dataset_id = _evaluation_dataset_id(repos)
    person_id = _person_id(repos, "张三")
    eval_cluster_id = evaluation.cluster_ids[0]

    # 业务路径（不经 Reference 入口）：评估照片上的确认是合法业务行为。
    from photo_archiver.application.commands.pairing import AssignClusterPersonCommand

    business = _workbench(repos).assign_person(
        AssignClusterPersonCommand(cluster_id=eval_cluster_id, person_id=person_id),
        actor=HUMAN_ACTOR,
    )
    assert business.status == "confirmed"
    business_samples = repos.person_face_samples.list_by_person(person_id)
    assert len(business_samples) >= 1  # 业务样本落库（合法）

    # Reference 语义路径：同一簇必须被守卫拒绝（业务样本 ≠ Evaluation Reference）。
    with pytest.raises(ReferenceIsolationViolationError):
        _guard(repos).confirm_reference_cluster(
            evaluation.cluster_run_id, {eval_cluster_id}, person_id,
            dataset_id, DATASET_VERSION,
        )
