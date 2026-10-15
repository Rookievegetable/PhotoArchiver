"""PairingWorkbenchDialog tests — Stage E 身份指派 UI.

Covers: generation/cluster rendering with assignment states (auto suggestion
vs manual confirm distinguishable), suggestion generation through the
service, confirm/reject/assign/unassign/state actions hitting the services
and re-rendering, empty roster/no-cluster states. Services are the real
application services over InMemory repositories (same harness as the
service tests) so the UI is exercised against genuine state transitions.
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from unittest.mock import Mock

from photo_archiver.application.services import (
    ClusterResultsService,
    ListPersonsService,
    PairingWorkbenchService,
    SuggestPairingsService,
)
from photo_archiver.domain import MatchStatus, RecognitionResult
from photo_archiver.infrastructure import (
    InMemoryClusterPersonAssignmentRepository,
    InMemoryFaceClusterRepository,
    InMemoryFaceObservationRepository,
    InMemoryPersonFaceSampleRepository,
    NumpyCosineSimilarityFactory,
)
from photo_archiver.presentation.views.pairing_workbench_dialog import (
    PairingWorkbenchDialog,
)


class _RunRepoWithPhotos(InMemoryFaceClusterRepository):
    def __init__(self):
        super().__init__()
        self._recognition_runs: dict = {}
        self._run_photos: dict = {}

    def add_recognition_run(self, run):
        self._recognition_runs[run.id] = run

    def get_run(self, run_id):
        return self._recognition_runs.get(run_id)

    def add_run_photos(self, run_id, snapshots):
        self._run_photos.setdefault(run_id, []).extend(snapshots)

    def list_run_photos(self, run_id):
        return list(self._run_photos.get(run_id, []))


class _Harness:
    """One generation with two clusters + a two-person roster."""

    def __init__(self, *, with_roster: bool = True):
        self.clusters = _RunRepoWithPhotos()
        self.observations = InMemoryFaceObservationRepository()
        self.assignments = InMemoryClusterPersonAssignmentRepository(
            cluster_scope=self.clusters.list_clusters,
        )
        self.samples = InMemoryPersonFaceSampleRepository()
        self.persons = []
        from photo_archiver.domain import RecognitionRun

        self.recognition_run = RecognitionRun(parameters={})
        self.clusters.add_recognition_run(self.recognition_run)
        if with_roster:
            self._make_person("张三", 1)
            self._make_person("李四", 2)
        self.roster = Mock(execute=Mock(return_value=list(self.persons)))

    def _make_person(self, name, order):
        from photo_archiver.domain import Person

        person = Person(name=name, roster_order=order)
        self.persons.append(person)
        return person

    def seed_generation(self, *, captured: bool = False):
        from uuid import uuid4

        from photo_archiver.domain import (
            FaceCluster,
            FaceClusterMember,
            FaceClusterRun,
            FaceObservation,
        )
        from datetime import datetime

        run = self.recognition_run
        observations = []
        for index, angle in enumerate((0.0, 6.0, 180.0, 186.0)):
            observation = FaceObservation(
                run_id=run.id, photo_id=uuid4(), face_index=index % 2,
                photo_face_count=2, det_score=0.9,
                box=type("B", (), {"x1": index, "y1": 0, "x2": index + 10, "y2": 10})(),
                embedding=__import__("photo_archiver.domain", fromlist=["FaceEmbedding"]).FaceEmbedding(
                    (__import__("math").cos(__import__("math").radians(angle)),
                     __import__("math").sin(__import__("math").radians(angle))),
                ),
                scope_verdict="in_selected_scope",
            )
            self.observations.add_many([observation])
            observations.append(observation)
        cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="v1")
        self.clusters.add_cluster_run(cluster_run)
        for ordinal, members in enumerate((observations[:2], observations[2:])):
            cluster = FaceCluster(
                cluster_run_id=cluster_run.id, run_id=run.id, ordinal=ordinal,
                member_count=len(members), sort_key=f"k|{ordinal}|000000",
                first_captured_at=datetime(2026, 1, 1, 8, 0, 0) if captured else None,
            )
            self.clusters.add_clusters([cluster])
            self.clusters.add_members([
                FaceClusterMember(cluster_id=cluster.id, observation_id=o.id)
                for o in members
            ])
        cluster_run.start()
        cluster_run.complete(2, 4, 0)
        return cluster_run

    def build_services(self):
        suggest = SuggestPairingsService(
            self.clusters, self.observations, _RosterRepo(self.persons),
            self.assignments, self.samples, NumpyCosineSimilarityFactory(),
        )
        workbench = PairingWorkbenchService(
            self.assignments, self.clusters, self.observations,
            _RosterRepo(self.persons), _RecognitionStub(), self.samples,
        )
        results = ClusterResultsService(
            self.clusters, self.observations, self.clusters, self.assignments,
        )
        roster = ListPersonsService(_RosterRepo(self.persons))
        return suggest, workbench, results, roster

    def build_dialog(self, qtbot) -> PairingWorkbenchDialog:
        suggest, workbench, results, roster = self.build_services()
        dialog = PairingWorkbenchDialog(
            suggest, workbench, results, roster, self.recognition_run.id,
        )
        qtbot.addWidget(dialog)
        return dialog


class _RosterRepo:
    def __init__(self, persons):
        self._persons = persons

    def list_all(self):
        return list(self._persons)

    def find_by_id(self, person_id):
        return next((p for p in self._persons if p.id == person_id), None)


class _RecognitionStub:
    """S1：补齐投影所有权契约（与 SQLite 实现同语义）。

    缺失任一方法都会让 ``ProjectionReconciler`` 抛 ``AttributeError``，而对话框
    的 ``except Exception`` 会弹出未打桩的模态框 → headless 永久挂起。
    """

    def __init__(self):
        self.rows: list = []

    def add(self, result):
        self.rows.append(result)

    def list_by_photo(self, photo_id):
        return [row for row in self.rows if row.photo_id == photo_id]

    def list_all_approved(self):
        return [row for row in self.rows if row.status == MatchStatus.APPROVED]

    def find_projection(self, photo_id, person_id):
        for row in self.rows:
            if (row.photo_id == photo_id and row.person_id == person_id
                    and row.assignment_id is not None
                    and row.status == MatchStatus.APPROVED):
                return row
        return None

    def list_projections(self):
        return [row for row in self.rows
                if row.assignment_id is not None and row.status == MatchStatus.APPROVED]

    def create_projection(self, photo_id, person_id, assignment_id):
        row = RecognitionResult(
            photo_id=photo_id, person_id=person_id, confidence=None,
            status=MatchStatus.APPROVED, assignment_id=assignment_id,
        )
        self.rows.append(row)
        return row

    def retarget_projection(self, result_id, assignment_id):
        for row in self.rows:
            if row.id == result_id:
                row.assignment_id = assignment_id
                return 1
        return 0

    def terminate_projection(self, result_id):
        for row in self.rows:
            if row.id == result_id and row.status == MatchStatus.APPROVED:
                row.status = MatchStatus.REJECTED
                return 1
        return 0

    def remove_results_for_person_photos(self, person_id, photo_ids):
        targets = set(photo_ids)
        before = len(self.rows)
        self.rows = [
            row for row in self.rows
            if not (row.person_id == person_id and row.photo_id in targets
                    and row.status == MatchStatus.APPROVED)
        ]
        return before - len(self.rows)


def test_clusters_render_with_unassigned_state(qtbot) -> None:
    harness = _Harness()
    harness.seed_generation()
    dialog = harness.build_dialog(qtbot)

    assert dialog._cluster_list.count() == 2
    texts = [dialog._cluster_list.item(i).text() for i in range(2)]
    # 尚无决策行 → 显示「尚未生成建议」提示（区别于已有行的未指派状态）。
    assert all("尚未生成建议" in t for t in texts)


def test_generate_suggestions_renders_pending_with_source(qtbot) -> None:
    harness = _Harness()
    harness.seed_generation()
    dialog = harness.build_dialog(qtbot)

    dialog._on_generate_clicked()

    assert "已生成 2 条建议" in dialog._status_label.text()
    texts = [dialog._cluster_list.item(i).text() for i in range(2)]
    assert all("待确认" in t and "顺序建议" in t for t in texts)


def test_confirm_action_confirms_and_renders_person(qtbot) -> None:
    harness = _Harness()
    harness.seed_generation()
    dialog = harness.build_dialog(qtbot)
    dialog._on_generate_clicked()
    dialog._cluster_list.setCurrentRow(0)
    person_id = dialog._person_combo.currentData()

    dialog._on_confirm_clicked()

    assert "已确认归属" in dialog._status_label.text()
    assignment = dialog._assignments_by_cluster[dialog._selected_cluster_id]
    assert assignment.status == "confirmed"
    assert assignment.person_id == person_id


def test_reject_action_marks_rejected(qtbot) -> None:
    harness = _Harness()
    harness.seed_generation()
    dialog = harness.build_dialog(qtbot)
    dialog._on_generate_clicked()
    dialog._cluster_list.setCurrentRow(0)
    assignment_id = dialog._selected_assignment_id()
    assert assignment_id is not None

    dialog._on_reject_clicked()

    assert "已拒绝" in dialog._status_label.text()
    # 拒绝后的行离开有效映射——经 get_assignment 验证落库状态。
    row = dialog._workbench_service.get_assignment(assignment_id)
    assert row is not None and row.status == "rejected"


def test_manual_assign_confirms_immediately_and_replaces(qtbot) -> None:
    harness = _Harness()
    harness.seed_generation()
    dialog = harness.build_dialog(qtbot)
    dialog._on_generate_clicked()
    dialog._cluster_list.setCurrentRow(0)
    suggested_person = dialog._person_combo.currentData()
    dialog._on_confirm_clicked()

    # 改派：选择另一名人员并人工指派。
    other = next(p for p in harness.persons if p.id != suggested_person)
    index = dialog._person_combo.findData(other.id)
    dialog._person_combo.setCurrentIndex(index if index >= 0 else 0)
    dialog._selected_cluster_id = dialog._selected_cluster_id
    dialog._on_assign_clicked()

    assert "已人工指派" in dialog._status_label.text()
    assignment = dialog._assignments_by_cluster[dialog._selected_cluster_id]
    assert assignment.status == "confirmed"
    assert assignment.source == "manual"
    assert assignment.person_id == other.id


def test_unassign_and_state_actions(qtbot) -> None:
    harness = _Harness()
    harness.seed_generation()
    dialog = harness.build_dialog(qtbot)
    dialog._on_generate_clicked()
    dialog._cluster_list.setCurrentRow(0)

    dialog._on_unassign_clicked()
    assert "已解除映射" in dialog._status_label.text()

    dialog._on_state_clicked("unknown")
    assert "unknown" in dialog._status_label.text()


def test_empty_roster_disables_person_combo(qtbot) -> None:
    harness = _Harness(with_roster=False)
    harness.seed_generation()
    dialog = harness.build_dialog(qtbot)

    assert dialog._person_combo.count() == 0
    assert dialog._person_combo.isEnabled() is False


def test_no_clusters_shows_state(qtbot) -> None:
    harness = _Harness()
    dialog = harness.build_dialog(qtbot)  # 未种任何聚类代际

    assert "尚无聚类结果" in dialog._status_label.text()
    assert dialog._cluster_list.count() == 0

def test_auto_confirmed_renders_distinct_label_and_feedback(qtbot) -> None:
    """C4-1/C4-2：auto_confirmed 行显示独立状态（非"未指派"），反馈含自动确认计数。"""
    harness = _Harness()
    harness.seed_generation(captured=True)  # 时间齐备 → 整批位置自动确认
    dialog = harness.build_dialog(qtbot)
    dialog._on_generate_clicked()
    item_text = dialog._cluster_list.item(0).text()
    assert "自动确认（待人工终审）" in item_text
    assert "未指派" not in item_text
    assert "位置自动确认 2 项（待人工终审）" in dialog._status_label.text()
    assert "未执行" not in dialog._status_label.text()

def test_confirm_on_auto_confirmed_routes_to_final_confirmation(qtbot) -> None:
    """C4-2：auto 行的确认按钮走 D-6 人工终审（assign_person），非原地升级。"""
    harness = _Harness()
    harness.seed_generation(captured=True)
    dialog = harness.build_dialog(qtbot)
    dialog._on_generate_clicked()
    dialog._cluster_list.setCurrentRow(0)
    person_id = dialog._person_combo.currentData()

    dialog._on_confirm_clicked()

    assert "已人工终审确认" in dialog._status_label.text()
    assignment = dialog._assignments_by_cluster[dialog._selected_cluster_id]
    assert assignment.status == "confirmed"
    assert assignment.source == "manual"  # 新建人工决策行，非原地升级
    assert assignment.person_id == person_id  # 终审确认的是 auto 行的原人员

def test_suggested_path_confirm_still_works_when_counts_mismatch(qtbot) -> None:
    """C4-2.5：数量不等 → suggested 路径保留，原地确认行为不变。"""
    harness = _Harness()
    harness.seed_generation(captured=True)
    harness._make_person("王五", None)  # 3 人 × 2 簇 → COUNT_MISMATCH
    dialog = harness.build_dialog(qtbot)
    dialog._on_generate_clicked()
    # 生成反馈含阻断原因（数量不一致）
    assert "簇与人员数量不一致" in dialog._status_label.text()
    dialog._cluster_list.setCurrentRow(0)

    dialog._on_confirm_clicked()

    assert "已确认归属" in dialog._status_label.text()
    assignment = dialog._assignments_by_cluster[dialog._selected_cluster_id]
    assert assignment.status == "confirmed"
