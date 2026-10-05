"""S4-B-2 Ground Truth 单专家协议验收测试（D-2 = Single Human Expert）。

对应任务的验收项，全部使用**独立 in-memory 仓储**（domain/service 层）
或**真实 SQLite**（仓储隔离性），确保"标注不污染业务链"是可执行断言而非声明。

旧双标协议（≥2 人一致 / 仲裁）已废止：不存在 agreement/adjudication 路径，
单条专家标注直接构成真值（resolution='expert'）。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.services.calibration_annotation_service import (
    CalibrationAnnotationService,
)
from photo_archiver.domain.entities.calibration_annotation import (
    DIFFICULTY_BLUR,
    DIFFICULTY_OCCLUSION,
    RESOLUTION_EXPERT,
    ROLE_INDEPENDENT,
    VERDICT_OUT_OF_ROSTER,
    VERDICT_PERSON,
    VERDICT_UNDECIDABLE,
    CalibrationGroundTruth,
)
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.infrastructure.repositories.in_memory_calibration_annotation_repository import (
    InMemoryCalibrationAnnotationRepository,
)

ANNOTATOR_A = "annotator-a"
ANNOTATOR_B = "annotator-b"


@pytest.fixture
def service() -> CalibrationAnnotationService:
    return CalibrationAnnotationService(InMemoryCalibrationAnnotationRepository())


@pytest.fixture
def cluster_id():
    return uuid4()


@pytest.fixture
def other_cluster_id():
    return uuid4()


def _person():
    return uuid4()


# ── 1. 同一 Cluster 可追加多条标注（append-only）───────────────────────────


def test_same_cluster_accepts_multiple_annotations(service, cluster_id) -> None:
    """重新标注 = 追加新行；role 恒为 independent（仲裁角色已随旧协议废止）。"""
    first = service.annotate(cluster_id, ANNOTATOR_A, VERDICT_PERSON, _person())
    second = service.annotate(cluster_id, ANNOTATOR_B, VERDICT_PERSON, _person())
    assert first.id != second.id
    assert first.role == ROLE_INDEPENDENT and second.role == ROLE_INDEPENDENT
    assert len(service.store.list_annotations(cluster_id)) == 2


# ── 2. 历史不会被覆盖，最新行是当前答案 ────────────────────────────────────


def test_repeat_annotation_appends_history_and_latest_wins(
    service, cluster_id,
) -> None:
    service.annotate(cluster_id, ANNOTATOR_A, VERDICT_PERSON, _person())
    service.annotate(cluster_id, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    # 历史保留两行；真值取该簇最新一行。
    rows = service.store.list_annotations(cluster_id)
    assert len(rows) == 2
    truth = service.resolve_ground_truth(cluster_id)
    assert truth is not None
    assert truth.verdict == VERDICT_OUT_OF_ROSTER
    assert truth.source_annotation_ids == (rows[-1].id,)
    assert truth.annotator_count == 1
    assert truth.resolution == RESOLUTION_EXPERT


# ── 3. 单条专家标注直接构成 Ground Truth ────────────────────────────────────


def test_single_annotation_becomes_ground_truth(service, cluster_id) -> None:
    """D-2 核心：1 Annotation → GroundTruth（无需第二标注员/仲裁）。"""
    annotation = service.annotate(cluster_id, ANNOTATOR_A, VERDICT_PERSON, _person())
    truth = service.resolve_ground_truth(cluster_id)
    assert truth is not None
    assert truth.resolution == RESOLUTION_EXPERT
    assert truth.annotator_count == 1
    assert truth.source_annotation_ids == (annotation.id,)
    assert truth.verdict == VERDICT_PERSON


def test_unannotated_cluster_yields_no_truth(service, cluster_id) -> None:
    assert service.resolve_ground_truth(cluster_id) is None


def test_ground_truth_rejects_forged_multi_source(cluster_id) -> None:
    """不得伪造第二 source annotation / 第二标注员通过校验。"""
    with pytest.raises(ValidationError, match="exactly one annotation"):
        CalibrationGroundTruth(
            cluster_id=cluster_id,
            verdict=VERDICT_PERSON,
            person_id=_person(),
            resolution=RESOLUTION_EXPERT,
            source_annotation_ids=(uuid4(), uuid4()),
            annotator_count=2,
        )
    with pytest.raises(ValidationError, match="explicit source annotations"):
        CalibrationGroundTruth(
            cluster_id=cluster_id,
            verdict=VERDICT_PERSON,
            person_id=_person(),
            resolution=RESOLUTION_EXPERT,
            source_annotation_ids=(),
            annotator_count=1,
        )


# ── 4. 未标注的簇不进入 Frozen Dataset ──────────────────────────────────────


def test_unlabeled_clusters_are_not_entered_into_dataset(
    service, cluster_id,
) -> None:
    """未标注的簇甚至不参与统计——freeze 只遍历已标注簇。"""
    dataset = service.freeze_dataset(uuid4(), version="v1")
    assert (dataset.cluster_count, dataset.usable_count, dataset.excluded_count) == (0, 0, 0)


def test_annotated_cluster_enters_dataset_as_expert_truth(
    service, cluster_id,
) -> None:
    service.annotate(cluster_id, ANNOTATOR_A, VERDICT_PERSON, _person())
    dataset = service.freeze_dataset(uuid4(), version="v1")
    assert (dataset.cluster_count, dataset.usable_count, dataset.excluded_count) == (1, 1, 0)
    truths = service.dataset_truth(dataset.id, "v1")
    assert len(truths) == 1 and truths[0].resolution == RESOLUTION_EXPERT


# ── 5. undecidable 不会被误算为 positive/negative ───────────────────────────


def test_undecidable_requires_reason_and_is_not_a_negative(
    service, cluster_id,
) -> None:
    with pytest.raises(ValidationError, match="requires a difficulty_reason"):
        service.annotate(cluster_id, ANNOTATOR_A, VERDICT_UNDECIDABLE)

    service.annotate(
        cluster_id, ANNOTATOR_A, VERDICT_UNDECIDABLE,
        difficulty_reason=DIFFICULTY_OCCLUSION,
    )
    truth = service.resolve_ground_truth(cluster_id)
    assert truth is not None
    assert truth.verdict == VERDICT_UNDECIDABLE
    assert truth.person_id is None
    assert truth.difficulty_reason == DIFFICULTY_OCCLUSION


def test_reannotation_undecidable_to_person_updates_truth(
    service, cluster_id,
) -> None:
    service.annotate(cluster_id, ANNOTATOR_A, VERDICT_UNDECIDABLE,
                     difficulty_reason=DIFFICULTY_BLUR)
    person = _person()
    service.annotate(cluster_id, ANNOTATOR_A, VERDICT_PERSON, person)
    truth = service.resolve_ground_truth(cluster_id)
    assert truth is not None
    assert truth.verdict == VERDICT_PERSON and truth.person_id == person


# ── 6. out_of_roster 不会被误算成某个 Person ────────────────────────────────


def test_out_of_roster_carries_no_person(service, cluster_id) -> None:
    with pytest.raises(ValidationError, match="must not carry a person_id"):
        service.annotate(
            cluster_id, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER, person_id=_person()
        )
    service.annotate(cluster_id, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    truth = service.resolve_ground_truth(cluster_id)
    assert truth is not None and truth.verdict == VERDICT_OUT_OF_ROSTER
    assert truth.person_id is None


# ── 7. 同一照片多个 Cluster 可独立标注 ──────────────────────────────────────


def test_clusters_of_same_photo_annotated_independently(service) -> None:
    """簇级标注：同照片的两个簇互不影响，也不互相推断。"""
    photo_cluster_1, photo_cluster_2 = uuid4(), uuid4()
    service.annotate(photo_cluster_1, ANNOTATOR_A, VERDICT_PERSON, _person())
    service.annotate(photo_cluster_2, ANNOTATOR_B, VERDICT_OUT_OF_ROSTER)

    truth_1 = service.resolve_ground_truth(photo_cluster_1)
    truth_2 = service.resolve_ground_truth(photo_cluster_2)
    assert truth_1 is not None and truth_1.verdict == VERDICT_PERSON
    assert truth_2 is not None and truth_2.verdict == VERDICT_OUT_OF_ROSTER


# ── 8/9. Ground Truth 不会创建 Business Assignment，也不触发归档 ────────────


def test_ground_truth_flow_creates_no_business_rows(tmp_path: Path) -> None:
    """隔离性（真实 SQLite）：标注全流程不写任何业务表。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    service = CalibrationAnnotationService(repos.calibration_annotations)

    from photo_archiver.domain import Person

    human = Person(name="标注对象")
    repos.people.add(human)

    cluster = _seed_cluster(repos)

    service.annotate(cluster.id, ANNOTATOR_A, VERDICT_PERSON, human.id)
    service.freeze_dataset(uuid4(), version="v1")

    assert len(repos.cluster_assignments.list_by_cluster(cluster.id)) == 0, (
        "标注不得创建业务 Assignment"
    )
    assert repos.recognition.list_projections() == []
    assert repos.recognition.list_all_approved() == []
    assert repos.person_face_samples.list_by_person(human.id) == []
    assert repos.archive_records.list_all() == []


def _seed_cluster(repos):
    """建一个最小可用的 FaceCluster（需 run → observations → cluster）。"""
    from datetime import datetime

    from photo_archiver.domain import FaceCluster, FaceClusterRun
    from photo_archiver.domain import RecognitionRun
    from photo_archiver.domain import Photo, PhotoPath, PhotoPathBase

    path = Path(repos._connection_provider.database_path).parent / "seed.jpg"
    path.write_bytes(b"x")
    photo = Photo(path=PhotoPath(path, PhotoPathBase.ABSOLUTE))
    repos.photos.add(photo)

    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run = FaceClusterRun(
        recognition_run_id=run.id, algorithm_version="calib-seed"
    )
    repos.face_clusters.add_cluster_run(cluster_run)
    cluster = FaceCluster(
        cluster_run_id=cluster_run.id, run_id=run.id, ordinal=0,
        member_count=1, sort_key="k0",
    )
    repos.face_clusters.add_clusters([cluster])
    assert cluster.created_at is None or isinstance(cluster.created_at, datetime)
    return cluster


# ── 10. 历史标注不会被覆盖 ──────────────────────────────────────────────────


def test_annotation_history_is_append_only(service, cluster_id) -> None:
    repository = service.store
    for index in range(3):
        service.annotate(cluster_id, ANNOTATOR_A, VERDICT_PERSON, _person())
        assert len(repository.list_annotations(cluster_id)) == index + 1
    assert len(repository.list_annotations(cluster_id)) == 3


# ── 11. Frozen Dataset 不允许无版本变更 ──────────────────────────────────────


def test_frozen_dataset_records_id_and_version(service, cluster_id) -> None:
    person = _person()
    service.annotate(cluster_id, ANNOTATOR_A, VERDICT_PERSON, person)
    dataset_id = uuid4()
    service.freeze_dataset(dataset_id, version="v1", notes="第一轮")

    stored = service.store.get_dataset(dataset_id)
    assert stored is not None
    assert stored.version == "v1" and stored.notes == "第一轮"
    assert stored.id == dataset_id

    truths = service.dataset_truth(dataset_id, "v1")
    assert len(truths) == 1
    assert truths[0].dataset_id == dataset_id and truths[0].dataset_version == "v1"


def test_new_version_does_not_mutate_previous_dataset(service, cluster_id) -> None:
    person = _person()
    service.annotate(cluster_id, ANNOTATOR_A, VERDICT_PERSON, person)

    first_id = uuid4()
    service.freeze_dataset(first_id, version="v1")
    first_truths = service.dataset_truth(first_id, "v1")

    # 重新标注 → 新的真值 → 冻结为新版本
    service.annotate(cluster_id, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    second_id = uuid4()
    service.freeze_dataset(second_id, version="v2")

    assert service.dataset_truth(first_id, "v1") == first_truths, (
        "旧版本数据集不可被后续标注改写"
    )
    assert len(service.dataset_truth(second_id, "v2")) == 1
    assert service.dataset_truth(second_id, "v2")[0].verdict == VERDICT_OUT_OF_ROSTER
    assert len(service.store.list_datasets()) == 2


# ── 附加：标签与载荷的耦合约束 + 身份 fail-closed 回归 ──────────────────────


def test_person_verdict_requires_person_id(service, cluster_id) -> None:
    with pytest.raises(ValidationError, match="requires a person_id"):
        service.annotate(cluster_id, ANNOTATOR_A, VERDICT_PERSON)


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_annotator_identity_fail_closed(service, cluster_id, blank) -> None:
    """上一轮身份防线回归：None/空白不得落库（None 由实体非空类型+空白校验拦截）。"""
    if blank is None:
        with pytest.raises(ValidationError):
            service.annotate(cluster_id, blank, VERDICT_OUT_OF_ROSTER)
    else:
        with pytest.raises(ValidationError, match="annotator_id"):
            service.annotate(cluster_id, blank, VERDICT_OUT_OF_ROSTER)


def test_valid_explicit_annotator_id_accepted(service, cluster_id) -> None:
    annotation = service.annotate(cluster_id, "annotator-a", VERDICT_OUT_OF_ROSTER)
    assert annotation.annotator_id == "annotator-a"


def test_annotation_is_immutable(service, cluster_id) -> None:
    annotation = service.annotate(cluster_id, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    with pytest.raises(Exception):
        annotation.verdict = VERDICT_PERSON  # type: ignore[misc]
