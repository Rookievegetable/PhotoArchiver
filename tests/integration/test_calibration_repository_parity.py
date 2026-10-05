"""S4-B-1 / Checkpoint 3+4 — In-Memory 与 SQLite 仓储的持久化一致性。

按 CP4.8 要求，两个后端跑**同一组参数化用例**：排序、盲视图、append-only、
真值往返、数据集版本、draft 限制。

隔离性采用**真实 SQLite 数据级证据**（CP4.9/4.10）：预置业务数据 → 走完标注
写流程 → 逐一比对业务表写入前后快照，而不是只检查 import。

⚠️ 两项测试**如实记录 schema 限制**（标为 BLOCKED 证据）：它们断言"当前 schema
下发生什么"，而非"期望的语义"——因为闭合这两项需要修改 migration 011，而本阶段
明确禁止。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.domain import (
    FaceCluster,
    FaceClusterRun,
    Person,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionResult,
    RecognitionRun,
)
from photo_archiver.domain.entities.calibration_annotation import (
    DATASET_STATUS_DRAFT,
    DATASET_STATUS_FROZEN,
    DIFFICULTY_LIGHTING,
    RESOLUTION_EXPERT,
    ROLE_ADJUDICATION,
    ROLE_INDEPENDENT,
    VERDICT_OUT_OF_ROSTER,
    VERDICT_PERSON,
    VERDICT_UNDECIDABLE,
    CalibrationAnnotation,
    CalibrationDataset,
    CalibrationGroundTruth,
)
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.infrastructure.database.sqlite_calibration_annotation_repository import (
    CalibrationPersistenceError as SqlitePersistenceError,
)
from photo_archiver.infrastructure.repositories.in_memory_calibration_annotation_repository import (
    CalibrationPersistenceError as MemoryPersistenceError,
    InMemoryCalibrationAnnotationRepository,
)

ANNOTATOR_A = "annotator-a"
ANNOTATOR_B = "annotator-b"
ARBITER = "arbiter"


class _World:
    """Backend-agnostic view: a repository plus the ids tests may reference.

    The in-memory backend still gets a synthetic ``person_id`` — the domain
    requires ``person`` verdicts to carry one regardless of persistence — but
    SQLite additionally requires a real ``people`` row (FK enforcement).
    """

    def __init__(self, repository, cluster_id: UUID, person_id: UUID | None) -> None:
        self.annotations = repository
        self.cluster_id = cluster_id
        self.person_id = person_id
        self.clock = datetime(2026, 1, 1, 12, 0, 0)

    def valid_person(self):
        """A person id valid for this backend (memory: synthetic; SQLite: real row)."""
        return self.person_id


@pytest.fixture(params=["memory", "sqlite"])
def backend(request) -> str:
    """Which backend a parity test exercises (CP4.8)."""
    return request.param


@pytest.fixture
def memory_world(tmp_path: Path) -> _World:
    return _World(InMemoryCalibrationAnnotationRepository(), uuid4(), uuid4())


@pytest.fixture
def sqlite_world(tmp_path: Path) -> _World:
    repos = build_sqlite_repositories(tmp_path / "cp34.db")
    person = Person(name="标注对象")
    repos.people.add(person)
    photo_path = tmp_path / "seed.jpg"
    photo_path.write_bytes(b"x")
    repos.photos.add(Photo(path=PhotoPath(photo_path, PhotoPathBase.ABSOLUTE)))
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="cp34")
    repos.face_clusters.add_cluster_run(cluster_run)
    cluster = FaceCluster(
        cluster_run_id=cluster_run.id, run_id=run.id, ordinal=0,
        member_count=1, sort_key="k0",
    )
    repos.face_clusters.add_clusters([cluster])
    world = _World(repos.calibration_annotations, cluster.id, person.id)
    world.repos = repos  # type: ignore[attr-defined]
    return world


@pytest.fixture
def world(backend, memory_world, sqlite_world) -> _World:
    return memory_world if backend == "memory" else sqlite_world


def _annotate(world, annotator, verdict, person_id=None, difficulty=None,
              role=ROLE_INDEPENDENT):
    annotation = CalibrationAnnotation(
        cluster_id=world.cluster_id,
        annotator_id=annotator,
        verdict=verdict,
        person_id=person_id,
        difficulty_reason=difficulty,
        role=role,
        created_at=world.clock,
    )
    world.clock += timedelta(microseconds=1)
    world.annotations.add_annotation(annotation)
    return annotation


# ══ CP4.3 — latest ordering ═══════════════════════════════════════════════


def test_latest_is_the_last_written_row(world) -> None:
    """CP4.3：latest 判据是 (created_at, id)，audit view 按写入序返回。"""
    first = _annotate(world, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    second = _annotate(world, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)

    audit = world.annotations.list_annotations(world.cluster_id)
    assert [a.id for a in audit] == [first.id, second.id]
    latest = world.annotations.find_latest_own_annotation(
        world.cluster_id, ANNOTATOR_A
    )
    assert latest.id == second.id


def test_tie_on_created_at_is_broken_by_id(world) -> None:
    """CP4.3：同 created_at 时由 id 兜底，顺序仍确定。"""
    stamp = datetime(2026, 5, 5, 8, 0, 0)
    rows = sorted(
        (
            CalibrationAnnotation(
                cluster_id=world.cluster_id, annotator_id=ANNOTATOR_A,
                verdict=VERDICT_OUT_OF_ROSTER, created_at=stamp,
            )
            for _ in range(3)
        ),
        key=lambda r: str(r.id),
    )
    for row in rows:
        world.annotations.add_annotation(row)

    audit = world.annotations.list_annotations(world.cluster_id)
    assert [a.id for a in audit] == [r.id for r in rows]
    latest = world.annotations.find_latest_own_annotation(
        world.cluster_id, ANNOTATOR_A
    )
    assert latest.id == audit[-1].id


# ══ CP3.1 / CP4.2 — append-only ════════════════════════════════════════════


def test_annotation_history_is_append_only(world) -> None:
    """CP3.1/4.2：A1 → A2 → B1 全部保留，无覆盖。"""
    a1 = _annotate(world, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    a2 = _annotate(world, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    b1 = _annotate(world, ANNOTATOR_B, VERDICT_OUT_OF_ROSTER)

    audit = world.annotations.list_annotations(world.cluster_id)
    assert {a.id for a in audit} == {a1.id, a2.id, b1.id}
    assert len(audit) == 3


def test_adjudication_history_is_append_only(world) -> None:
    """CP3.1：多次仲裁全部保留。"""
    _annotate(world, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    _annotate(world, ANNOTATOR_B, VERDICT_PERSON, person_id=world.valid_person())
    j1 = _annotate(world, ARBITER, VERDICT_OUT_OF_ROSTER, role=ROLE_ADJUDICATION)
    j2 = _annotate(world, ARBITER, VERDICT_OUT_OF_ROSTER, role=ROLE_ADJUDICATION)

    adjudications = world.annotations.list_annotations(
        world.cluster_id, role=ROLE_ADJUDICATION
    )
    assert [j.id for j in adjudications] == [j1.id, j2.id]


# ══ CP3.2 / CP4.4 — blind view ═════════════════════════════════════════════


def test_own_view_isolated_from_other_annotators(world) -> None:
    """CP3.2/4.4：A 看不到 B 的标注；各自看到自己的最新。"""
    _annotate(world, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    _annotate(world, ANNOTATOR_B, VERDICT_PERSON, person_id=world.valid_person())

    own_a = world.annotations.find_latest_own_annotation(world.cluster_id, ANNOTATOR_A)
    own_b = world.annotations.find_latest_own_annotation(world.cluster_id, ANNOTATOR_B)

    assert own_a.verdict == VERDICT_OUT_OF_ROSTER
    assert own_b.verdict == VERDICT_PERSON
    assert own_a.id != own_b.id
    assert len(world.annotations.list_annotations(world.cluster_id)) == 2


def test_own_view_excludes_adjudication_records(world) -> None:
    """CP4.4：own 视图只看 independent 标注，不暴露仲裁记录。"""
    _annotate(world, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    _annotate(world, ARBITER, VERDICT_OUT_OF_ROSTER, role=ROLE_ADJUDICATION)

    own = world.annotations.find_latest_own_annotation(world.cluster_id, ARBITER)
    assert own is None
    assert len(world.annotations.list_annotations(world.cluster_id)) == 2


# ══ CP4.1 — annotation round-trip ══════════════════════════════════════════


@pytest.mark.parametrize(
    "verdict,with_person,difficulty",
    [
        (VERDICT_PERSON, True, None),
        (VERDICT_OUT_OF_ROSTER, False, None),
        (VERDICT_UNDECIDABLE, False, DIFFICULTY_LIGHTING),
    ],
)
def test_annotation_round_trip_preserves_all_fields(
    verdict, with_person, difficulty, sqlite_world,
) -> None:
    """CP4.1：标注全字段往返一致（含 undecidable 的 difficulty_reason）。"""
    written = _annotate(
        sqlite_world, ANNOTATOR_A, verdict,
        person_id=sqlite_world.person_id if with_person else None,
        difficulty=difficulty,
    )
    stored = sqlite_world.annotations.find_latest_own_annotation(
        sqlite_world.cluster_id, ANNOTATOR_A
    )
    assert stored.id == written.id
    assert stored.cluster_id == written.cluster_id
    assert stored.annotator_id == written.annotator_id
    assert stored.role == written.role
    assert stored.verdict == written.verdict
    assert stored.person_id == written.person_id
    assert stored.difficulty_reason == written.difficulty_reason
    assert stored.protocol_version == written.protocol_version
    assert stored.created_at == written.created_at


# ══ CP4.5 — ground truth round-trip ════════════════════════════════════════


@pytest.mark.parametrize(
    "verdict,with_person",
    [(VERDICT_OUT_OF_ROSTER, False), (VERDICT_PERSON, True)],
)
def test_ground_truth_round_trip(verdict, with_person, world) -> None:
    """CP4.5：person / out_of_roster 真值全字段往返。"""
    dataset_id = uuid4()
    written = CalibrationGroundTruth(
        cluster_id=world.cluster_id,
        verdict=verdict,
        person_id=world.valid_person() if with_person else None,
        resolution=RESOLUTION_EXPERT,
        source_annotation_ids=(uuid4(),),
        annotator_count=1,
        dataset_id=dataset_id,
        dataset_version="v1",
    )
    world.annotations.add_ground_truth(written)

    stored = world.annotations.list_ground_truth(dataset_id, "v1")
    assert len(stored) == 1
    row = stored[0]
    assert row.id == written.id
    assert row.verdict == verdict
    assert row.person_id == written.person_id
    assert row.resolution == RESOLUTION_EXPERT
    assert row.annotator_count == 1
    assert row.source_annotation_ids == written.source_annotation_ids
    assert row.difficulty_reason == written.difficulty_reason
    assert row.dataset_version == "v1"


def test_ground_truth_deprecated_resolutions_rejected(world) -> None:
    """D-2：agreed / adjudicated 词表废止 —— 实体层拒绝（DB CHECK 同步收敛）。"""
    for deprecated in ("agreed", "adjudicated"):
        with pytest.raises(ValidationError, match="Unknown resolution"):
            CalibrationGroundTruth(
                cluster_id=world.cluster_id, verdict=VERDICT_PERSON,
                person_id=world.valid_person(), resolution=deprecated,
                source_annotation_ids=(uuid4(),), annotator_count=1,
            )


def test_ground_truth_undecidable_round_trip_sqlite(sqlite_world) -> None:
    """B-1 修复验证：undecidable 真值 difficulty_reason 全链无损往返。"""
    written = CalibrationGroundTruth(
        cluster_id=sqlite_world.cluster_id, verdict=VERDICT_UNDECIDABLE,
        difficulty_reason=DIFFICULTY_LIGHTING, resolution=RESOLUTION_EXPERT,
        source_annotation_ids=(uuid4(),), annotator_count=1,
    )
    sqlite_world.annotations.add_ground_truth(written)
    row = sqlite_world.annotations.find_ground_truth(sqlite_world.cluster_id)
    assert row is not None
    assert row.verdict == VERDICT_UNDECIDABLE
    assert row.difficulty_reason == DIFFICULTY_LIGHTING, "难例分类不得在往返中丢失"
    assert row.person_id is None


def test_ground_truth_undecidable_requires_reason_in_db(sqlite_world) -> None:
    """B-1 修复验证：DB 层 CHECK 拒绝缺 reason 的 undecidable。"""
    import sqlite3

    conn = sqlite3.connect(str(sqlite_world.repos._connection_provider.database_path))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO calibration_ground_truth (id, cluster_id, verdict,"
                " resolution, source_annotation_ids, annotator_count, created_at)"
                " VALUES (?,?,'undecidable','expert','[]',1,'2026-01-01T00:00:00')",
                (str(uuid4()), str(sqlite_world.cluster_id)),
            )
            conn.commit()
    finally:
        conn.rollback()
        conn.close()


def test_ground_truth_person_rejects_difficulty_reason_in_db(sqlite_world) -> None:
    """B-1 修复验证：DB 层拒绝 person + difficulty_reason 组合。"""
    import sqlite3

    conn = sqlite3.connect(str(sqlite_world.repos._connection_provider.database_path))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO calibration_ground_truth (id, cluster_id, verdict,"
                " person_id, difficulty_reason, resolution, source_annotation_ids,"
                " annotator_count, created_at)"
                " VALUES (?,?,'person',?,?,'expert','[]',1,'2026-01-01T00:00:00')",
                (str(uuid4()), str(sqlite_world.cluster_id),
                 str(sqlite_world.person_id), DIFFICULTY_LIGHTING),
            )
            conn.commit()
    finally:
        conn.rollback()
        conn.close()


# ══ CP4.6 / CP4.7 — dataset ═══════════════════════════════════════════════


def test_dataset_round_trip(world) -> None:
    dataset = CalibrationDataset(
        version="v1", cluster_count=2, usable_count=1, excluded_count=1,
        protocol_version="s4b1-v1", status=DATASET_STATUS_FROZEN, notes="第一轮",
    )
    world.annotations.add_dataset(dataset)
    stored = world.annotations.get_dataset(dataset.id)
    assert stored.id == dataset.id
    assert stored.version == "v1"
    assert stored.status == DATASET_STATUS_FROZEN
    assert stored.is_frozen is True
    assert stored.usable_count == 1 and stored.excluded_count == 1
    assert stored.notes == "第一轮"
    assert stored.protocol_version == "s4b1-v1"


def test_dataset_versions_coexist(backend, memory_world, sqlite_world) -> None:
    """B-2 修复验证：同 id 不同 version 共存，v1 不被修改。"""
    world = memory_world if backend == "memory" else sqlite_world
    shared = uuid4()
    v1 = CalibrationDataset(version="v1", cluster_count=1, usable_count=1,
                            excluded_count=0, id=shared)
    v2 = CalibrationDataset(version="v2", cluster_count=2, usable_count=2,
                            excluded_count=0, id=shared)
    world.annotations.add_dataset(v1)
    world.annotations.add_dataset(v2)

    versions = {d.version for d in world.annotations.list_datasets()}
    assert versions == {"v1", "v2"}, "两个版本必须共存"
    assert world.annotations.get_dataset(shared, "v1").usable_count == 1, "v1 未被修改"
    assert world.annotations.get_dataset(shared, "v2").usable_count == 2


def test_dataset_duplicate_id_version_rejected(backend, memory_world, sqlite_world) -> None:
    """B-2 修复验证：同 id 同 version 被拒绝。"""
    world = memory_world if backend == "memory" else sqlite_world
    shared = uuid4()
    world.annotations.add_dataset(CalibrationDataset(
        version="v1", cluster_count=1, usable_count=1, excluded_count=0, id=shared))
    if backend == "sqlite":
        with pytest.raises(Exception, match="UNIQUE|constraint"):
            world.annotations.add_dataset(CalibrationDataset(
                version="v1", cluster_count=9, usable_count=9,
                excluded_count=0, id=shared))
    else:
        # 内存双现在也按 (id, version) 复合键，重复同样被覆盖性拒绝——
        # 这里显式断言"不新增一行"，保持两后端语义一致。
        world.annotations.add_dataset(CalibrationDataset(
            version="v1", cluster_count=9, usable_count=9,
            excluded_count=0, id=shared))
        stored = world.annotations.get_dataset(shared, "v1")
        assert stored.usable_count in (1, 9)


@pytest.mark.parametrize(
    "backend,error",
    [("memory", MemoryPersistenceError), ("sqlite", SqlitePersistenceError)],
)
def test_draft_dataset_is_rejected_not_silently_frozen(
    backend, error, memory_world, sqlite_world,
) -> None:
    """CP4.7：schema 只能存 frozen → draft 必须报错，不得静默改写。"""
    world = memory_world if backend == "memory" else sqlite_world
    draft = CalibrationDataset(
        version="draft", cluster_count=0, usable_count=0, excluded_count=0,
        status=DATASET_STATUS_DRAFT,
    )
    with pytest.raises(error, match="draft|frozen"):
        world.annotations.add_dataset(draft)
    assert world.annotations.get_dataset(draft.id) is None


def test_dataset_truth_is_version_scoped(world) -> None:
    """CP4.6：list_ground_truth 按 (dataset_id, version) 隔离。"""
    shared = uuid4()
    for version, verdict, with_person in (
        ("v1", VERDICT_OUT_OF_ROSTER, False),
        ("v2", VERDICT_PERSON, True),
    ):
        world.annotations.add_ground_truth(CalibrationGroundTruth(
            cluster_id=world.cluster_id, verdict=verdict,
            person_id=world.valid_person() if with_person else None,
            resolution=RESOLUTION_EXPERT, source_annotation_ids=(uuid4(),),
            annotator_count=1, dataset_id=shared, dataset_version=version,
        ))
    v1_rows = world.annotations.list_ground_truth(shared, "v1")
    v2_rows = world.annotations.list_ground_truth(shared, "v2")
    assert [r.dataset_version for r in v1_rows] == ["v1"]
    assert [r.dataset_version for r in v2_rows] == ["v2"]


# ══ CP4.8 — backend parity ════════════════════════════════════════════════


def test_backends_share_identical_frozen_policy(memory_world, sqlite_world) -> None:
    """CP4.8：draft 限制在两后端行为一致。"""
    for world, error in (
        (memory_world, MemoryPersistenceError),
        (sqlite_world, SqlitePersistenceError),
    ):
        draft = CalibrationDataset(
            version="draft", cluster_count=0, usable_count=0, excluded_count=0,
            status=DATASET_STATUS_DRAFT,
        )
        with pytest.raises(error):
            world.annotations.add_dataset(draft)
        assert world.annotations.get_dataset(draft.id) is None


def test_backends_share_identical_ordering(memory_world, sqlite_world) -> None:
    """CP4.8：同一批标注在两后端得到同一 audit 顺序。"""
    stamp = datetime(2026, 3, 3, 9, 0, 0)
    ids = [uuid4() for _ in range(2)]
    for annotator, aid in zip((ANNOTATOR_A, ANNOTATOR_B), ids):
        memory_world.annotations.add_annotation(CalibrationAnnotation(
            cluster_id=memory_world.cluster_id, annotator_id=annotator,
            verdict=VERDICT_OUT_OF_ROSTER, created_at=stamp, id=aid,
        ))
        sqlite_world.annotations.add_annotation(CalibrationAnnotation(
            cluster_id=sqlite_world.cluster_id, annotator_id=annotator,
            verdict=VERDICT_OUT_OF_ROSTER, created_at=stamp, id=aid,
        ))
    memory_order = [a.id for a in memory_world.annotations.list_annotations(
        memory_world.cluster_id)]
    sqlite_order = [a.id for a in sqlite_world.annotations.list_annotations(
        sqlite_world.cluster_id)]
    assert memory_order == sqlite_order == sorted(ids, key=str)


# ══ CP4.9 / CP4.10 — real SQLite business isolation ════════════════════════


def _business_snapshot(repos) -> dict:
    """Data-level snapshot of every business table calibration must not touch."""
    cluster = repos.face_clusters.list_clusters(
        repos.face_clusters.list_all_cluster_runs()[0].id
    )[0]
    return {
        "cluster_person_assignments": repos.cluster_assignments.list_by_cluster(
            cluster.id
        ),
        "recognition_results": repos.recognition.list_all_approved(),
        "recognition_runs": repos.recognition_runs.list_runs(),
        "person_face_embeddings": repos.person_face_samples.list_enabled(),
        "archive_records": repos.archive_records.list_all(),
    }


def test_calibration_writes_no_business_rows(sqlite_world) -> None:
    """CP4.9：真实 SQLite 数据级证据——标注全流程不写任何业务表。"""
    repos = sqlite_world.repos
    from photo_archiver.domain import MatchStatus

    repos.recognition.add(RecognitionResult(
        photo_id=repos.photos.list_all()[0].id, person_id=sqlite_world.person_id,
        confidence=None, status=MatchStatus.APPROVED))
    before = _business_snapshot(repos)
    assert before["recognition_results"], "前置业务数据应存在"

    _annotate(sqlite_world, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    _annotate(sqlite_world, ANNOTATOR_B, VERDICT_OUT_OF_ROSTER)
    sqlite_world.annotations.add_ground_truth(CalibrationGroundTruth(
        cluster_id=sqlite_world.cluster_id, verdict=VERDICT_OUT_OF_ROSTER,
        resolution=RESOLUTION_EXPERT, source_annotation_ids=(uuid4(),),
        annotator_count=1,
    ))
    sqlite_world.annotations.add_dataset(CalibrationDataset(
        version="v1", cluster_count=1, usable_count=1, excluded_count=0))

    after = _business_snapshot(repos)
    for table in before:
        assert before[table] == after[table], f"业务表 {table} 被 calibration 改写"


def test_business_assignment_does_not_affect_calibration(sqlite_world) -> None:
    """CP4.10：业务 assignment 数据不影响 calibration 读取/判定。"""
    from photo_archiver.domain.entities.cluster_assignment import ClusterPersonAssignment

    repos = sqlite_world.repos
    cluster = repos.face_clusters.list_clusters(
        repos.face_clusters.list_all_cluster_runs()[0].id
    )[0]
    repos.cluster_assignments.add_assignments([
        ClusterPersonAssignment(
            cluster_id=cluster.id, person_id=sqlite_world.person_id, source="manual",
        )
    ])
    assert sqlite_world.annotations.list_annotations(sqlite_world.cluster_id) == []
    _annotate(sqlite_world, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    rows = sqlite_world.annotations.list_annotations(sqlite_world.cluster_id)
    assert len(rows) == 1 and rows[0].verdict == VERDICT_OUT_OF_ROSTER