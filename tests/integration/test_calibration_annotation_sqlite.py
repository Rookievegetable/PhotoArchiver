"""S4-B-1 SQLite 仓储层测试：真实数据库下的持久化、排序与隔离性。

与 in-memory 双（``test_calibration_annotation_service.py``）互补——后者验证
生命周期语义，本文件验证：

* 三张表的 append-only 行为在真实 SQL 约束下成立；
* ``list_annotations`` / ``find_latest_own_annotation`` 的排序与盲标注视图；
* **Checkpoint 10 #9/#10**：标注全流程在真实数据库中不写任何业务表。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest


from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.services.calibration_annotation_service import (
    CalibrationAnnotationService,
)
from photo_archiver.domain import FaceCluster, FaceClusterRun, Person, Photo, RecognitionRun
from photo_archiver.domain.entities.calibration_annotation import (
    DIFFICULTY_LIGHTING,
    ROLE_ADJUDICATION,
    ROLE_INDEPENDENT,
    VERDICT_OUT_OF_ROSTER,
    VERDICT_PERSON,
    VERDICT_UNDECIDABLE,
)
from photo_archiver.domain.value_objects import PhotoPath, PhotoPathBase


def _world(tmp_path: Path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    service = CalibrationAnnotationService(repos.calibration_annotations)
    human = Person(name="真值对象")
    repos.people.add(human)

    path = tmp_path / "seed.jpg"
    path.write_bytes(b"x")
    photo = Photo(path=PhotoPath(path, PhotoPathBase.ABSOLUTE))
    repos.photos.add(photo)

    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="s4b1")
    repos.face_clusters.add_cluster_run(cluster_run)
    cluster = FaceCluster(
        cluster_run_id=cluster_run.id, run_id=run.id, ordinal=0,
        member_count=1, sort_key="k0",
    )
    repos.face_clusters.add_clusters([cluster])
    return repos, service, human, cluster, photo


def test_annotation_round_trips_through_sqlite(tmp_path: Path) -> None:
    repos, service, human, cluster, photo = _world(tmp_path)
    written = service.annotate(cluster.id, "annotator-a", VERDICT_PERSON, human.id)
    stored = repos.calibration_annotations.list_annotations(cluster.id)
    assert len(stored) == 1
    assert stored[0].id == written.id
    assert stored[0].person_id == human.id
    assert stored[0].role == ROLE_INDEPENDENT
    assert stored[0].created_at == written.created_at


def test_blind_view_returns_only_own_latest(tmp_path: Path) -> None:
    """盲标注边界（Checkpoint 8）：own 视图只返回自己的最新行。"""
    repos, service, human, cluster, photo = _world(tmp_path)
    other = Person(name="他人")
    repos.people.add(other)

    service.annotate(cluster.id, "annotator-a", VERDICT_PERSON, human.id)
    service.annotate(cluster.id, "annotator-a", VERDICT_OUT_OF_ROSTER)
    service.annotate(cluster.id, "annotator-b", VERDICT_PERSON, other.id)

    own = service.latest_own_annotation(cluster.id, "annotator-a")
    assert own is not None and own.verdict == VERDICT_OUT_OF_ROSTER, (
        "own 视图返回自己的最新行"
    )
    assert service.latest_own_annotation(cluster.id, "annotator-b").person_id == other.id

    # 审计视图能看到全部（仅仲裁/报告使用）
    everything = repos.calibration_annotations.list_annotations(cluster.id)
    assert len(everything) == 3
    assert {a.annotator_id for a in everything} == {"annotator-a", "annotator-b"}


def test_role_filter_separates_independent_from_adjudication(tmp_path: Path) -> None:
    """role 过滤是仓储机制；单专家协议下服务只产出 independent，
    adjudication role 行仅可经仓储直写（历史上由已废止的仲裁路径产生）。"""
    from photo_archiver.domain.entities.calibration_annotation import CalibrationAnnotation

    repos, service, human, cluster, photo = _world(tmp_path)
    service.annotate(cluster.id, "annotator-a", VERDICT_PERSON, human.id)
    service.annotate(cluster.id, "annotator-b", VERDICT_OUT_OF_ROSTER)
    repos.calibration_annotations.add_annotation(CalibrationAnnotation(
        cluster_id=cluster.id, annotator_id="arbiter",
        verdict=VERDICT_PERSON, role=ROLE_ADJUDICATION, person_id=human.id,
    ))

    independent = repos.calibration_annotations.list_annotations(
        cluster.id, role=ROLE_INDEPENDENT
    )
    adjudications = repos.calibration_annotations.list_annotations(
        cluster.id, role=ROLE_ADJUDICATION
    )
    assert len(independent) == 2 and len(adjudications) == 1


def test_undecidable_reason_survives_to_ground_truth(tmp_path: Path) -> None:
    """难例分类必须贯通到真值行——S4-B-2 质量分层的唯一载体。"""
    repos, service, _, cluster, _photo = _world(tmp_path)
    service.annotate(
        cluster.id, "annotator-a", VERDICT_UNDECIDABLE,
        difficulty_reason=DIFFICULTY_LIGHTING,
    )
    truth = service.resolve_ground_truth(cluster.id)
    assert truth is not None
    assert truth.verdict == VERDICT_UNDECIDABLE
    assert truth.difficulty_reason == DIFFICULTY_LIGHTING
    assert repos.calibration_annotations.find_ground_truth(cluster.id) is None, (
        "未冻结前仓储中尚无真值行"
    )


def test_frozen_dataset_writes_versioned_truth_rows(tmp_path: Path) -> None:
    repos, service, human, cluster, photo = _world(tmp_path)
    service.annotate(cluster.id, "annotator-a", VERDICT_PERSON, human.id)

    dataset_id = uuid4()
    dataset = service.freeze_dataset(dataset_id, version="v1", notes="第一轮")
    assert dataset.usable_count == 1

    rows = repos.calibration_annotations.list_ground_truth(dataset_id, "v1")
    assert len(rows) == 1
    assert rows[0].dataset_id == dataset_id
    assert rows[0].dataset_version == "v1"
    assert rows[0].resolution == "expert"
    assert len(rows[0].source_annotation_ids) == 1
    assert rows[0].annotator_count == 1
    assert repos.calibration_annotations.get_dataset(dataset_id).version == "v1"


def test_annotation_never_writes_business_tables(tmp_path: Path) -> None:
    """Checkpoint 10 #9/#10：真实数据库下，业务表零写入。"""
    repos, service, human, cluster, photo = _world(tmp_path)

    # 业务链预置数据：确认"确实存在会被误写的表"
    from photo_archiver.domain import RecognitionResult

    repos.recognition.add(RecognitionResult(photo_id=photo.id, confidence=None))
    before_assignments = len(repos.cluster_assignments.list_by_cluster(cluster.id))
    before_projections = len(repos.recognition.list_projections())
    before_samples = len(repos.person_face_samples.list_by_person(human.id))
    before_archive = len(repos.archive_records.list_all())

    service.annotate(cluster.id, "annotator-a", VERDICT_PERSON, human.id)
    service.annotate(cluster.id, "annotator-b", VERDICT_PERSON, human.id)
    service.freeze_dataset(uuid4(), version="v1")

    assert len(repos.cluster_assignments.list_by_cluster(cluster.id)) == before_assignments
    assert len(repos.recognition.list_projections()) == before_projections
    assert len(repos.person_face_samples.list_by_person(human.id)) == before_samples
    assert len(repos.archive_records.list_all()) == before_archive
    assert repos.recognition.list_all_approved() == [], "标注不得产生可归档行"


def test_protocol_rejects_business_writes_by_construction() -> None:
    """结构性隔离：标注仓储契约不含任何业务仓储方法。"""
    from photo_archiver.domain.repositories.calibration_annotation_repository import (
        CalibrationAnnotationRepository,
    )

    forbidden = {
        "add", "add_many", "update_status", "remove_results_for_person_photos",
        "add_assignments", "update_assignment", "add_samples", "disable_samples",
        "list_approved_by_person", "list_projections",
    }
    declared = {
        name for name in dir(CalibrationAnnotationRepository)
        if not name.startswith("_")
    }
    assert not (declared & forbidden), (
        f"标注仓储契约泄漏业务方法: {declared & forbidden}"
    )


def test_downgrade_removes_calibration_tables(tmp_path: Path) -> None:
    """迁移可逆：downgrade 后三张 calibration 表消失，业务表不受影响。"""
    import sqlite3

    from alembic import command
    from alembic.config import Config

    db = tmp_path / "down.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    build_sqlite_repositories(db)
    _, service, human, cluster, _photo = _world(tmp_path)
    service.annotate(cluster.id, "annotator-a", VERDICT_PERSON, human.id)

    cfg = Config(str(Path("alembic.ini").resolve()))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    cfg.set_main_option("script_location", str(Path("alembic").resolve()))
    command.downgrade(cfg, "010_assignment_source_review")

    with sqlite3.connect(str(db)) as conn:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "calibration_annotations" not in tables
    assert "calibration_ground_truth" not in tables
    assert "calibration_datasets" not in tables
    assert "cluster_person_assignments" in tables and "recognition_results" in tables
    assert isinstance(human, Person) and isinstance(cluster, FaceCluster)

def test_ground_truth_check_constraints_single_expert(tmp_path: Path) -> None:
    """Migration 012 SQL 级 CHECK：resolution 词表收敛 'expert'、annotator_count=1。"""
    import sqlite3

    repos, service, human, cluster, _photo = _world(tmp_path)
    annotation = service.annotate(cluster.id, "annotator-a", VERDICT_PERSON, human.id)
    conn = sqlite3.connect(str(repos._connection_provider.database_path))

    def _gt_row(resolution: str, count: int, sources: str):
        return (
            str(uuid4()), str(cluster.id), "person", str(human.id),
            resolution, sources, count, "2026-01-01T00:00:00",
        )

    try:
        # expert + 单来源 + count=1 → 合法
        conn.execute(
            "INSERT INTO calibration_ground_truth (id, cluster_id, verdict,"
            " person_id, resolution, source_annotation_ids, annotator_count,"
            " created_at) VALUES (?,?,?,?,?,?,?,?)",
            _gt_row("expert", 1, f'["{annotation.id}"]'),
        )
        conn.commit()
        # 废止词表在 DB 层拒绝
        for deprecated in ("agreed", "adjudicated"):
            with pytest.raises(sqlite3.IntegrityError, match="resolution"):
                conn.execute(
                    "INSERT INTO calibration_ground_truth (id, cluster_id, verdict,"
                    " person_id, resolution, source_annotation_ids, annotator_count,"
                    " created_at) VALUES (?,?,?,?,?,?,?,?)",
                    _gt_row(deprecated, 1, f'["{annotation.id}"]'),
                )
                conn.rollback()
        # 伪造第二标注（annotator_count=2）在 DB 层拒绝
        with pytest.raises(sqlite3.IntegrityError, match="annotator_count"):
            conn.execute(
                "INSERT INTO calibration_ground_truth (id, cluster_id, verdict,"
                " person_id, resolution, source_annotation_ids, annotator_count,"
                " created_at) VALUES (?,?,?,?,?,?,?,?)",
                _gt_row("expert", 2, f'["{annotation.id}", "{uuid4()}"]'),
            )
            conn.rollback()
    finally:
        conn.close()
