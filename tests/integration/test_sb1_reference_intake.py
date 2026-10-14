"""S-B-1 Reference Photo Intake acceptance tests（T1–T12）.

隔离测试环境：``build_sqlite_repositories(tmp_path)`` 真实 SQLite + 临时照片
+ 可控假检测器（仅替代 InsightFace 模型本身），生产库零接触。

评估侧与参考侧各走**真实业务链**（scan → recognize → cluster → [confirm]），
``ReferenceIntakeService`` 守卫只读 fail-closed。验收映射：

    T1  Reference Photo 正常导入            chain test
    T2  Reference photo_id / observation 可解析  chain test
    T3  Reference observation embedding 非空     chain test
    T4  Reference Photo ∈ EvalPhotoSet → rejected  test_reference_photo_in_evaluation_set_rejected
    T5  cross-run 同 photo_id 不能绕过 Guard     test_cross_run_same_photo_cannot_bypass_guard
    T6  Evaluation cluster observation → rejected  test_evaluation_cluster_observation_rejected
    T7  未解析 observation → rejected            test_unknown_observation_rejected
    T8  未解析 person → rejected                 test_unknown_person_rejected
    T9  embedding 为空 → rejected（域构造期）     test_empty_embedding_rejected_at_domain_boundary
    T10 duplicate (person_id, observation_id) 幂等  test_duplicate_sample_deposit_is_idempotent
    T11 new sample enabled = 1                chain test
    T12 Assignment SSOT 语义不被破坏          chain test
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application import (
    ClusterFacesService,
    PairingWorkbenchService,
    ParseImportDraftService,
    ConfirmImportService,
    ReferenceIntakeService,
    RunRecognitionService,
    SuggestPairingsService,
)
from photo_archiver.application.commands.cluster_faces import StartClusteringRunCommand
from photo_archiver.application.commands.import_draft import (
    ConfirmImportCommand,
    ParseImportDraftCommand,
)
from photo_archiver.application.commands.pairing import (
    AssignClusterPersonCommand,
    ConfirmAssignmentCommand,
    StartSuggestPairingsCommand,
)
from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR
from photo_archiver.application.commands.scan_and_register_photos import (
    ScanAndRegisterPhotosCommand,
)
from photo_archiver.application.commands.start_recognition_run import (
    StartRecognitionRunCommand,
)
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
)
from photo_archiver.application.services.scan_and_register_photos_service import (
    ScanAndRegisterPhotosService,
)
from photo_archiver.domain.entities.calibration_annotation import (
    CalibrationDataset,
    CalibrationGroundTruth,
)
from photo_archiver.domain.entities.cluster_assignment import PersonFaceSample
from photo_archiver.domain.entities.face_cluster import FaceCluster, FaceClusterMember, FaceClusterRun
from photo_archiver.domain.entities.face_observation import FaceObservation
from photo_archiver.domain.exceptions import (
    ReferenceIsolationViolationError,
    ValidationError,
)
from photo_archiver.domain.value_objects import (
    FaceBox,
    FaceBoxEmbedding,
    FaceEmbedding,
)
from photo_archiver.infrastructure import (
    FileRosterTableReader,
    LocalPhotoFileScanner,
    NumpyCosineSimilarityFactory,
    PillowPhotoMetadataReader,
    SQLiteUnitOfWork,
)
from photo_archiver.infrastructure.image.content_hash_calculator import (
    ContentHashCalculator,
)

DATASET_VERSION = "round-1"

# 四个相互正交的 4 维向量：同向量聚为一簇，异向量互不合并。
V_A = (1.0, 0.0, 0.0, 0.0)
V_B = (0.0, 1.0, 0.0, 0.0)
V_C = (0.0, 0.0, 1.0, 0.0)
V_D = (0.0, 0.0, 0.0, 1.0)


class _FakeDetector:
    """可控假检测器（替代 InsightFace）：按图片文件名返回预定人脸嵌入。"""

    def __init__(self, faces_by_name: dict[str, list[tuple[float, tuple[float, ...]]]]):
        self._faces_by_name = faces_by_name

    def detect(self, image: Path) -> list[FaceBoxEmbedding]:
        return self.detect_with_embeddings(image)

    def detect_with_embeddings(self, image: Path) -> list[FaceBoxEmbedding]:
        faces = self._faces_by_name.get(image.name, [])
        return [
            FaceBoxEmbedding(
                box=FaceBox(x1=0, y1=0, x2=8, y2=8, confidence=confidence),
                embedding=FaceEmbedding(vector=tuple(vector)),
            )
            for confidence, vector in faces
        ]


def _make_image(directory: Path, name: str, captured: datetime) -> Path:
    path = directory / name
    Image.new("RGB", (8, 8), (len(name) * 30 % 255, 60, 120)).save(path)
    stamp = captured.timestamp()
    os.utime(path, (stamp, stamp))
    return path


def _import_people(repos, tmp_path: Path, names: list[str]):
    csv_path = tmp_path / "roster.csv"
    lines = ["姓名,工号,部门"]
    lines.extend(f"{name},2026-{index:03d},一组" for index, name in enumerate(names, 1))
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    parse = ParseImportDraftService(
        FileRosterTableReader(), repos.import_batches, repos.people
    )
    draft = parse.execute(ParseImportDraftCommand(source_path=csv_path))
    confirm = ConfirmImportService(
        repos.import_batches,
        repos.people,
        unit_of_work=SQLiteUnitOfWork(repos._connection_provider),
    )
    result = confirm.execute(ConfirmImportCommand(batch_id=draft.batch.id))
    assert result.errors == ()
    return [repos.people.find_by_id(pid) for pid in result.person_ids]


def _scan(repos, photos_dir: Path):
    service = ScanAndRegisterPhotosService(
        LocalPhotoFileScanner(),
        repos.folders,
        repos.photos,
        metadata_reader=PillowPhotoMetadataReader(),
    )
    service.execute(ScanAndRegisterPhotosCommand(folder_path=photos_dir))
    return [photo for photo in repos.photos.list_all()]


def _recognize(repos, detector, photos):
    service = RunRecognitionService(
        detector=detector,
        matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=repos.face_embeddings,
        recognition_repository=repos.recognition,
        recognition_run_repository=repos.recognition_runs,
        face_observation_repository=repos.face_observations,
        photo_repository=repos.photos,
    )
    return service.execute(
        StartRecognitionRunCommand(
            photo_ids=tuple(photo.id for photo in photos),
            images=tuple(photo.path.raw_path for photo in photos),
        )
    )


def _cluster(repos, run):
    return ClusterFacesService(
        repos.recognition_runs,
        repos.face_observations,
        repos.face_clusters,
        NumpyCosineSimilarityFactory(),
    ).execute(StartClusteringRunCommand(run.id))


def _guard(repos) -> ReferenceIntakeService:
    return ReferenceIntakeService(
        repos.calibration_annotations,
        repos.face_clusters,
        repos.face_observations,
        repos.photos,
        ContentHashCalculator(),
        _workbench(repos),
    )


def _workbench(repos) -> PairingWorkbenchService:
    return PairingWorkbenchService(
        repos.cluster_assignments,
        repos.face_clusters,
        repos.face_observations,
        repos.people,
        repos.recognition,
        repos.person_face_samples,
        reconciler=ProjectionReconciler(
            recognition_repository=repos.recognition,
            assignment_repository=repos.cluster_assignments,
            cluster_repository=repos.face_clusters,
            observation_repository=repos.face_observations,
        ),
    )


@dataclass(frozen=True, slots=True)
class _Side:
    """One intake side (evaluation or reference) built through the real chain."""

    run_id: object
    cluster_run_id: object
    photo_ids: list
    cluster_ids: list
    observation_ids: list


def _single_face_detector(faces_by_name) -> _FakeDetector:
    return _FakeDetector(faces_by_name)


def _build_evaluation_side(repos, tmp_path: Path) -> _Side:
    """Frozen evaluation baseline simulation: scan→recognize→cluster→GT."""
    eval_dir = tmp_path / "eval_photos"
    eval_dir.mkdir()
    _make_image(eval_dir, "eval_1.jpg", datetime(2026, 1, 1, 12, 0, 0))
    _make_image(eval_dir, "eval_2.jpg", datetime(2026, 1, 2, 12, 0, 0))
    photos = _scan(repos, eval_dir)
    run = _recognize(
        repos,
        _single_face_detector(
            {"eval_1.jpg": [(0.9, V_A)], "eval_2.jpg": [(0.9, V_B)]}
        ),
        photos,
    )
    cluster_run = _cluster(repos, run)
    people = _import_people(repos, tmp_path, ["张三", "李四"])
    clusters = sorted(
        repos.face_clusters.list_clusters(cluster_run.id), key=lambda c: c.ordinal
    )
    dataset = CalibrationDataset(
        version=DATASET_VERSION, cluster_count=2, usable_count=2, excluded_count=0
    )
    repos.calibration_annotations.add_dataset(dataset)
    for index, cluster in enumerate(clusters):
        repos.calibration_annotations.add_ground_truth(
            CalibrationGroundTruth(
                cluster_id=cluster.id,
                verdict="person",
                resolution="expert",
                source_annotation_ids=(uuid4(),),
                annotator_count=1,
                person_id=people[index].id,
                dataset_id=dataset.id,
                dataset_version=DATASET_VERSION,
            )
        )
    observations = repos.face_observations.list_by_run(run.id)
    return _Side(
        run_id=run.id,
        cluster_run_id=cluster_run.id,
        photo_ids=[photo.id for photo in photos],
        cluster_ids=[cluster.id for cluster in clusters],
        observation_ids=[observation.id for observation in observations],
    )


def _build_reference_side(repos, tmp_path: Path) -> _Side:
    """Reference batch: independent directory → independent runs."""
    ref_dir = tmp_path / "reference_photos"
    ref_dir.mkdir()
    _make_image(ref_dir, "ref_1.jpg", datetime(2026, 3, 1, 12, 0, 0))
    _make_image(ref_dir, "ref_2.jpg", datetime(2026, 3, 2, 12, 0, 0))
    known = {photo.id for photo in repos.photos.list_all()}
    photos = [photo for photo in _scan(repos, ref_dir) if photo.id not in known]
    run = _recognize(
        repos,
        _single_face_detector(
            {"ref_1.jpg": [(0.9, V_C)], "ref_2.jpg": [(0.9, V_D)]}
        ),
        photos,
    )
    cluster_run = _cluster(repos, run)
    clusters = repos.face_clusters.list_clusters(cluster_run.id)
    observations = repos.face_observations.list_by_run(run.id)
    return _Side(
        run_id=run.id,
        cluster_run_id=cluster_run.id,
        photo_ids=[photo.id for photo in photos],
        cluster_ids=[cluster.id for cluster in clusters],
        observation_ids=[observation.id for observation in observations],
    )


def _confirm_reference_clusters(repos, reference: _Side):
    workbench = _workbench(repos)
    results = []
    for assignment in repos.cluster_assignments.list_active_by_cluster_run(
        reference.cluster_run_id
    ):
        if assignment.status == "suggested":
            results.append(workbench.confirm(
                ConfirmAssignmentCommand(assignment_id=assignment.id)))
        elif assignment.status == "auto_confirmed":
            # S4 C-3：位置自动确认行的人工终审走 D-6 路径（新建 manual confirmed）。
            results.append(workbench.assign_person(
                AssignClusterPersonCommand(cluster_id=assignment.cluster_id,
                                           person_id=assignment.person_id),
                actor=HUMAN_ACTOR))
    return results


def _all_samples(repos) -> list[PersonFaceSample]:
    samples: list[PersonFaceSample] = []
    for person in repos.people.list_all():
        samples.extend(repos.person_face_samples.list_by_person(person.id))
    return samples


def test_reference_intake_chain_creates_valid_samples(tmp_path):
    """T1/T2/T3/T11/T12 + Phase E/F 代次独立性 + Phase C/G 守卫通过。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    evaluation = _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)

    # Phase E/F：参考批次代次独立（新 run / 新 cluster run，绝非复用评估代次）。
    assert reference.run_id != evaluation.run_id
    assert reference.cluster_run_id != evaluation.cluster_run_id

    # T1：参考照片已导入（独立批次）。
    assert len(reference.photo_ids) == 2

    # Phase C：动态重建 EvalPhotoSet（此处 = 2 张评估照片，非硬编码）且参考集无交集。
    report = _guard(repos).verify_reference_photos(
        set(reference.photo_ids), _evaluation_dataset_id(repos), DATASET_VERSION
    )
    assert report.evaluation_photo_count == 2
    assert report.reference_photo_count == 2

    # Phase G 守卫通过（待沉淀观察全部干净）。
    _guard(repos).verify_reference_cluster_samples(
        reference.cluster_run_id,
        set(reference.cluster_ids),
        _evaluation_dataset_id(repos),
        DATASET_VERSION,
    )

    # T12 前置：人工确认走既有业务入口（suggest → confirm，Assignment SSOT 不变）。
    _suggest = SuggestPairingsService(
        repos.face_clusters,
        repos.face_observations,
        repos.people,
        repos.cluster_assignments,
        repos.person_face_samples,
        NumpyCosineSimilarityFactory(),
    )
    _suggest.execute(StartSuggestPairingsCommand(cluster_run_id=reference.cluster_run_id))
    results = _confirm_reference_clusters(repos, reference)
    assert len(results) == 2

    # T2：每个样本的 observation 可解析且其 photo_id 在参考批次内。
    observations = {
        observation.id: observation
        for observation in repos.face_observations.list_by_run(reference.run_id)
    }
    samples = _all_samples(repos)
    assert len(samples) == 2
    for sample in samples:
        assert sample.observation_id in observations
        assert observations[sample.observation_id].photo_id in set(reference.photo_ids)

    # T3：embedding 非空。
    assert all(len(sample.embedding.vector) > 0 for sample in samples)

    # T11：新样本 enabled = 1。
    assert all(sample.enabled for sample in samples)

    # T12：Assignment SSOT —— 簇级确认行存在（业务身份事实仍由 Assignment 承载），
    # 且评估侧零污染。
    confirmed = [
        assignment
        for assignment in repos.cluster_assignments.list_active_by_cluster_run(
            reference.cluster_run_id
        )
        if assignment.status == "confirmed"
    ]
    assert len(confirmed) == 2
    assert repos.cluster_assignments.list_active_by_cluster_run(
        evaluation.cluster_run_id
    ) == []
    assert len(repos.person_face_samples.list_by_person(_person_id(repos, "张三"))) >= 1


def test_duplicate_sample_deposit_is_idempotent(tmp_path):
    """T10：重复 (person_id, observation_id) 不产生重复样本。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)
    suggest = SuggestPairingsService(
        repos.face_clusters,
        repos.face_observations,
        repos.people,
        repos.cluster_assignments,
        repos.person_face_samples,
        NumpyCosineSimilarityFactory(),
    )
    suggest.execute(StartSuggestPairingsCommand(cluster_run_id=reference.cluster_run_id))
    _confirm_reference_clusters(repos, reference)
    samples_after_first = _all_samples(repos)
    distinct_pairs = {(s.person_id, s.observation_id) for s in samples_after_first}
    assert len(distinct_pairs) == len(samples_after_first) == 2

    # 幂等路径一：重复 suggest 对已确认簇不再产生新建议（active-assignment skip）。
    suggest.execute(StartSuggestPairingsCommand(cluster_run_id=reference.cluster_run_id))
    still_suggested = [
        assignment
        for assignment in repos.cluster_assignments.list_active_by_cluster_run(
            reference.cluster_run_id
        )
        if assignment.status == "suggested"
    ]
    assert still_suggested == []

    # 幂等路径二：对已确认行重复 confirm 被状态机拒绝，样本数不变。
    confirmed = [
        assignment
        for assignment in repos.cluster_assignments.list_active_by_cluster_run(
            reference.cluster_run_id
        )
        if assignment.status == "confirmed"
    ]
    with pytest.raises(ValidationError):
        _workbench(repos).confirm(ConfirmAssignmentCommand(assignment_id=confirmed[0].id))
    assert _all_samples(repos) == samples_after_first


def test_reference_photo_in_evaluation_set_rejected(tmp_path):
    """T4：Reference Photo ∈ EvalPhotoSet → fail-closed；守卫只读；空集拒绝。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    evaluation = _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)
    guard = _guard(repos)
    dataset_id = _evaluation_dataset_id(repos)

    photos_before = len(repos.photos.list_all())
    observations_before = len(repos.face_observations.list_by_run(reference.run_id))
    samples_before = len(_all_samples(repos))

    with pytest.raises(ReferenceIsolationViolationError):
        guard.verify_reference_photos(
            {evaluation.photo_ids[0]}, dataset_id, DATASET_VERSION
        )
    with pytest.raises(ValidationError):
        guard.verify_reference_photos(set(), dataset_id, DATASET_VERSION)
    # 数据集版本写错 → fail-closed（不允许静默放行）。
    with pytest.raises(ValidationError):
        guard.verify_reference_photos(
            set(reference.photo_ids), dataset_id, "round-2"
        )

    # 守卫只读：验证失败后零写入。
    assert len(repos.photos.list_all()) == photos_before
    assert len(repos.face_observations.list_by_run(reference.run_id)) == observations_before
    assert len(_all_samples(repos)) == samples_before

    # 参考集自身依然通过（对照）。
    report = guard.verify_reference_photos(set(reference.photo_ids), dataset_id, DATASET_VERSION)
    assert report.reference_photo_count == 2


def test_cross_run_same_photo_cannot_bypass_guard(tmp_path):
    """T5：同一物理照片经不同 run 的 observation_id 不能绕过 photo_id 守卫。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    evaluation = _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)

    # 参考 run 下为评估照片再造一条观察（新 observation_id，同一 photo_id）。
    eval_photo_id = evaluation.photo_ids[0]
    smuggled = FaceObservation(
        run_id=reference.run_id,
        photo_id=eval_photo_id,
        face_index=0,
        photo_face_count=1,
        det_score=0.9,
        box=FaceBox(x1=0, y1=0, x2=8, y2=8, confidence=0.9),
        embedding=FaceEmbedding(vector=V_D),
        scope_verdict="in_selected_scope",
    )
    repos.face_observations.add_many([smuggled])
    assert smuggled.id not in set(evaluation.observation_ids)

    # 把它挂进一个"参考簇"，photo 级守卫必须拒绝（同簇观察集不含它也无济于事）。
    smuggled_run = FaceClusterRun(
        recognition_run_id=reference.run_id, algorithm_version="test"
    )
    repos.face_clusters.add_cluster_run(smuggled_run)
    smuggled_cluster = FaceCluster(
        cluster_run_id=smuggled_run.id,
        run_id=reference.run_id,
        ordinal=0,
        member_count=1,
        sort_key="~|~|0",
    )
    repos.face_clusters.add_clusters([smuggled_cluster])
    repos.face_clusters.add_members(
        [FaceClusterMember(cluster_id=smuggled_cluster.id, observation_id=smuggled.id)]
    )
    with pytest.raises(ReferenceIsolationViolationError, match="evaluation photo"):
        _guard(repos).verify_reference_cluster_samples(
            smuggled_run.id,
            {smuggled_cluster.id},
            _evaluation_dataset_id(repos),
            DATASET_VERSION,
        )
    # photo 级主守卫同样拒绝该照片。
    with pytest.raises(ReferenceIsolationViolationError):
        _guard(repos).verify_reference_photos(
            {eval_photo_id}, _evaluation_dataset_id(repos), DATASET_VERSION
        )


def test_evaluation_cluster_observation_rejected(tmp_path):
    """T6：Evaluation cluster 的观察不得作为 Reference 样本来源（same-cluster）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    evaluation = _build_evaluation_side(repos, tmp_path)
    _build_reference_side(repos, tmp_path)
    with pytest.raises(ReferenceIsolationViolationError, match="evaluation cluster"):
        _guard(repos).verify_reference_cluster_samples(
            evaluation.cluster_run_id,
            {evaluation.cluster_ids[0]},
            _evaluation_dataset_id(repos),
            DATASET_VERSION,
        )


def test_unknown_observation_rejected(tmp_path):
    """T7：簇成员指向不存在的观察 → rejected。

    两层防御实测：存储层 FK 先行拒绝（悬挂成员结构性不可持久化）；守卫的
    dangling 分支为 in-memory 适配器与未来 schema 漂移保留的纵深防御。
    """
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)
    dangling_run = FaceClusterRun(
        recognition_run_id=reference.run_id, algorithm_version="test"
    )
    repos.face_clusters.add_cluster_run(dangling_run)
    dangling_cluster = FaceCluster(
        cluster_run_id=dangling_run.id,
        run_id=reference.run_id,
        ordinal=0,
        member_count=1,
        sort_key="~|~|0",
    )
    repos.face_clusters.add_clusters([dangling_cluster])
    with pytest.raises(sqlite3.IntegrityError):
        repos.face_clusters.add_members(
            [
                FaceClusterMember(
                    cluster_id=dangling_cluster.id, observation_id=uuid4()
                )
            ]
        )
    # 成员未落库 → 守卫的悬挂分支需注入 in-memory 悬挂态验证（不依赖 FK）：
    # 用只重载 list_members 的包装仓储模拟"成员存在但观察缺失"。
    class _DanglingClusterRepo:
        """只重载 list_members：注入一个指向不存在观察的成员（绕过 FK）。"""

        def __init__(self, inner):
            self._inner = inner
            self._inject = (dangling_cluster.id, uuid4())

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def list_members(self, cluster_run_id):
            members = list(self._inner.list_members(cluster_run_id))
            if cluster_run_id == dangling_run.id:
                members.append(
                    FaceClusterMember(
                        cluster_id=self._inject[0], observation_id=self._inject[1]
                    )
                )
            return members

    guarded = ReferenceIntakeService(
        repos.calibration_annotations,
        _DanglingClusterRepo(repos.face_clusters),
        repos.face_observations,
        repos.photos,
        ContentHashCalculator(),
        _workbench(repos),
    )
    with pytest.raises(ValidationError, match="unknown observation"):
        guarded.verify_reference_cluster_samples(
            dangling_run.id,
            {dangling_cluster.id},
            _evaluation_dataset_id(repos),
            DATASET_VERSION,
        )


def test_unknown_person_rejected(tmp_path):
    """T8：未解析 person → rejected（既有业务守卫，零副作用）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)
    assignments_before = len(repos.cluster_assignments.list_active_by_cluster_run(
        reference.cluster_run_id
    ))
    with pytest.raises(ValidationError):
        _workbench(repos).assign_person(
            AssignClusterPersonCommand(
                cluster_id=reference.cluster_ids[0], person_id=uuid4()
            ),
            actor=HUMAN_ACTOR,
        )
    assert (
        len(repos.cluster_assignments.list_active_by_cluster_run(reference.cluster_run_id))
        == assignments_before
    )


def test_empty_embedding_rejected_at_domain_boundary(tmp_path):
    """T9：embedding 为空在域构造期即被拒绝——空嵌入样本结构性不可产生。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _build_evaluation_side(repos, tmp_path)
    reference = _build_reference_side(repos, tmp_path)
    suggest = SuggestPairingsService(
        repos.face_clusters,
        repos.face_observations,
        repos.people,
        repos.cluster_assignments,
        repos.person_face_samples,
        NumpyCosineSimilarityFactory(),
    )
    suggest.execute(StartSuggestPairingsCommand(cluster_run_id=reference.cluster_run_id))
    _confirm_reference_clusters(repos, reference)
    with pytest.raises(ValidationError):
        FaceEmbedding(vector=())
    for sample in _all_samples(repos):
        assert len(sample.embedding.vector) > 0


def _evaluation_dataset_id(repos):
    datasets = repos.calibration_annotations.list_datasets()
    assert len(datasets) == 1
    return datasets[0].id


def _person_id(repos, name: str):
    for person in repos.people.list_all():
        if person.name == name:
            return person.id
    raise AssertionError(f"person {name} not found")
