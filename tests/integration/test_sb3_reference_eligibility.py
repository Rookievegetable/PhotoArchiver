"""S-B-3 Reference Eligibility acceptance tests（任务书 §11 场景 1–18）.

隔离 SQLite 临时库；评估侧 persons = 冻结 GT 人口（张三/李四/王五），
参考批次走 D-SB-1 指定链（独立目录 → 独立识别 run → 独立聚类 run）。
"""

from __future__ import annotations

import shutil
import sqlite3

from PIL import Image
import uuid as uuid_mod
from datetime import datetime, timezone as _tz
from pathlib import Path

import pytest

from tests.integration.test_sb1_reference_intake import (
    _cluster,
    _evaluation_dataset_id,
    _import_people,
    _recognize,
    _scan,
    _workbench,
)

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application import (
    ReferenceEligibilityService,
    ReferenceIntakeService,
)
from photo_archiver.application.commands.pairing import AssignClusterPersonCommand
from photo_archiver.domain import Person
from photo_archiver.domain.entities.calibration_annotation import (
    CalibrationDataset,
    CalibrationGroundTruth,
)
from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR
from photo_archiver.domain.entities.face_cluster import (
    FaceCluster,
    FaceClusterMember,
)
from photo_archiver.infrastructure.image.content_hash_calculator import (
    ContentHashCalculator,
)

VERSION = "pilot-sb3"


def _make_unique_image(directory: Path, name: str, seed: int) -> Path:
    """每张图唯一像素内容（S-B-2 hash 守卫会拦同字节图——测试图必须互异）。"""
    path = directory / name
    Image.new("RGB", (8, 8), (seed * 37 % 255, 90 + seed % 100, 60 + seed % 50)).save(path)
    return path


def _detector(faces_by_name):
    from tests.integration.test_sb1_reference_intake import _FakeDetector

    return _FakeDetector(faces_by_name)


def _guard(repos) -> ReferenceIntakeService:
    return ReferenceIntakeService(
        repos.calibration_annotations,
        repos.face_clusters,
        repos.face_observations,
        repos.photos,
        ContentHashCalculator(),
        _workbench(repos),
    )


def _eligibility(repos) -> ReferenceEligibilityService:
    return ReferenceEligibilityService(
        reference_intake=_guard(repos),
        calibration_repository=repos.calibration_annotations,
        assignment_repository=repos.cluster_assignments,
        cluster_repository=repos.face_clusters,
        observation_repository=repos.face_observations,
        photo_repository=repos.photos,
        person_repository=repos.people,
        sample_repository=repos.person_face_samples,
        run_repository=repos.recognition_runs,
        content_hasher=ContentHashCalculator(),
    )


def _build_three_person_evaluation(repos, tmp_path: Path):
    """冻结评估侧：3 张单人照片 → 3 簇 → 冻结 GT（张三/李四/王五）。"""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    _make_unique_image(eval_dir, "e1.jpg", 1)
    _make_unique_image(eval_dir, "e2.jpg", 2)
    _make_unique_image(eval_dir, "e3.jpg", 3)
    photos = _scan(repos, eval_dir)
    run = _recognize(repos, _detector({
        "e1.jpg": [(0.9, (1.0, 0, 0, 0))],
        "e2.jpg": [(0.9, (0, 1.0, 0, 0))],
        "e3.jpg": [(0.9, (0, 0, 1.0, 0))],
    }), photos)
    cluster_run = _cluster(repos, run)
    people = _import_people(repos, tmp_path, ["张三", "李四", "王五"])
    clusters = sorted(
        repos.face_clusters.list_clusters(cluster_run.id), key=lambda c: c.ordinal
    )
    dataset = CalibrationDataset(version=VERSION, cluster_count=3,
                                 usable_count=3, excluded_count=0)
    repos.calibration_annotations.add_dataset(dataset)
    for index, cluster in enumerate(clusters):
        repos.calibration_annotations.add_ground_truth(CalibrationGroundTruth(
            cluster_id=cluster.id, verdict="person", resolution="expert",
            source_annotation_ids=(uuid_mod.uuid4(),), annotator_count=1,
            person_id=people[index].id,
            dataset_id=dataset.id, dataset_version=VERSION))
    return run, cluster_run, clusters, people


def _reference_batch(repos, tmp_path: Path, names_and_faces):
    """参考批次：独立目录 → 独立识别 run → 独立聚类 run（D-SB-1 指定链）。"""
    ref_dir = tmp_path / f"ref_{uuid_mod.uuid4().hex[:8]}"
    ref_dir.mkdir()
    for index, (name, _faces) in enumerate(names_and_faces):
        _make_unique_image(ref_dir, name, 100 + index)
    photos = _scan(repos, ref_dir)
    run = _recognize(repos, _detector(dict(names_and_faces)), photos)
    cluster_run = _cluster(repos, run)
    clusters = sorted(
        repos.face_clusters.list_clusters(cluster_run.id), key=lambda c: c.ordinal
    )
    return run, cluster_run, clusters


def _person_id(repos, name: str):
    for person in repos.people.list_all():
        if person.name == name:
            return person.id
    raise AssertionError(f"person {name} not found")


def _evaluate(repos, run, cluster_run):
    report = _eligibility(repos).evaluate_person_coverage(
        _evaluation_dataset_id(repos), VERSION, {run.id}, {cluster_run.id}
    )
    by_pfe = {s.pfe_id: s for s in report.samples}
    return report, by_pfe


def _samples_of(report, person_id):
    return [s for s in report.samples if s.person_id == person_id]


def test_case_1_frozen_person_reference_is_eligible(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    r_run, r_crun, r_clusters = _reference_batch(
        repos, tmp_path, [("r1.jpg", [(0.9, (0, 0, 0, 1.0))])])
    _guard(repos).confirm_reference_cluster(
        r_crun.id, {r_clusters[0].id}, people[0].id,
        _evaluation_dataset_id(repos), VERSION)
    report, _by_pfe = _evaluate(repos, r_run, r_crun)
    sample = _samples_of(report, people[0].id)[0]
    assert sample.decision == "ELIGIBLE"
    assert all(c.passed for c in sample.checks)
    assert sample.quality_observation.endswith("(D-SB-10 OPEN PARAMETER)")


def test_case_2_7_8_9_business_pfe_on_eval_photo_ineligible(tmp_path):
    """generic business PFE：评估照片/观察/簇 + cross-run 四查全败。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, e_crun, e_clusters, _people = _build_three_person_evaluation(repos, tmp_path)
    person = _person_id(repos, "王五")
    _workbench(repos).assign_person(AssignClusterPersonCommand(
        cluster_id=e_clusters[0].id, person_id=person), actor=HUMAN_ACTOR)
    r_run, r_crun, _r_clusters = _reference_batch(
        repos, tmp_path, [("decoy.jpg", [(0.9, (0, 0, 0, 1.0))])])
    report, _by_pfe = _evaluate(repos, r_run, r_crun)
    sample = _samples_of(report, person)[0]
    assert sample.decision == "INELIGIBLE"
    failed = {c.name for c in sample.checks if not c.passed}
    assert {"E-01-reference-source", "E-05-eval-photo-isolation",
            "E-05-same-cluster", "E-05-cross-run"} <= failed


def test_case_3_4_corrupt_embedding_rows_ineligible(tmp_path):
    """missing/empty/corrupt embedding → 该人整组 INELIGIBLE（不崩溃、不跳过）。"""
    db = tmp_path / "db.sqlite3"
    repos = build_sqlite_repositories(db)
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    r_run, r_crun, r_clusters = _reference_batch(
        repos, tmp_path, [("r1.jpg", [(0.9, (0, 0, 0, 1.0))])])
    _guard(repos).confirm_reference_cluster(
        r_crun.id, {r_clusters[0].id}, people[0].id,
        _evaluation_dataset_id(repos), VERSION)
    obs_id = repos.face_clusters.list_members(r_crun.id)[0].observation_id
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO person_face_embeddings (id, person_id, observation_id,"
        " embedding, quality_score, enabled, created_at) VALUES (?, ?, ?, ?, 0.5, 1, ?)",
        (str(uuid_mod.uuid4()), str(people[1].id), str(obs_id), "",
         datetime.now(_tz.utc).isoformat()))
    con.execute(
        "INSERT INTO person_face_embeddings (id, person_id, observation_id,"
        " embedding, quality_score, enabled, created_at) VALUES (?, ?, ?, ?, 0.5, 1, ?)",
        (str(uuid_mod.uuid4()), str(people[2].id), str(obs_id), "not-json",
         datetime.now(_tz.utc).isoformat()))
    con.commit()
    con.close()
    report, _by_pfe = _evaluate(repos, r_run, r_crun)
    assert set(report.unreadable_person_ids) == {people[1].id, people[2].id}
    for person in (people[1], people[2]):
        assert _samples_of(report, person.id) == []  # 无法评估 → 排除出候选
    zhang = _samples_of(report, people[0].id)
    # 张三在该测试场景中就是冻结 GT 人口 → 合法参考样本判 ELIGIBLE。
    assert len(zhang) == 1 and zhang[0].decision == "ELIGIBLE"


def test_case_5_dangling_observation_ineligible(tmp_path):
    db = tmp_path / "db.sqlite3"
    repos = build_sqlite_repositories(db)
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    r_run, r_crun, _r_clusters = _reference_batch(
        repos, tmp_path, [("r1.jpg", [(0.9, (0, 0, 0, 1.0))])])
    con = sqlite3.connect(str(db))
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute(
        "INSERT INTO person_face_embeddings (id, person_id, observation_id,"
        " embedding, quality_score, enabled, created_at) VALUES (?, ?, ?, ?, 0.5, 1, ?)",
        (str(uuid_mod.uuid4()), str(people[0].id), str(uuid_mod.uuid4()),
         "[0.5, 0.5, 0.5, 0.5]", datetime.now(_tz.utc).isoformat()))
    con.commit()
    con.close()
    report, _by_pfe = _evaluate(repos, r_run, r_crun)
    dangling = [s for s in _samples_of(report, people[0].id)
                if s.observation_id not in
                {o.id for o in repos.face_observations.list_by_run(r_run.id)}]
    assert dangling and all(s.decision == "INELIGIBLE" for s in dangling)
    assert all(any(c.name == "E-04-observation-valid" and not c.passed
                   for c in s.checks) for s in dangling)


def test_case_6_invalid_person_blocked_by_fk(tmp_path):
    """invalid person：FK 结构性阻止（第一层防御实测）。"""
    db = tmp_path / "db.sqlite3"
    repos = build_sqlite_repositories(db)
    _build_three_person_evaluation(repos, tmp_path)
    phantom = uuid_mod.uuid4()
    some_obs = repos.face_observations.list_by_run(
        repos.recognition_runs.list_runs()[0].id)[0].id
    con = sqlite3.connect(str(db))
    con.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO person_face_embeddings (id, person_id, observation_id,"
            " embedding, enabled, created_at) VALUES (?, ?, ?, ?, 1, 'x')",
            (str(uuid_mod.uuid4()), str(phantom), str(some_obs), "[0.5, 0.5, 0.5, 0.5]"))
    con.close()


def test_case_10_same_bytes_new_path_ineligible(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, _people = _build_three_person_evaluation(repos, tmp_path)
    eval_photo = [p for p in repos.photos.list_all() if p.original_name == "e1.jpg"][0]
    ref_dir = tmp_path / "copied"
    ref_dir.mkdir()
    shutil.copyfile(eval_photo.path.raw_path, ref_dir / "copy.jpg")
    photos = _scan(repos, ref_dir)
    r_run = _recognize(repos, _detector({"copy.jpg": [(0.9, (1.0, 0, 0, 0))]}), photos)
    r_crun = _cluster(repos, r_run)
    r_cluster = repos.face_clusters.list_clusters(r_crun.id)[0]
    person = _person_id(repos, "张三")
    _workbench(repos).assign_person(AssignClusterPersonCommand(
        cluster_id=r_cluster.id, person_id=person), actor=HUMAN_ACTOR)
    report, _by_pfe = _evaluate(repos, r_run, r_crun)
    sample = _samples_of(report, person)[0]
    assert sample.decision == "INELIGIBLE"
    assert any(c.name == "E-05-content-hash" and not c.passed
               for c in sample.checks)


def test_case_11_multi_face_same_photo_different_people_allowed(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    r_run, r_crun, r_clusters = _reference_batch(repos, tmp_path, [
        ("two.jpg", [(0.9, (0, 0, 0, 1.0)), (0.9, (1.0, 1.0, 0, 0))])])
    assert len(r_clusters) == 2
    _guard(repos).confirm_reference_cluster(
        r_crun.id, {r_clusters[0].id}, people[0].id,
        _evaluation_dataset_id(repos), VERSION)
    _guard(repos).confirm_reference_cluster(
        r_crun.id, {r_clusters[1].id}, people[1].id,
        _evaluation_dataset_id(repos), VERSION)
    report, _by_pfe = _evaluate(repos, r_run, r_crun)
    same_photo = [s for s in report.samples
                  if s.person_id in (people[0].id, people[1].id)]
    assert len(same_photo) == 2
    assert all(s.decision == "ELIGIBLE" for s in same_photo)
    assert len({s.photo_id for s in same_photo}) == 1  # 同 photo，两条合法参考


def test_case_12_13_14_coverage_classes(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    r_run, r_crun, r_clusters = _reference_batch(repos, tmp_path, [
        ("r1.jpg", [(0.9, (0, 0, 0, 1.0))]),
        ("r2.jpg", [(0.9, (1.0, 1.0, 0, 0))]),
        ("r3.jpg", [(0.9, (1.0, -1.0, 0, 0))]),
    ])
    # 张三 ×2（multi）、李四 ×1（single）、王五 ×0（gap）。
    _guard(repos).confirm_reference_cluster(
        r_crun.id, {r_clusters[0].id, r_clusters[1].id}, people[0].id,
        _evaluation_dataset_id(repos), VERSION)
    _guard(repos).confirm_reference_cluster(
        r_crun.id, {r_clusters[2].id}, people[1].id,
        _evaluation_dataset_id(repos), VERSION)
    report = _eligibility(repos).evaluate_person_coverage(
        _evaluation_dataset_id(repos), VERSION, {r_run.id}, {r_crun.id})
    rows = {c.person_name: c for c in report.coverage_rows if c.is_frozen_person}
    assert rows["张三"].reference_count == 2
    assert rows["张三"].classification == "COVERED/MULTI_REFERENCE"
    assert rows["李四"].reference_count == 1
    assert rows["李四"].classification == "COVERED/SINGLE_REFERENCE"
    assert rows["王五"].reference_count == 0
    assert rows["王五"].classification == "NO_REFERENCE"
    assert report.frozen_person_count == 3
    assert report.frozen_covered_count == 2
    assert report.frozen_no_reference_count == 1
    assert report.frozen_multi_reference_count == 1
    assert report.frozen_single_reference_count == 1


def test_case_15_non_frozen_person_coverage_only(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, _people = _build_three_person_evaluation(repos, tmp_path)
    repos.people.add(Person(name="编外测试人"))
    outsider = [p for p in repos.people.list_all() if p.name == "编外测试人"][0]
    r_run, r_crun, r_clusters = _reference_batch(
        repos, tmp_path, [("r1.jpg", [(0.9, (0, 0, 0, 1.0))])])
    _guard(repos).confirm_reference_cluster(
        r_crun.id, {r_clusters[0].id}, outsider.id,
        _evaluation_dataset_id(repos), VERSION)
    report = _eligibility(repos).evaluate_person_coverage(
        _evaluation_dataset_id(repos), VERSION, {r_run.id}, {r_crun.id})
    sample = _samples_of(report, outsider.id)[0]
    assert sample.decision == "COVERAGE_ONLY"
    assert all(c.passed for c in sample.checks)
    assert report.coverage_only_person_count == 1
    assert report.frozen_covered_count == 0  # 冻结人口覆盖不变（0/3）


def test_case_16_quality_observed_not_judged(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    r_run, r_crun, r_clusters = _reference_batch(
        repos, tmp_path, [("lowq.jpg", [(0.10, (0, 0, 0, 1.0))])])
    _guard(repos).confirm_reference_cluster(
        r_crun.id, {r_clusters[0].id}, people[0].id,
        _evaluation_dataset_id(repos), VERSION)
    report, _by_pfe = _evaluate(repos, r_run, r_crun)
    sample = _samples_of(report, people[0].id)[0]
    # 张三是本场景冻结人口 → ELIGIBLE；低质量值未触发淘汰（D-SB-10 只记录）。
    assert sample.decision == "ELIGIBLE"
    assert "0.1" in sample.quality_observation
    assert "no acceptance threshold" in sample.quality_observation


def test_case_17_duplicate_observation_two_persons_ineligible(tmp_path):
    """同一 observation 被两个 person 主张 → 双双 INELIGIBLE（reuse violation）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    r_run, r_crun, _r_clusters = _reference_batch(
        repos, tmp_path, [("r1.jpg", [(0.9, (0, 0, 0, 1.0))])])
    shared_obs = repos.face_observations.list_by_run(r_run.id)[0]
    cluster_a = FaceCluster(cluster_run_id=r_crun.id, run_id=r_run.id,
                            ordinal=0, member_count=1, sort_key="~|~|0")
    cluster_b = FaceCluster(cluster_run_id=r_crun.id, run_id=r_run.id,
                            ordinal=1, member_count=1, sort_key="~|~|1")
    repos.face_clusters.add_clusters([cluster_a, cluster_b])
    repos.face_clusters.add_members([
        FaceClusterMember(cluster_id=cluster_a.id, observation_id=shared_obs.id),
        FaceClusterMember(cluster_id=cluster_b.id, observation_id=shared_obs.id),
    ])
    _guard(repos).confirm_reference_cluster(
        r_crun.id, {cluster_a.id}, people[0].id,
        _evaluation_dataset_id(repos), VERSION)
    _guard(repos).confirm_reference_cluster(
        r_crun.id, {cluster_b.id}, people[1].id,
        _evaluation_dataset_id(repos), VERSION)
    report, _by_pfe = _evaluate(repos, r_run, r_crun)
    dup = [s for s in report.samples
           if s.person_id in (people[0].id, people[1].id)]
    assert len(dup) == 2
    assert all(s.decision == "INELIGIBLE" for s in dup)
    assert all(any(c.name == "C-duplicate-reuse" and not c.passed
                   for c in s.checks) for s in dup)


def test_case_owner_gate_mixed_provenance(tmp_path):
    """识别 run ∈ 指定集合但聚类 run ∉ 指定集合 → OWNER-GATE（证据不足）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _run, _e_crun, _e_clusters, people = _build_three_person_evaluation(repos, tmp_path)
    r_run, r_crun, _r_clusters = _reference_batch(
        repos, tmp_path, [("r1.jpg", [(0.9, (0, 0, 0, 1.0))])])
    # 指定集不完整（聚类 run 未指定）：混合/缺失溯源不得静默放行。
    r2_run, r2_crun, r2_clusters = _reference_batch(
        repos, tmp_path, [("r2.jpg", [(0.9, (1.0, 1.0, 0, 0))])])
    person = _person_id(repos, "张三")
    _guard(repos).confirm_reference_cluster(
        r2_crun.id, {r2_clusters[0].id}, person,
        _evaluation_dataset_id(repos), VERSION)
    samples, _unreadable = _eligibility(repos).evaluate_samples(
        _evaluation_dataset_id(repos), VERSION, {r_run.id, r2_run.id}, {r_crun.id})
    sample = [s for s in samples if s.person_id == person
              and s.observation_id in {o.id for o in
                  repos.face_observations.list_by_run(r2_run.id)}][0]
    assert sample.decision == "OWNER-GATE"
    assert any(c.name == "E-01-reference-source" and not c.passed
               for c in sample.checks)
