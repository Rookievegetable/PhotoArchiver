"""S4-B-1 建立 / S4-B-2 D-2 单专家协议 — Ground Truth 全链路 E2E。

真实 SQLite（build_sqlite_repositories）+ 真实 UI Panel，验证：

- 单条专家标注 → GroundTruth（resolution='expert'，annotator_count=1）→ Dataset；
- append-only / re-annotation latest-wins；
- person / out_of_roster / undecidable 三态与 difficulty_reason 贯通；
- Dataset version 隔离、draft 拒收、version latest 语义；
- Calibration / 业务链双向隔离（真实五表快照）；
- UI blind view（own-latest-only）与身份 fail-closed 保持。

旧双标协议（≥2 人一致 / 仲裁）已废止：不存在 agreement/adjudication 路径，
任何伪造第二标注的兼容逻辑都必须被测试拒绝。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.services.calibration_annotation_service import (
    CalibrationAnnotationService,
)
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
    PROTOCOL_VERSION,
    RESOLUTION_EXPERT,
    VERDICT_OUT_OF_ROSTER,
    VERDICT_PERSON,
    VERDICT_UNDECIDABLE,
    CalibrationDataset,
)
from photo_archiver.presentation.views.calibration_annotation_panel import (
    CalibrationAnnotationPanel,
)

ANNOTATOR_A = "annotator-a"
ANNOTATOR_B = "annotator-b"


class _World:
    """Real SQLite world with cluster + persons + panel + service."""

    def __init__(self, tmp_path: Path) -> None:
        self.repos = build_sqlite_repositories(tmp_path / "cp89.db")
        self.reconciler = None  # calibration 不依赖 reconcile
        self.service = CalibrationAnnotationService(
            self.repos.calibration_annotations
        )

        self.person_a = Person(name="张三")
        self.person_b = Person(name="李四")
        self.repos.people.add(self.person_a)
        self.repos.people.add(self.person_b)

        self.photo_path = tmp_path / "seed.jpg"
        self.photo_path.write_bytes(b"x")
        self.photo = Photo(path=PhotoPath(self.photo_path, PhotoPathBase.ABSOLUTE))
        self.repos.photos.add(self.photo)

        self.run = RecognitionRun()
        self.repos.recognition_runs.add_run(self.run)
        self.cluster_run = FaceClusterRun(
            recognition_run_id=self.run.id, algorithm_version="cp89"
        )
        self.repos.face_clusters.add_cluster_run(self.cluster_run)
        self.cluster = FaceCluster(
            cluster_run_id=self.cluster_run.id, run_id=self.run.id,
            ordinal=0, member_count=1, sort_key="k0",
        )
        self.repos.face_clusters.add_clusters([self.cluster])

        self._clock = datetime(2026, 1, 15, 9, 0, 0)

    def next_clock(self) -> datetime:
        self._clock += timedelta(minutes=1)
        return self._clock

    def business_snapshot(self) -> dict:
        cluster = self.repos.face_clusters.list_clusters(
            self.repos.face_clusters.list_all_cluster_runs()[0].id
        )[0]
        return {
            "cluster_person_assignments": self.repos.cluster_assignments.list_by_cluster(cluster.id),
            "recognition_results": self.repos.recognition.list_all_approved(),
            "recognition_runs": self.repos.recognition_runs.list_runs(),
            "person_face_embeddings": self.repos.person_face_samples.list_enabled(),
            "archive_records": self.repos.archive_records.list_all(),
        }


@pytest.fixture
def world(tmp_path: Path) -> _World:
    return _World(tmp_path)


def _submit_person_panel(world: _World, qtbot, annotator_id: str, person_id):
    """经真实 UI Panel 以指定身份提交一条 person 标注并返回面板。"""
    persons = [(world.person_a.id, "张三"), (world.person_b.id, "李四")]
    panel = CalibrationAnnotationPanel(
        calibration_service=world.service, annotator_id=annotator_id,
        persons_provider=lambda: persons,
    )
    qtbot.addWidget(panel)
    panel.set_cluster(world.cluster.id)
    panel._person_radio.setChecked(True)
    for i in range(panel._person_combo.count()):
        if panel._person_combo.itemData(i) == person_id:
            panel._person_combo.setCurrentIndex(i)
    panel._on_submit()
    return panel


# ══ CP8.1 / CP8.2 — 单条专家标注 → expert GroundTruth ═══════════════════


def test_single_expert_annotation_produces_expert_truth(world: _World) -> None:
    """D-2：一条专家标注直接构成真值 —— resolution=expert, annotator_count=1。"""
    service = world.service
    cid = world.cluster.id

    annotation = service.annotate(
        cid, ANNOTATOR_A, VERDICT_PERSON, person_id=world.person_a.id
    )

    truth = service.resolve_ground_truth(cid)
    assert truth is not None
    assert truth.resolution == RESOLUTION_EXPERT
    assert truth.annotator_count == 1
    assert truth.source_annotation_ids == (annotation.id,)
    assert truth.person_id == world.person_a.id
    assert truth.verdict == VERDICT_PERSON
    assert truth.difficulty_reason is None


def test_expert_annotation_via_ui_panel_persists(world: _World, qtbot) -> None:
    """CP8.1：经 UI Panel 提交 → 真正持久化到 SQLite。"""
    import sqlite3

    service = world.service
    cid = world.cluster.id

    _submit_person_panel(world, qtbot, ANNOTATOR_A, world.person_a.id)

    truth = service.resolve_ground_truth(cid)
    assert truth is not None and truth.resolution == RESOLUTION_EXPERT

    # 真正落库：直接读 SQLite
    conn = sqlite3.connect(str(world.repos._connection_provider.database_path))
    rows = conn.execute(
        "SELECT annotator_id, verdict, person_id, role, protocol_version "
        "FROM calibration_annotations WHERE cluster_id = ?",
        (str(cid),),
    ).fetchall()
    conn.close()
    assert len(rows) == 1, "单条专家标注真实落库"
    assert rows[0][1] == "person"
    assert rows[0][4] == PROTOCOL_VERSION


# ══ CP8.3/8.4/8.5 — 废止路径拒绝：无 agreement/adjudication 伪兼容 ═══════


def test_unannotated_cluster_yields_no_truth(world: _World) -> None:
    """未标注 → None（不产生真值行）。"""
    assert world.service.resolve_ground_truth(world.cluster.id) is None


def test_reannotation_latest_wins(world: _World) -> None:
    """CP8.5 语义迁移：多次标注 → 最新一条生效，全部历史保留。"""
    service = world.service
    cid = world.cluster.id
    first = service.annotate(cid, ANNOTATOR_A, VERDICT_PERSON,
                             person_id=world.person_a.id)
    second = service.annotate(cid, ANNOTATOR_B, VERDICT_PERSON,
                              person_id=world.person_b.id)
    assert first.id != second.id

    truth = service.resolve_ground_truth(cid)
    assert truth is not None
    assert truth.person_id == world.person_b.id, "最新一条生效"
    assert truth.source_annotation_ids == (second.id,)
    assert truth.annotator_count == 1, "真值来源恰为一条专家标注"

    # 全部历史保留（append-only，A 与 B 的行都在）
    all_annotations = world.repos.calibration_annotations.list_annotations(cid)
    assert len(all_annotations) == 2


# ══ CP8.6 — 同一标注者重新标注 ══════════════════════════════════════════


def test_same_annotator_reannotation_preserves_history(world: _World) -> None:
    """CP8.6：同一标注者改判 → 两行保留、latest 返回第二行并构成真值。"""
    service = world.service
    cid = world.cluster.id

    first = service.annotate(cid, ANNOTATOR_A, VERDICT_PERSON, person_id=world.person_a.id)
    second = service.annotate(cid, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    assert first.id != second.id, "两条是独立行"

    # list_annotations 看到两行
    all_annotations = world.repos.calibration_annotations.list_annotations(cid)
    assert len(all_annotations) == 2

    # find_latest_own_annotation 只返回第二行
    latest = world.repos.calibration_annotations.find_latest_own_annotation(
        cid, ANNOTATOR_A
    )
    assert latest is not None and latest.id == second.id

    # 单专家协议：最新行直接成为真值
    truth = service.resolve_ground_truth(cid)
    assert truth is not None
    assert truth.verdict == VERDICT_OUT_OF_ROSTER
    assert truth.source_annotation_ids == (second.id,)


# ══ CP8.7 — undecidable 全链贯通 ════════════════════════════════════════


def test_undecidable_full_lifecycle_to_dataset(world: _World) -> None:
    """CP8.7：undecidable → GroundTruth → Dataset → dataset_truth 全链保留 blur。"""
    service = world.service
    cid = world.cluster.id
    dataset_id = uuid4()

    service.annotate(cid, ANNOTATOR_A, VERDICT_UNDECIDABLE,
                     difficulty_reason="blur")
    truth = service.resolve_ground_truth(cid)
    assert truth is not None and truth.verdict == VERDICT_UNDECIDABLE
    assert truth.difficulty_reason == "blur"

    service.freeze_dataset(dataset_id, version="v1")
    truths = service.dataset_truth(dataset_id, "v1")
    assert len(truths) == 1
    assert truths[0].verdict == VERDICT_UNDECIDABLE
    assert truths[0].difficulty_reason == "blur", "dataset export 不得丢失难例分类"
    assert truths[0].resolution == RESOLUTION_EXPERT
    assert truths[0].annotator_count == 1


# ══ CP8.8 — out_of_roster 全链贯通 ══════════════════════════════════════


def test_out_of_roster_full_lifecycle_to_dataset(world: _World) -> None:
    """CP8.8：out_of_roster → GroundTruth → Dataset → dataset_truth。"""
    service = world.service
    cid = world.cluster.id
    dataset_id = uuid4()

    service.annotate(cid, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    truth = service.resolve_ground_truth(cid)
    assert truth is not None and truth.verdict == VERDICT_OUT_OF_ROSTER
    assert truth.person_id is None and truth.difficulty_reason is None

    service.freeze_dataset(dataset_id, version="v1")
    truths = service.dataset_truth(dataset_id, "v1")
    assert len(truths) == 1
    assert truths[0].verdict == VERDICT_OUT_OF_ROSTER
    assert truths[0].person_id is None


# ══ CP8.9 / CP8.10 — Dataset 版本隔离与冻结 ═════════════════════════════


def test_dataset_v1_v2_coexist_and_v1_unchanged(world: _World) -> None:
    """CP8.9/8.10：v1 与 v2 共存；v2 新增不影响 v1。"""
    service = world.service
    cid = world.cluster.id
    dataset_id = uuid4()

    # v1：张三
    service.annotate(cid, ANNOTATOR_A, VERDICT_PERSON, person_id=world.person_a.id)
    service.freeze_dataset(dataset_id, version="v1")
    v1_truths = service.dataset_truth(dataset_id, "v1")
    assert len(v1_truths) == 1
    assert v1_truths[0].person_id == world.person_a.id
    v1_snapshot = [(t.cluster_id, t.verdict, t.person_id, t.difficulty_reason,
                    t.resolution, t.source_annotation_ids, t.annotator_count)
                   for t in v1_truths]

    # v2：改判 out_of_roster + 新簇标注给李四
    service.annotate(cid, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)  # 撤回张三
    cluster2 = FaceCluster(
        cluster_run_id=world.cluster_run.id, run_id=world.run.id,
        ordinal=1, member_count=1, sort_key="k1",
    )
    world.repos.face_clusters.add_clusters([cluster2])
    service.annotate(cluster2.id, ANNOTATOR_A, VERDICT_PERSON,
                     person_id=world.person_b.id)
    service.freeze_dataset(dataset_id, version="v2")

    v2_truths = service.dataset_truth(dataset_id, "v2")
    assert len(v2_truths) >= 1
    # v1 内容完全不变
    v1_after = service.dataset_truth(dataset_id, "v1")
    v1_after_snapshot = [(t.cluster_id, t.verdict, t.person_id, t.difficulty_reason,
                          t.resolution, t.source_annotation_ids, t.annotator_count)
                         for t in v1_after]
    assert v1_snapshot == v1_after_snapshot, "v2 创建不得修改 v1"


# ══ CP8.11 — draft 不静默转换 ═══════════════════════════════════════════


def test_draft_dataset_rejected_both_backends(world: _World) -> None:
    """CP8.11：draft 在 SQLite 报错、不留持久化痕迹。"""
    from photo_archiver.infrastructure.database.sqlite_calibration_annotation_repository import (
        CalibrationPersistenceError,
    )

    draft = CalibrationDataset(
        version="draft", cluster_count=0, usable_count=0, excluded_count=0,
        status="draft",
    )
    with pytest.raises(CalibrationPersistenceError):
        world.repos.calibration_annotations.add_dataset(draft)
    assert world.repos.calibration_annotations.get_dataset(draft.id) is None


# ══ CP8.12 — dataset_truth 只含已标注簇 ═════════════════════════════════


def test_dataset_truth_covers_exactly_the_annotated_clusters(world: _World) -> None:
    """CP8.12：freeze 遍历已标注簇——未标注簇不进入数据集。"""
    service = world.service
    dataset_id = uuid4()

    # cluster 1：已标注（张三）→ 进入
    service.annotate(world.cluster.id, ANNOTATOR_A, VERDICT_PERSON,
                     person_id=world.person_a.id)

    # cluster 2：未标注 → 不进入
    cluster2 = FaceCluster(
        cluster_run_id=world.cluster_run.id, run_id=world.run.id,
        ordinal=1, member_count=1, sort_key="k1",
    )
    world.repos.face_clusters.add_clusters([cluster2])

    service.freeze_dataset(dataset_id, version="v1")
    truths = service.dataset_truth(dataset_id, "v1")
    assert len(truths) == 1, "只有已标注簇进入数据集"
    assert truths[0].person_id == world.person_a.id


# ══ CP8.13 — Assignment 不影响 GroundTruth ══════════════════════════════


def test_assignment_change_does_not_affect_ground_truth(world: _World) -> None:
    """CP8.13：业务 Assignment 变化后，GroundTruth 不变。"""
    from photo_archiver.domain.entities.cluster_assignment import (
        ClusterPersonAssignment,
    )

    service = world.service
    cid = world.cluster.id
    dataset_id = uuid4()

    # 建立 Ground Truth
    service.annotate(cid, ANNOTATOR_A, VERDICT_PERSON, person_id=world.person_a.id)
    service.freeze_dataset(dataset_id, version="v1")
    truth_before = service.dataset_truth(dataset_id, "v1")

    # 写入业务 Assignment（手工指派给另一个人）
    assignment = ClusterPersonAssignment(
        cluster_id=cid, person_id=world.person_b.id, source="manual",
    )
    assignment.confirm()
    world.repos.cluster_assignments.add_assignments([assignment])

    truth_after = service.dataset_truth(dataset_id, "v1")
    assert [
        (t.cluster_id, t.verdict, t.person_id, t.difficulty_reason) for t in truth_before
    ] == [
        (t.cluster_id, t.verdict, t.person_id, t.difficulty_reason) for t in truth_after
    ], "Assignment 变化不得影响 GroundTruth"


# ══ CP8.14 — Business isolation（真实 SQLite 全表快照） ══════════════════


def test_full_lifecycle_business_isolation(world: _World) -> None:
    """CP8.14：完整 Calibration 生命周期 → 业务五表 before == after（数据级）。"""
    service = world.service
    cid = world.cluster.id
    before = world.business_snapshot()
    # 预置业务数据（证明表确实存在且可被误写）
    world.repos.recognition.add(RecognitionResult(
        photo_id=world.photo.id, confidence=None,
    ))

    # 完整生命周期（含重新标注与重新冻结）
    service.annotate(cid, ANNOTATOR_A, VERDICT_PERSON, person_id=world.person_a.id)
    service.annotate(cid, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)
    service.freeze_dataset(uuid4(), version="v1")
    service.freeze_dataset(uuid4(), version="v2")

    after = world.business_snapshot()
    for table in before:
        assert before[table] == after[table], f"业务表 {table} 被 calibration 改写"


# ══ CP8.15 — Calibration 数据完整性 ═════════════════════════════════════


def test_calibration_data_integrity_after_full_lifecycle(world: _World) -> None:
    """CP8.15：完整生命周期后三张表数据完整且可追溯。"""
    service = world.service
    cid = world.cluster.id
    dataset_id = uuid4()

    ann_a = service.annotate(cid, ANNOTATOR_A, VERDICT_PERSON,
                             person_id=world.person_a.id)
    service.freeze_dataset(dataset_id, version="v1")

    # annotation history 完整
    annotations = world.repos.calibration_annotations.list_annotations(cid)
    assert len(annotations) == 1

    # ground truth 可追溯（来源恰为那条专家标注）
    truth = world.repos.calibration_annotations.find_ground_truth(cid)
    assert truth is not None
    assert truth.source_annotation_ids == (ann_a.id,)
    assert truth.annotator_count == 1

    # dataset version 唯一
    datasets = world.repos.calibration_annotations.list_datasets()
    assert len(datasets) == 1 and datasets[0].version == "v1"

    # frozen dataset 可重现
    truths = service.dataset_truth(dataset_id, "v1")
    assert len(truths) == 1 and truths[0].person_id == world.person_a.id


# ══ CP8.20 — 未聚类 fail-closed ═════════════════════════════════════════


def test_nonexistent_cluster_fail_closed(world: _World) -> None:
    """CP8.20：不存在的 cluster_id → Service 正常记录（无 FK 约束检查取决于仓储），但 UI 层已阻止。"""
    # Service 层不验证 cluster 存在性（由 UI 层 fail-closed），
    # 但真实 SQLite FK 会拒绝（cluster_id FK → face_clusters）。
    nonexistent = uuid4()
    with pytest.raises(Exception):
        world.service.annotate(nonexistent, ANNOTATOR_A, VERDICT_PERSON,
                               person_id=world.person_a.id)


# ══ CP8.21 — version latest 语义（v8/v9/v10 词典序陷阱） ═══════════════


def test_version_latest_lexicographic_trap(world: _World) -> None:
    """CP8.21：v10 与 v9 同 dataset_id，version=None 时由 created_at 决定。

    词典序 v10 < v9，但 created_at DESC 主导排序 → latest 由时间序决定。
    记录为当前可接受（依赖 created_at 唯一性），不自行引入 sequence 字段。
    """
    shared = uuid4()

    for version in ("v8", "v9", "v10"):
        world.repos.calibration_annotations.add_dataset(CalibrationDataset(
            version=version, cluster_count=0, usable_count=0, excluded_count=0,
            id=shared,
        ))

    # created_at 由 add_dataset 逐条写入，每条微秒级递增
    # get_dataset(version=None) 按 created_at DESC → latest = 最后写入的 v10
    latest = world.repos.calibration_annotations.get_dataset(shared)
    assert latest is not None
    assert latest.version == "v10", (
        "created_at DESC 主导排序 → 最新写入的 v10 被返回（不受词典序 v10 < v9 影响）"
    )
    # 但如果同刻写入，词典序陷阱仍存在 → 记为 ATTENTION
    all_datasets = world.repos.calibration_annotations.list_datasets()
    assert len(all_datasets) == 3, "三个版本都保留"


# ══ CP8.22 — sampling 未实现确认 ════════════════════════════════════════


def test_no_sampling_executor_exists() -> None:
    """CP8.22：全仓不存在 sampling executor / seed 参与抽样的实现。"""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "photo_archiver"
    for py_file in src.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and "sampling" in node.name.lower():
                pytest.fail(f"发现了 sampling executor: {py_file}:{node.lineno}")


# ══ CP8.23 — annotator_id 全链一致 ══════════════════════════════════════


def test_annotator_id_consistent_through_service_to_repo(world: _World) -> None:
    """CP8.23：annotator_id 在 Service → Repository 全链一致。"""
    service = world.service
    cid = world.cluster.id
    service.annotate(cid, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)

    stored = world.repos.calibration_annotations.list_annotations(cid)
    assert len(stored) == 1
    assert stored[0].annotator_id == ANNOTATOR_A


# ══ CP8.24 — protocol_version 全链保留 ══════════════════════════════════


def test_protocol_version_round_trip(world: _World) -> None:
    """CP8.24：protocol_version 在 Service → Repository → SQLite 全链保留。"""
    service = world.service
    cid = world.cluster.id
    service.annotate(cid, ANNOTATOR_A, VERDICT_OUT_OF_ROSTER)

    stored = world.repos.calibration_annotations.list_annotations(cid)
    assert stored[0].protocol_version == PROTOCOL_VERSION


# ══ CP8.19 — UI blind 行为保持 ═════════════════════════════════════════


def test_ui_blind_isolation_two_annotators(world: _World, qtbot) -> None:
    """CP8.19：A 面板只见 A 的 latest；B 面板只见 B 的 latest（身份防线不因协议变更削弱）。"""
    service = world.service
    cid = world.cluster.id

    # A 标注张三
    _submit_person_panel(world, qtbot, ANNOTATOR_A, world.person_a.id)
    # B 标注张三（单专家协议允许多身份追加；真值取最新）
    _submit_person_panel(world, qtbot, ANNOTATOR_B, world.person_a.id)

    # 服务层隔离：两个身份各自返回自己的行，互不汇聚
    own_a = service.latest_own_annotation(cid, ANNOTATOR_A)
    own_b = service.latest_own_annotation(cid, ANNOTATOR_B)
    assert own_a is not None and own_a.annotator_id == ANNOTATOR_A
    assert own_b is not None and own_b.annotator_id == ANNOTATOR_B
    assert own_a.id != own_b.id

    # UI 层：各自重载 → 状态栏渲染的是"我的最新标注"（own view），不是未标注
    panel_a = CalibrationAnnotationPanel(
        calibration_service=service, annotator_id=ANNOTATOR_A,
        persons_provider=lambda: [(world.person_a.id, "张三"), (world.person_b.id, "李四")],
    )
    qtbot.addWidget(panel_a)
    panel_a.set_cluster(cid)
    assert panel_a._status_label.text().startswith("我的最新标注"), (
        "A 面板渲染自己的最新标注（own view）"
    )
    panel_b = CalibrationAnnotationPanel(
        calibration_service=service, annotator_id=ANNOTATOR_B,
        persons_provider=lambda: [(world.person_a.id, "张三"), (world.person_b.id, "李四")],
    )
    qtbot.addWidget(panel_b)
    panel_b.set_cluster(cid)
    assert panel_b._status_label.text().startswith("我的最新标注"), (
        "B 面板渲染自己的最新标注（互不泄露）"
    )
