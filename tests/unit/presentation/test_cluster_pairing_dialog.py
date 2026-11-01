"""整合配对界面对话框测试 — 界面优化 §5/§3.3（替代原 PairingWorkbenchDialog 测试）.

覆盖：组列表展示匹配人员/未匹配与照片数、生成建议反馈、批量确认/拒绝
（操作前计划 + 逐项提交 + 部分成功反馈 + 跳过原因）、照片忽略/恢复
（逐项 + 已忽略标记）、无"解除映射"入口、历史未知处理状态不冒充 0 脸。
服务为真实应用服务 + InMemory 仓储（与服务层测试同构）。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

import math
import time
from datetime import datetime

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QMessageBox
from uuid import uuid4

from photo_archiver.application.commands import AddPersonCommand
from photo_archiver.application.commands.photo_ignore import (
    IgnorePhotosCommand,
    RestorePhotosCommand,
)
from photo_archiver.application.services import (
    ClusterResultsService,
    ListPersonsService,
    PairingWorkbenchService,
    PhotoIgnoreService,
    SuggestPairingsService,
)
from photo_archiver.application.commands.pairing import (
    ConfirmAssignmentCommand,
)
from photo_archiver.application.services.pairing_workbench_service import (
    AssignClusterPersonCommand,
)
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
)
from photo_archiver.domain import (
    FaceBox,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceEmbedding,
    FaceObservation,
    MatchStatus,
    Person,
    RecognitionResult,
    RecognitionRun,
    RunPhotoSnapshot,
)
from photo_archiver.domain.entities.cluster_assignment import (
    ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
    ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
    ASSIGNMENT_STATUS_AUTO_CONFIRMED,
    ASSIGNMENT_STATUS_CONFIRMED,
    ClusterPersonAssignment,
    HUMAN_ACTOR,
)
from photo_archiver.infrastructure import (
    InMemoryClusterPersonAssignmentRepository,
    InMemoryFaceClusterRepository,
    InMemoryFaceObservationRepository,
    InMemoryPersonFaceSampleRepository,
    InMemoryPhotoIgnoreStateRepository,
    InMemoryRecognitionRunRepository,
    NumpyCosineSimilarityFactory,
)
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.task_coordinator import TaskCoordinator
from photo_archiver.workers.qt_executor import QtWorkerExecutor
from photo_archiver.presentation.visual_style import build_stylesheet, token
from photo_archiver.presentation.views.cluster_results_dialog import (
    ClusterResultsDialog,
)


class _PersonRepo:
    def __init__(self, persons):
        self._persons = persons

    def list_all(self):
        return sorted(self._persons.values(),
                      key=lambda p: (p.roster_order is None,
                                     p.roster_order if p.roster_order is not None else 0,
                                     str(p.id)))

    def find_by_id(self, person_id):
        return self._persons.get(person_id)


class _RecognitionRepoStub:
    """Projection store stand-in（语义与 SQLiteRecognitionRepository 对齐）."""

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


class _Harness:
    """One recognition run + run photo snapshots; generations added per test."""

    def __init__(self):
        self.clusters = InMemoryFaceClusterRepository()
        self.observations = InMemoryFaceObservationRepository()
        self.runs = InMemoryRecognitionRunRepository()
        self.assignments = InMemoryClusterPersonAssignmentRepository(
            cluster_scope=self.clusters.list_clusters,
        )
        self.samples = InMemoryPersonFaceSampleRepository()
        self.ignores = InMemoryPhotoIgnoreStateRepository()
        self.recognition = _RecognitionRepoStub()
        self.persons = {}
        self.recognition_run = RecognitionRun(parameters={})
        self.runs.add_run(self.recognition_run)

    def add_person(self, name, roster_order=None):
        person = Person(name=name, roster_order=roster_order)
        self.persons[person.id] = person
        return person

    def add_photo(self, path: str):
        photo_id = uuid4()
        self.runs.add_run_photos(self.recognition_run.id, [
            RunPhotoSnapshot(self.recognition_run.id, photo_id, path, None),
        ])
        return photo_id

    def add_observation(self, photo_id, index, angle):
        radians = math.radians(angle)
        observation = FaceObservation(
            run_id=self.recognition_run.id, photo_id=photo_id, face_index=index,
            photo_face_count=index + 1, det_score=0.9,
            box=FaceBox(index, 0, index + 10, 10),
            embedding=FaceEmbedding((math.cos(radians), math.sin(radians))),
            scope_verdict="in_selected_scope",
        )
        self.observations.add_many([observation])
        return observation

    def add_generation(self, member_spec, *, outcomes=None):
        """member_spec: [(sort_key, [observation, ...])]; outcomes: photo→outcome."""
        cluster_run = FaceClusterRun(
            recognition_run_id=self.recognition_run.id, algorithm_version="v1",
        )
        self.clusters.add_cluster_run(cluster_run)
        clusters = []
        for ordinal, (sort_key, members) in enumerate(member_spec):
            cluster = FaceCluster(
                cluster_run_id=cluster_run.id, run_id=self.recognition_run.id,
                ordinal=ordinal, member_count=len(members), sort_key=sort_key,
                first_captured_at=datetime(2026, 1, 1),
            )
            self.clusters.add_clusters([cluster])
            clusters.append(cluster)
            for member in members:
                self.clusters.add_members([
                    FaceClusterMember(cluster_id=cluster.id,
                                      observation_id=member.id),
                ])
        cluster_run.start()
        cluster_run.complete(len(member_spec), sum(len(m) for _, m in member_spec), 0)
        if outcomes:
            for snapshot in list(self.runs.list_run_photos(self.recognition_run.id)):
                outcome = outcomes.get(snapshot.photo_id)
                if outcome:
                    self.runs.update_run_photo_outcome(
                        self.recognition_run.id, snapshot.photo_id, outcome,
                    )
        return cluster_run, clusters

    def build_services(self):
        reconciler = ProjectionReconciler(
            recognition_repository=self.recognition,
            assignment_repository=self.assignments,
            cluster_repository=self.clusters,
            observation_repository=self.observations,
            photo_ignore_repository=self.ignores,
        )
        suggest = SuggestPairingsService(
            self.clusters, self.observations, _PersonRepo(self.persons),
            self.assignments, self.samples, NumpyCosineSimilarityFactory(),
            photo_ignore_repository=self.ignores,
        )
        workbench = PairingWorkbenchService(
            self.assignments, self.clusters, self.observations,
            _PersonRepo(self.persons), self.recognition, self.samples,
            reconciler=reconciler,
        )
        ignore = PhotoIgnoreService(
            self.ignores, self.clusters, self.observations, self.assignments,
            reconciler=reconciler,
        )
        results = ClusterResultsService(
            self.runs, self.observations, self.clusters, self.assignments,
            photo_ignore_repository=self.ignores,
        )
        roster = ListPersonsService(_PersonRepo(self.persons))
        return suggest, workbench, ignore, results, roster

    def build_dialog(self, qtbot):
        suggest, workbench, ignore, results, roster = self.build_services()
        dialog = ClusterResultsDialog(
            results, self.recognition_run.id,
            suggest_service=suggest,
            workbench_service=workbench,
            ignore_service=ignore,
            list_persons=roster,
        )
        qtbot.addWidget(dialog)
        return dialog


# ── 组列表与详情展示 ─────────────────────────────────────────────────────────


def test_group_list_shows_person_or_unmatched_and_photo_count(qtbot):
    harness = _Harness()
    person = harness.add_person("张三", 1)
    photo_a = harness.add_photo("photos/a.jpg")
    photo_b = harness.add_photo("photos/b.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_a, 1, 6.0)
    o3 = harness.add_observation(photo_b, 0, 180.0)
    cluster_run, clusters = harness.add_generation([
        ("k|a|000000", [o1, o2]),
        ("k|b|000001", [o3]),
    ])
    suggest, workbench, ignore, results, roster = harness.build_services()
    workbench.assign_person(
        AssignClusterPersonCommand(cluster_id=clusters[0].id, person_id=person.id),
        actor=HUMAN_ACTOR,
    )
    dialog = ClusterResultsDialog(
        results, harness.recognition_run.id,
        suggest_service=suggest, workbench_service=workbench,
        ignore_service=ignore, list_persons=roster,
    )
    qtbot.addWidget(dialog)

    entries = [dialog._cluster_list.item(i).text()
               for i in range(dialog._cluster_list.count())]
    assert any("张三" in entry and "1 照片/2 脸" in entry for entry in entries)
    assert any("未匹配" in entry and "1 照片/1 脸" in entry for entry in entries)


def test_unknown_photo_outcome_is_not_shown_as_no_face(qtbot):
    """§6.3：历史 run 的 None 状态展示为"未知"，绝不冒充 0 张脸。"""
    harness = _Harness()
    photo_a = harness.add_photo("photos/a.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    harness.add_generation([("k|a|000000", [o1])])
    dialog = harness.build_dialog(qtbot)

    grid_text = dialog._photo_grid.item(0).text()
    assert "处理状态未知（历史 run）" in grid_text
    assert "0 张脸" not in grid_text


def test_run_status_summary_counts_each_outcome(qtbot):
    harness = _Harness()
    photo_a = harness.add_photo("photos/a.jpg")
    photo_b = harness.add_photo("photos/b.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_b, 0, 0.0)
    harness.add_generation(
        [("k|a|000000", [o1]), ("k|b|000001", [o2])],
        outcomes={photo_a: "no_face", photo_b: "faces"},
    )
    dialog = harness.build_dialog(qtbot)

    status = dialog._run_status_label.text()
    assert "0 脸 1" in status and "有脸 1" in status and "未知 0" in status


# ── 无"解除映射"入口（§5.6） ────────────────────────────────────────────────


def test_no_unassign_entry_exists_in_pairing_mode(qtbot):
    harness = _Harness()
    photo_a = harness.add_photo("photos/a.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    harness.add_generation([("k|a|000000", [o1])])
    dialog = harness.build_dialog(qtbot)

    buttons = dialog.findChildren(__import__("PySide6").QtWidgets.QPushButton)
    assert all("解除映射" not in button.text() for button in buttons)


# ── P5：生成建议按钮态与空名单反馈（阶段 1） ──────────────────────────────


def test_generate_button_disabled_without_generation(qtbot):
    """P5：识别运行无任何聚类代际时「生成建议」禁用（无静默无效路径）。"""
    harness = _Harness()
    dialog = harness.build_dialog(qtbot)

    assert dialog._generation_combo.count() == 0
    assert dialog._generate_button.isEnabled() is False


def test_generate_button_enabled_with_generation(qtbot):
    """P5：存在代际时按钮恢复可用。"""
    harness = _Harness()
    photo_a = harness.add_photo("photos/a.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    harness.add_generation([("k|a|000000", [o1])])
    dialog = harness.build_dialog(qtbot)

    assert dialog._generation_combo.count() == 1
    assert dialog._generate_button.isEnabled() is True


def test_generate_with_empty_roster_shows_feedback(qtbot, monkeypatch):
    """P5：名单为空时点击给出可见反馈（不静默产出零建议）。"""
    harness = _Harness()
    photo_a = harness.add_photo("photos/a.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    harness.add_generation([("k|a|000000", [o1])])
    dialog = harness.build_dialog(qtbot)  # 未 add_person：名单为空

    from photo_archiver.presentation import ui_text as text
    monkeypatch.setattr(dialog, "refresh", lambda: None)  # 只验证反馈分支
    dialog._on_generate_clicked()

    assert text.CLUSTER_PAIRING_NO_PERSONS in dialog._feedback_label.text()


# ── 批量确认 / 拒绝（逐项提交，部分成功） ────────────────────────────────────


def test_batch_confirm_skips_confirmed_and_reports_partial_success(qtbot, monkeypatch):
    harness = _Harness()
    person = harness.add_person("张三", 1)
    photo_a = harness.add_photo("photos/a.jpg")
    photo_b = harness.add_photo("photos/b.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_b, 0, 0.0)
    cluster_run, clusters = harness.add_generation([
        ("k|a|000000", [o1]), ("k|b|000001", [o2]),
    ])
    dialog = harness.build_dialog(qtbot)
    # 簇 1 已确认给张三；簇 2 未指派。
    dialog._workbench_service.assign_person(
        AssignClusterPersonCommand(cluster_id=clusters[0].id, person_id=person.id),
        actor=HUMAN_ACTOR,
    )
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)
    # 批量选中两簇 + 目标人员张三。
    for row in range(dialog._cluster_list.count()):
        dialog._cluster_list.item(row).setSelected(True)
    index = dialog._person_combo.findData(person.id)
    dialog._person_combo.setCurrentIndex(index)

    # 预演：第一簇跳过（已确认）、第二簇执行。
    plan = dialog._plan_confirm(
        [clusters[0].id, clusters[1].id], person.id,
    )
    assert [action for _, _, action, _ in plan] == ["skip", "assign"]
    # N-1：skip 项必须携带可读原因（不得展示 None）。
    from photo_archiver.presentation import ui_text as ui_text_module

    assert plan[0][3] == ui_text_module.CLUSTER_PAIRING_CONFIRMED_SKIP

    monkeypatch.setattr(
        "photo_archiver.presentation.views.cluster_results_dialog.QMessageBox.exec",
        lambda self: __import__("PySide6").QtWidgets.QMessageBox.StandardButton.Ok,
    )
    dialog._on_confirm_clicked()

    summary = dialog._feedback_label.text()
    assert "成功 1" in summary and "跳过 1" in summary and "失败 0" in summary
    active = {
        assignment.cluster_id: assignment
        for assignment in dialog._results_service.assignments_active(cluster_run.id)
    }
    assert active[clusters[1].id].status == "confirmed"
    assert active[clusters[1].id].person_id == person.id


def test_batch_reject_reports_skip_reasons(qtbot, monkeypatch):
    harness = _Harness()
    person = harness.add_person("张三", 1)
    other = harness.add_person("李四", 2)
    photo_a = harness.add_photo("photos/a.jpg")
    photo_b = harness.add_photo("photos/b.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_b, 0, 0.0)
    _cluster_run, clusters = harness.add_generation([
        ("k|a|000000", [o1]), ("k|b|000001", [o2]),
    ])
    dialog = harness.build_dialog(qtbot)
    dialog._workbench_service.assign_person(
        AssignClusterPersonCommand(cluster_id=clusters[0].id, person_id=person.id),
        actor=HUMAN_ACTOR,
    )
    dialog.refresh()
    for row in range(dialog._cluster_list.count()):
        dialog._cluster_list.item(row).setSelected(True)
    index = dialog._person_combo.findData(other.id)
    dialog._person_combo.setCurrentIndex(index)

    monkeypatch.setattr(
        "photo_archiver.presentation.views.cluster_results_dialog.QMessageBox.exec",
        lambda self: __import__("PySide6").QtWidgets.QMessageBox.StandardButton.Ok,
    )
    dialog._on_reject_clicked()

    summary = dialog._feedback_label.text()
    assert "成功 0" in summary and "跳过 2" in summary
    # 两簇的现有决策均未被拒绝（拒绝对象是簇×人员配对，均非李四）。
    for cluster in clusters:
        latest = harness.assignments.list_latest_decision(cluster.id)
        assert latest is None or latest.status != "rejected"


# ── 照片忽略 / 恢复（逐项反馈 + 标记） ──────────────────────────────────────


def test_ignore_marks_render_after_service_and_refresh(qtbot):
    """忽略/恢复经代际作用域服务执行（面板按钮已撤，入口=照片详情）；
    刷新后组内照片行携带「（已忽略）」标记，恢复后标记消失。"""
    harness = _Harness()
    person = harness.add_person("张三", 1)
    photo_a = harness.add_photo("photos/a.jpg")
    photo_b = harness.add_photo("photos/b.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_b, 0, 0.0)
    cluster_run, clusters = harness.add_generation([("k|a|000000", [o1, o2])])
    _suggest, workbench, ignore, _results, _roster = harness.build_services()
    workbench.assign_person(
        AssignClusterPersonCommand(cluster_id=clusters[0].id, person_id=person.id),
        actor=HUMAN_ACTOR,
    )
    dialog = harness.build_dialog(qtbot)
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)

    ignore.ignore_photos(IgnorePhotosCommand(
        cluster_run_id=cluster_run.id, photo_ids=(photo_a,),
    ))
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)
    texts = [dialog._photo_grid.item(i).text()
             for i in range(dialog._photo_grid.count())]
    assert any("（已忽略）" in t for t in texts)
    assert harness.ignores.find(cluster_run.id, photo_a) is not None

    ignore.restore_photos(RestorePhotosCommand(
        cluster_run_id=cluster_run.id, photo_ids=(photo_a,),
    ))
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)
    texts = [dialog._photo_grid.item(i).text()
             for i in range(dialog._photo_grid.count())]
    assert not any("（已忽略）" in t for t in texts)
    assert harness.ignores.find(cluster_run.id, photo_a) is None


# ── Owner 2026-10-31：批量通过（组级人工终审） ───────────────────────────────


def test_batch_pass_button_enabled_only_with_actionable_selection(qtbot):
    """Owner 2026-10-31 防呆：0 选区禁用；全为已确认组禁用（纯空转）；
    存在可处理组（建议/自动确认/未指派以外可跳过）即启用。"""
    harness = _Harness()
    alice = harness.add_person("1张三", 1)
    photo_a = harness.add_photo("photos/a.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    _cluster_run, clusters = harness.add_generation([("k|a|000000", [o1])])
    _suggest, workbench, _ignore, results, roster = harness.build_services()
    harness.assignments.add_assignments([
        ClusterPersonAssignment(
            cluster_id=clusters[0].id, person_id=alice.id,
            source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION, created_at=datetime.now(),
        ),
    ])
    dialog = ClusterResultsDialog(
        results, harness.recognition_run.id,
        suggest_service=_suggest, workbench_service=workbench,
        ignore_service=_ignore, list_persons=roster,
    )
    qtbot.addWidget(dialog)
    dialog.refresh()
    dialog._cluster_list.clearSelection()
    assert not dialog._batch_pass_button.isEnabled()

    dialog._cluster_list.setCurrentRow(0)
    assert dialog._batch_pass_button.isEnabled()  # 建议行＝可处理

    # 终审确认后：全部选中组均已确认 → 批量通过禁用（纯空转）。
    assignment = dialog._assignments_by_cluster()[clusters[0].id]
    workbench.confirm(ConfirmAssignmentCommand(assignment.id))
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)
    assert not dialog._batch_pass_button.isEnabled()


def test_confirm_button_shows_confirmed_and_disabled_for_confirmed_cluster(qtbot):
    """Owner 2026-10-31 防呆：选中已确认组＝确认键变「已确认」且不可点；
    未确认组恢复「确认」可用。"""
    harness = _Harness()
    alice = harness.add_person("1张三", 1)
    photo_a = harness.add_photo("photos/a.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    _cluster_run, clusters = harness.add_generation([("k|a|000000", [o1])])
    _suggest, workbench, _ignore, results, roster = harness.build_services()
    harness.assignments.add_assignments([
        ClusterPersonAssignment(
            cluster_id=clusters[0].id, person_id=alice.id,
            source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION, created_at=datetime.now(),
        ),
    ])
    dialog = ClusterResultsDialog(
        results, harness.recognition_run.id,
        suggest_service=_suggest, workbench_service=workbench,
        ignore_service=_ignore, list_persons=roster,
    )
    qtbot.addWidget(dialog)
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)
    assert dialog._confirm_button.text() == text.CLUSTER_PAIRING_CONFIRM_BUTTON
    assert dialog._confirm_button.isEnabled()

    assignment = dialog._assignments_by_cluster()[clusters[0].id]
    workbench.confirm(ConfirmAssignmentCommand(assignment.id))
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)
    assert dialog._confirm_button.text() == text.CLUSTER_PAIRING_CONFIRMED_BUTTON
    assert not dialog._confirm_button.isEnabled()


def test_batch_pass_confirms_selected_clusters(qtbot, monkeypatch):
    """批量通过：suggested→confirm；auto_confirmed→按本组指派人人工终审；
    未指派组跳过。确认前预演各组信息，执行后反馈统计并刷新。"""
    harness = _Harness()
    alice = harness.add_person("1张三", 1)
    bob = harness.add_person("2李四", 2)
    harness.add_person("3王五", 3)
    photo_a = harness.add_photo("photos/a.jpg")
    photo_b = harness.add_photo("photos/b.jpg")
    photo_c = harness.add_photo("photos/c.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_b, 0, 180.0)
    o3 = harness.add_observation(photo_c, 0, 90.0)
    _cluster_run, clusters = harness.add_generation([
        ("k|a|000000", [o1]),
        ("k|b|000001", [o2]),
        ("k|c|000002", [o3]),
    ])
    _suggest, workbench, _ignore, results, roster = harness.build_services()
    now = datetime.now()
    # 组 1＝建议行（suggested）；组 2＝位置自动确认行（auto_confirmed，待人工终审）；
    # 组 3＝未指派（跳过）。
    harness.assignments.add_assignments([
        ClusterPersonAssignment(
            cluster_id=clusters[0].id, person_id=alice.id,
            source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION, created_at=now,
        ),
        ClusterPersonAssignment(
            cluster_id=clusters[1].id, person_id=bob.id,
            source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM, created_at=now,
            status=ASSIGNMENT_STATUS_AUTO_CONFIRMED,
        ),
    ])
    dialog = ClusterResultsDialog(
        results, harness.recognition_run.id,
        suggest_service=_suggest, workbench_service=workbench,
        ignore_service=_ignore, list_persons=roster,
    )
    qtbot.addWidget(dialog)
    dialog.refresh()
    dialog._cluster_list.clearSelection()
    assert not dialog._batch_pass_button.isEnabled()

    dialog._cluster_list.selectAll()
    assert dialog._batch_pass_button.isEnabled()
    # 预演对话框：确认（Ok）继续。
    monkeypatch.setattr(
        "photo_archiver.presentation.views.cluster_results_dialog.QMessageBox.exec",
        lambda self: QMessageBox.StandardButton.Ok,
    )
    dialog._on_batch_pass_clicked()

    summary = dialog._feedback_label.text()
    assert "成功 2" in summary
    assert "跳过 1" in summary
    # 组 1：建议行 → confirmed。
    assert dialog._assignments_by_cluster()[clusters[0].id].status == "confirmed"
    # 组 2：自动确认行 → 人工终审 confirmed（同一人）。
    promoted = dialog._assignments_by_cluster()[clusters[1].id]
    assert promoted.status == "confirmed" and promoted.person_id == bob.id
    # 组 3：未指派 → 仍无有效指派。
    assert clusters[2].id not in dialog._assignments_by_cluster()


def test_batch_pass_plan_dialog_lists_cluster_info(qtbot, monkeypatch):
    """确认前预演＝各组信息（标签）＋跳过原因；取消（Cancel）零写入。"""
    harness = _Harness()
    alice = harness.add_person("1张三", 1)
    photo_a = harness.add_photo("photos/a.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    _cluster_run, clusters = harness.add_generation([("k|a|000000", [o1])])
    _suggest, workbench, _ignore, results, roster = harness.build_services()
    harness.assignments.add_assignments([
        ClusterPersonAssignment(
            cluster_id=clusters[0].id, person_id=alice.id,
            source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION, created_at=datetime.now(),
        ),
    ])
    dialog = ClusterResultsDialog(
        results, harness.recognition_run.id,
        suggest_service=_suggest, workbench_service=workbench,
        ignore_service=_ignore, list_persons=roster,
    )
    qtbot.addWidget(dialog)
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)

    shown: list[str] = []

    class _PlanBox:
        StandardButton = QMessageBox.StandardButton

        def __init__(self, parent=None):
            pass
        def setWindowTitle(self, title):
            pass
        def setText(self, body_text):
            shown.append(body_text)
        def setStandardButtons(self, *_args):
            pass
        def setDefaultButton(self, *_args):
            pass
        def exec(self):
            return QMessageBox.StandardButton.Cancel  # 取消＝零写入

    monkeypatch.setattr(
        "photo_archiver.presentation.views.cluster_results_dialog.QMessageBox",
        _PlanBox,
    )
    dialog._on_batch_pass_clicked()
    assert any("批量通过" in body_text and "第 1 组" in body_text for body_text in shown)
    # 取消 → 零写入（仍为 suggested）。
    assert dialog._assignments_by_cluster()[clusters[0].id].status == "suggested"


def test_ignore_command_scope_and_projection_revocation(qtbot):
    """忽略服务的完整链路在对话框场景下语义一致（投影撤销+作用域）。"""
    harness = _Harness()
    person = harness.add_person("张三", 1)
    photo_a = harness.add_photo("photos/a.jpg")
    photo_b = harness.add_photo("photos/b.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_b, 0, 0.0)
    cluster_run, clusters = harness.add_generation([("k|a|000000", [o1, o2])])
    suggest, workbench, ignore, results, roster = harness.build_services()
    workbench.assign_person(
        AssignClusterPersonCommand(cluster_id=clusters[0].id, person_id=person.id),
        actor=HUMAN_ACTOR,
    )

    result = ignore.ignore_photos(IgnorePhotosCommand(
        cluster_run_id=cluster_run.id, photo_ids=(photo_a,),
    ))

    assert result.succeeded_count == 1 and result.revoked_projections == 1
    rows = [row for row in harness.recognition.list_by_photo(photo_a)
            if row.person_id == person.id and row.assignment_id is not None]
    assert rows[0].status is MatchStatus.REJECTED


# ── §5.4 详图导航 ────────────────────────────────────────────────────────────


def test_photo_detail_stub_and_navigation(tmp_path, qtbot, monkeypatch):
    """详图存根构建 + 上一张/下一张在本组照片间循环切换。"""
    harness = _Harness()
    photo_a = harness.add_photo(str(tmp_path / "a.jpg"))
    photo_b = harness.add_photo(str(tmp_path / "b.jpg"))
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_b, 0, 0.0)
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.jpg").write_bytes(b"x")
    harness.add_generation([("k|a|000000", [o1, o2])])
    dialog = harness.build_dialog(qtbot)
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)

    stub = dialog._build_photo_stub(photo_a)
    assert stub is not None and stub.original_name == "a.jpg"

    opened: list = []

    class _FakeSignal:
        def connect(self, *_args, **_kwargs): pass
        def disconnect(self, *_args, **_kwargs): pass

    class _FakeDetail:
        def __init__(self, photo, **kwargs):
            opened.append(photo)
            self.finished = _FakeSignal()  # P6：详图生命周期信号（真实 QDialog 契约）
            self.navigation_requested = _FakeSignal()  # 阶段 C：内嵌导航信号
        def show(self): pass
        def raise_(self): pass
        def close(self): pass
        def deleteLater(self): pass
        def set_navigation_position(self, position_text): pass
        def replace_photo(self, photo, badge=None, thumbnail_path=None):
            opened.append(photo)

    monkeypatch.setattr(
        "photo_archiver.presentation.views.cluster_results_dialog.PhotoDetailDialog",
        _FakeDetail,
    )
    dialog._detail_photos = [photo_a, photo_b]
    dialog._detail_index = 0
    dialog._open_detail()
    dialog._on_detail_prev_next(1)   # → b
    dialog._on_detail_prev_next(1)   # 循环回 a
    dialog._on_detail_prev_next(-1)  # → b
    assert [p.original_name for p in opened] == ["a.jpg", "b.jpg", "a.jpg", "b.jpg"]


# ── P6：大图导航健壮性（阶段 2） ─────────────────────────────────────────────


def _two_photo_dialog(qtbot, tmp_path):
    """One generation, two photos on absolute paths（stub 可构建，详图可打开）。"""
    harness = _Harness()
    photo_a = harness.add_photo(str(tmp_path / "a.jpg"))
    photo_b = harness.add_photo(str(tmp_path / "b.jpg"))
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_b, 0, 180.0)
    harness.add_generation([("k|a|000000", [o1]), ("k|b|000001", [o2])])
    dialog = harness.build_dialog(qtbot)
    return dialog, photo_a, photo_b


def test_detail_dialog_carries_embedded_navigation(qtbot, tmp_path):
    """任务书阶段 C（D4=B1）：导航内嵌详图——面板无常驻按钮，打开即有
    "第 x/y 张"计数；任何关闭路径（close → finished）回收对话框。"""
    dialog, _photo_a, _photo_b = _two_photo_dialog(qtbot, tmp_path)
    assert not hasattr(dialog, "_detail_prev_button")
    assert not hasattr(dialog, "_detail_next_button")

    dialog._photo_grid.itemDoubleClicked.emit(dialog._photo_grid.item(0))
    assert dialog._detail_dialog is not None
    # 装置每组一簇一照片：计数如实反映组内照片数。
    assert "第 1 / 1 张" in dialog._detail_dialog._navigation_position_label.text()

    # 任何关闭路径（此处标题栏/程序化 close → finished）都回收对话框。
    dialog._detail_dialog.close()
    assert dialog._detail_dialog is None
    qtbot.wait(100)  # 同上：解码任务/延迟销毁沉降（PySide6 6.11.1 竞态）


def test_generation_switch_closes_open_detail(qtbot, tmp_path):
    """P6：切换代际 = 快照失效——已打开的详图自动关闭并回收。"""
    dialog, _photo_a, _photo_b = _two_photo_dialog(qtbot, tmp_path)
    other_index = 1 if dialog._generation_combo.currentIndex() == 0 else 0
    dialog._photo_grid.itemDoubleClicked.emit(dialog._photo_grid.item(0))
    assert dialog._detail_dialog is not None

    dialog._generation_combo.setCurrentIndex(other_index)

    assert dialog._detail_dialog is None
    # PySide6 6.11.1 + pytest-qt 拆除时序竞态（任务书阶段 C 记录）：在飞的
    # 高清解码任务与详图 deleteLater 组合时，测试体结束后的事件处理可能
    # 触发原生崩溃（独立运行/生产事件循环无此窗口）。在体内让解码任务与
    # 延迟销毁沉降，保证关闭路径断言之外的可复现性。
    qtbot.wait(100)


def test_refresh_closes_open_detail(qtbot, tmp_path):
    """P6：refresh（簇列表重载入口）同样关闭已打开的详图。"""
    dialog, _photo_a, _photo_b = _two_photo_dialog(qtbot, tmp_path)
    dialog._photo_grid.itemDoubleClicked.emit(dialog._photo_grid.item(0))
    assert dialog._detail_dialog is not None

    dialog.refresh()

    assert dialog._detail_dialog is None
    qtbot.wait(100)  # 同上：解码任务/延迟销毁沉降（PySide6 6.11.1 竞态）


def test_detail_nav_missing_photo_reports_and_keeps_index(qtbot, tmp_path):
    """P6：目标照片构建不出详图 → 可见反馈且不推进索引（不静默、不跳位）。"""
    dialog, _photo_a, _photo_b = _two_photo_dialog(qtbot, tmp_path)
    dialog._photo_grid.itemDoubleClicked.emit(dialog._photo_grid.item(0))
    assert dialog._detail_dialog is not None
    assert dialog._detail_index == 0
    feedback_before = dialog._feedback_label.text()

    # 模拟快照失效（正常路径已在切代际/刷新时关闭详图；此处覆盖防御分支）。
    dialog._current = None
    dialog._on_detail_prev_next(1)  # 详图内嵌 ‹ › / ← → 的宿主端接收槽

    assert dialog._feedback_label.text() != feedback_before
    assert text.CLUSTER_DETAIL_PHOTO_MISSING in dialog._feedback_label.text()
    assert dialog._detail_index == 0  # 未命中不推进索引
    assert dialog._detail_dialog is not None  # 现有详图保持原样
    qtbot.wait(100)  # 同上：解码任务/延迟销毁沉降（PySide6 6.11.1 竞态）

# ── 视觉对齐定向断言（taskbook-5 派生方案 B；Owner 2026-10-30 决策 #4=B）──


def test_decision_status_rendered_as_badge_with_severity_mapping(qtbot):
    """落点 3：配对状态徽章化——文字承载状态（非仅色），severity 五态映射。"""
    harness = _Harness()
    person = harness.add_person("张三", 1)
    photo_a = harness.add_photo("photos/a.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    _, clusters = harness.add_generation([("k|a|000000", [o1])])
    suggest, workbench, ignore, results, roster = harness.build_services()
    dialog = ClusterResultsDialog(
        results, harness.recognition_run.id,
        suggest_service=suggest, workbench_service=workbench,
        ignore_service=ignore, list_persons=roster,
    )
    qtbot.addWidget(dialog)

    # 无指派 → 未匹配（neutral）。
    assert dialog._decision_badge.text() == text.CLUSTER_PAIRING_UNMATCHED
    assert dialog._decision_badge.property("severity") == "neutral"

    # 人工指派（confirmed 前= suggested 建议态？assign_person 直接生成 confirmed 行）
    workbench.assign_person(
        AssignClusterPersonCommand(cluster_id=clusters[0].id, person_id=person.id),
        actor=HUMAN_ACTOR,
    )
    dialog.refresh()
    assert "张三" in dialog._decision_badge.text()
    assert dialog._decision_badge.property("severity") in ("success", "warning")


def test_pairing_run_status_label_is_neutral_badge(qtbot):
    """落点 4：run 照片处理状态行单一 neutral 徽章（七计数文本语义不变）。"""
    harness = _Harness()
    photo_a = harness.add_photo("photos/a.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    harness.add_generation(
        [("k|a|000000", [o1])], outcomes={photo_a: "no_face"},
    )
    dialog = harness.build_dialog(qtbot)

    assert dialog._run_status_label.property("severity") == "neutral"
    status = dialog._run_status_label.text()
    assert "0 脸 1" in status and "有脸 0" in status  # 七计数文本零变化


def test_pairing_feedback_row_is_card_contained(qtbot):
    """落点 5：反馈行 Card 容器化（文字零变化）。"""
    from photo_archiver.presentation.visual_style import CARD_OBJECT_NAME

    harness = _Harness()
    photo_a = harness.add_photo("photos/a.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    harness.add_generation([("k|a|000000", [o1])])
    dialog = harness.build_dialog(qtbot)

    assert dialog._feedback_card.objectName() == CARD_OBJECT_NAME
    assert dialog._feedback_label.parent() is dialog._feedback_card


# ── Owner 2026-10-31：切簇跟随目标人员 / 详图内忽略恢复 ──────────────────────


def test_selecting_cluster_follows_its_assigned_person(qtbot):
    """切簇时目标人员下拉自动跟随该组当前指派（suggested/auto_confirmed/
    confirmed 均算）；未指派组保持当前选择不动。"""
    harness = _Harness()
    alice = harness.add_person("1张三", 1)
    bob = harness.add_person("2李四", 2)
    photo_a = harness.add_photo("photos/a.jpg")
    photo_b = harness.add_photo("photos/b.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_b, 0, 180.0)
    _cluster_run, clusters = harness.add_generation([
        ("k|a|000000", [o1]),
        ("k|b|000001", [o2]),
    ])
    suggest, workbench, ignore, results, roster = harness.build_services()
    workbench.assign_person(
        AssignClusterPersonCommand(cluster_id=clusters[0].id, person_id=alice.id),
        actor=HUMAN_ACTOR,
    )
    workbench.assign_person(
        AssignClusterPersonCommand(cluster_id=clusters[1].id, person_id=bob.id),
        actor=HUMAN_ACTOR,
    )
    dialog = ClusterResultsDialog(
        results, harness.recognition_run.id,
        suggest_service=suggest, workbench_service=workbench,
        ignore_service=ignore, list_persons=roster,
    )
    qtbot.addWidget(dialog)

    dialog._cluster_list.setCurrentRow(0)
    assert dialog._person_combo.currentText() == "1张三"
    dialog._cluster_list.setCurrentRow(1)
    assert dialog._person_combo.currentText() == "2李四"
    dialog._cluster_list.setCurrentRow(0)
    assert dialog._person_combo.currentText() == "1张三"


def test_detail_dialog_toggle_ignore_keeps_detail_open(tmp_path, qtbot):
    """详图内忽略/恢复（Owner 2026-10-31）：单照片服务调用＋原位重渲染——
    详图不关闭、组内照片行随忽略标记刷新、按钮形态随状态切换。"""
    harness = _Harness()
    photo_a = harness.add_photo(str(tmp_path / "a.jpg"))
    (tmp_path / "a.jpg").write_bytes(b"x")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    cluster_run, _clusters = harness.add_generation([("k|a|000000", [o1])])
    dialog = harness.build_dialog(qtbot)
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)
    dialog._on_photo_double_clicked(dialog._photo_grid.item(0))
    detail = dialog._detail_dialog
    assert detail is not None
    assert detail.isVisible()
    assert detail._ignore_button.text() == text.CLUSTER_DETAIL_IGNORE_BUTTON

    detail._ignore_button.click()
    assert harness.ignores.find(cluster_run.id, photo_a) is not None
    assert detail._ignore_button.text() == text.CLUSTER_DETAIL_RESTORE_BUTTON
    assert detail.isVisible()  # 详图未关（原位重渲染契约）
    assert any(
        "（已忽略）" in dialog._photo_grid.item(i).text()
        for i in range(dialog._photo_grid.count())
    )

    detail._ignore_button.click()
    assert harness.ignores.find(cluster_run.id, photo_a) is None
    assert detail._ignore_button.text() == text.CLUSTER_DETAIL_IGNORE_BUTTON


# ── Owner 2026-10-31 卡顿修复：A 后台管线 + B 共享快照 ───────────────────────


def test_batch_confirm_reuses_shared_snapshot(qtbot):
    """卡顿修复·B：共享快照下 N 簇批量只加载一次全代际观测——无上下文时每
    簇 2 次（_sink_confirmation 与 photos_of_cluster 各一次），N 簇即 2N 次。"""
    harness = _Harness()
    alice = harness.add_person("1张三", 1)
    bob = harness.add_person("2李四", 2)
    photo_a = harness.add_photo("photos/a.jpg")
    photo_b = harness.add_photo("photos/b.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_b, 0, 180.0)
    _cluster_run, clusters = harness.add_generation([
        ("k|a|000000", [o1]),
        ("k|b|000001", [o2]),
    ])
    _suggest, workbench, _ignore, _results, _roster = harness.build_services()
    harness.assignments.add_assignments([
        ClusterPersonAssignment(
            cluster_id=clusters[0].id, person_id=alice.id,
            source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION, created_at=datetime.now(),
        ),
        ClusterPersonAssignment(
            cluster_id=clusters[1].id, person_id=bob.id,
            source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION, created_at=datetime.now(),
        ),
    ])

    class _CountingObservations:
        """Delegate everything except list_by_run, which is counted."""

        def __init__(self, inner):
            self._inner = inner
            self.list_by_run_calls = 0

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def list_by_run(self, run_id):
            self.list_by_run_calls += 1
            return self._inner.list_by_run(run_id)

    counting = _CountingObservations(harness.observations)
    workbench._observation_repository = counting
    context = workbench.create_batch_context()

    for cluster in clusters:
        assignment = workbench._assignment_repository.list_latest_decision(
            cluster.id,
        )
        workbench.confirm(
            ConfirmAssignmentCommand(assignment.id), context=context,
        )

    assert counting.list_by_run_calls == 1  # 整批一次（无上下文＝4 次）
    for cluster in clusters:
        latest = workbench._assignment_repository.list_latest_decision(cluster.id)
        assert latest.status == ASSIGNMENT_STATUS_CONFIRMED


def test_batch_pass_runs_through_task_pipeline(tmp_path, qtbot, monkeypatch):
    """卡顿修复·A：注入协调器+执行器后批量通过走后台任务管线——准入占位、
    完成后反馈+刷新+按钮恢复，状态落库与同步路径一致。"""
    from photo_archiver.presentation.task_coordinator import TaskCoordinator
    from photo_archiver.workers.qt_executor import QtWorkerExecutor

    harness = _Harness()
    alice = harness.add_person("1张三", 1)
    photo_a = harness.add_photo(str(tmp_path / "a.jpg"))
    (tmp_path / "a.jpg").write_bytes(b"x")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    _cluster_run, clusters = harness.add_generation([("k|a|000000", [o1])])
    _suggest, workbench, _ignore, results, roster = harness.build_services()
    harness.assignments.add_assignments([
        ClusterPersonAssignment(
            cluster_id=clusters[0].id, person_id=alice.id,
            source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION, created_at=datetime.now(),
        ),
    ])
    coordinator = TaskCoordinator()
    dialog = ClusterResultsDialog(
        results, harness.recognition_run.id,
        suggest_service=_suggest, workbench_service=workbench,
        ignore_service=_ignore, list_persons=roster,
        task_coordinator=coordinator,
        task_executor=QtWorkerExecutor(),
    )
    qtbot.addWidget(dialog)
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)

    monkeypatch.setattr(
        "photo_archiver.presentation.views.cluster_results_dialog.QMessageBox.exec",
        lambda self: QMessageBox.StandardButton.Ok,
    )
    dialog._on_batch_pass_clicked()
    assert coordinator.is_busy  # 准入占位（窗口级冲突门同源）

    qtbot.waitUntil(
        lambda: "成功 1" in dialog._feedback_label.text(), timeout=30000,
    )  # 全量负载下真实线程池启动+事件送达可超 10s（追加轮 13 同类放宽）
    assert not coordinator.is_busy
    assert not dialog._busy
    latest = dialog._assignments_by_cluster()[clusters[0].id]
    assert latest.status == ASSIGNMENT_STATUS_CONFIRMED


def test_batch_progress_bar_lifecycle(qtbot):
    """Owner 2026-10-31：批量终审进度条——started 可见（总数未知＝脉冲态）、
    progress 定值、终态（完成）隐藏。"""
    from photo_archiver.workers.events import (
        TaskCompleted,
        TaskProgress,
        TaskStarted,
    )
    from photo_archiver.workers.application_tasks import PairingBatchOutcome

    harness = _Harness()
    _suggest, workbench, _ignore, results, roster = harness.build_services()
    dialog = ClusterResultsDialog(
        results, harness.recognition_run.id,
        suggest_service=_suggest, workbench_service=workbench,
        ignore_service=_ignore, list_persons=roster,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._on_batch_started(TaskStarted("pairing_batch"))
    assert dialog._batch_progress.isVisible()
    assert dialog._batch_progress.minimum() == 0
    assert dialog._batch_progress.maximum() == 0  # 总数未知＝脉冲未知态

    dialog._on_batch_progress(TaskProgress(
        "pairing_batch", current=1, total=3, message="第 1 组",
    ))
    assert dialog._batch_progress.maximum() == 3
    assert dialog._batch_progress.value() == 1

    dialog._on_batch_terminal(TaskCompleted(
        "pairing_batch",
        result=PairingBatchOutcome(
            action="批量通过", succeeded=1, skipped=0, failed=0, outcomes=(),
        ),
    ))
    assert not dialog._batch_progress.isVisible()


def test_reopened_dialog_reattaches_to_running_batch(tmp_path, qtbot, monkeypatch):
    """在飞批次的新对话框实例自动附着（忙碌态+进度条），终态经协调器信号
    驱动两个并存实例——确定性：确认桩加 0.5s 延迟保证在飞窗口足够宽。"""

    harness = _Harness()
    alice = harness.add_person("1张三", 1)
    photo_a = harness.add_photo(str(tmp_path / "a.jpg"))
    (tmp_path / "a.jpg").write_bytes(b"x")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    _cluster_run, clusters = harness.add_generation([("k|a|000000", [o1])])
    _suggest, workbench, _ignore, results, roster = harness.build_services()
    harness.assignments.add_assignments([
        ClusterPersonAssignment(
            cluster_id=clusters[0].id, person_id=alice.id,
            source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
        ),
    ])

    # 确认桩：0.5s 延迟（让第二实例必然在飞窗口内构造并附着）。
    real_confirm = workbench.confirm

    def slow_confirm(command, context=None):
        time.sleep(0.5)
        return real_confirm(command, context=context)

    monkeypatch.setattr(workbench, "confirm", slow_confirm)

    coordinator = TaskCoordinator()

    def make_dialog():
        dialog = ClusterResultsDialog(
            results, harness.recognition_run.id,
            suggest_service=_suggest, workbench_service=workbench,
            ignore_service=_ignore, list_persons=roster,
            task_coordinator=coordinator,
            task_executor=QtWorkerExecutor(),
        )
        qtbot.addWidget(dialog)
        dialog.show()
        return dialog

    dialog1 = make_dialog()
    dialog1.refresh()
    dialog1._cluster_list.setCurrentRow(0)
    monkeypatch.setattr(
        "photo_archiver.presentation.views.cluster_results_dialog.QMessageBox.exec",
        lambda self: QMessageBox.StandardButton.Ok,
    )
    dialog1._on_batch_pass_clicked()
    assert coordinator.is_busy

    # 在飞窗口内构造第二实例：自动附着忙碌态与脉冲进度条。
    dialog2 = make_dialog()
    assert dialog2._busy
    assert dialog2._batch_progress.isVisible()

    # 终态经协调器信号同时驱动两个实例：反馈落盘 + 状态确认。
    qtbot.waitUntil(
        lambda: "成功 1" in dialog2._feedback_label.text(), timeout=30000,
    )
    assert not dialog2._busy
    assert not dialog2._batch_progress.isVisible()
    latest = dialog2._assignments_by_cluster()[clusters[0].id]
    assert latest.status == ASSIGNMENT_STATUS_CONFIRMED
    assert "成功 1" in dialog1._feedback_label.text()


def test_close_while_batch_running_is_blocked(tmp_path, qtbot, monkeypatch):
    """Owner 2026-10-31：在飞批次拒绝关闭（终态事件必须送达本对话框，
    无失联态）；完成后关闭恢复正常。"""
    harness = _Harness()
    alice = harness.add_person("1张三", 1)
    photo_a = harness.add_photo(str(tmp_path / "a.jpg"))
    (tmp_path / "a.jpg").write_bytes(b"x")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    _cluster_run, clusters = harness.add_generation([("k|a|000000", [o1])])
    _suggest, workbench, _ignore, results, roster = harness.build_services()
    harness.assignments.add_assignments([
        ClusterPersonAssignment(
            cluster_id=clusters[0].id, person_id=alice.id,
            source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION,
        ),
    ])

    real_confirm = workbench.confirm

    def slow_confirm(command, context=None):
        time.sleep(0.5)
        return real_confirm(command, context=context)

    monkeypatch.setattr(workbench, "confirm", slow_confirm)

    coordinator = TaskCoordinator()
    dialog = ClusterResultsDialog(
        results, harness.recognition_run.id,
        suggest_service=_suggest, workbench_service=workbench,
        ignore_service=_ignore, list_persons=roster,
        task_coordinator=coordinator,
        task_executor=QtWorkerExecutor(),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)
    monkeypatch.setattr(
        "photo_archiver.presentation.views.cluster_results_dialog.QMessageBox.exec",
        lambda self: QMessageBox.StandardButton.Ok,
    )
    dialog._on_batch_pass_clicked()
    assert dialog._busy

    dialog.close()  # Owner 关闭尝试：忙碌期被拒
    assert dialog.isVisible()  # 仍在（终态事件必须送达）

    qtbot.waitUntil(
        lambda: "成功 1" in dialog._feedback_label.text(), timeout=30000,
    )
    assert not dialog._busy
    dialog.close()
    assert not dialog.isVisible()

def test_batch_finalize_completes_at_realistic_scale_on_sqlite(
    make_sqlite_context, tmp_path, qtbot,
):
    """Owner 2026-10-31「卡住 0%」排查：真实 SQLite + run_immediate 事务链，
    40 簇 × 5 脸的批量终审必须完整执行（排除事务路径真卡死）；同时验证
    逐项提交后的 confirmed 落库与快照复用下的耗时上限（宽裕 60s 护栏）。"""
    import time

    from photo_archiver.domain import (
        FaceBox,
        FaceCluster,
        FaceClusterMember,
        FaceClusterRun,
        FaceEmbedding,
        FaceObservation,
    )
    from photo_archiver.workers.application_tasks import (
        PairingBatchFinalizeTask,
        PairingBatchItem,
    )

    context = make_sqlite_context(db_name="pairing_scale.db")
    services = context.services
    # 识别运行 + 观测/簇/代际全部走真实仓储（与应用同一条 SQLite 装配）。
    from photo_archiver.domain import RecognitionRun

    run = RecognitionRun(parameters={})
    repos = context.repositories
    repos.recognition_runs.add_run(run)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="v1")
    repos.face_clusters.add_cluster_run(cluster_run)

    observations = repos.face_observations
    persons = []
    for index in range(40):
        person = services.manage_people.add_person(
            AddPersonCommand(name=f"{index + 1}人员", identity=f"E{index:03d}"),
        )
        persons.append(person)

    from photo_archiver.domain import Photo, PhotoPath, PhotoPathBase

    clusters = []
    items: list[PairingBatchItem] = []
    for cluster_index in range(40):
        cluster = FaceCluster(
            cluster_run_id=cluster_run.id,
            run_id=run.id,
            ordinal=cluster_index,
            member_count=5,
            sort_key=f"k|{cluster_index:04d}",
        )
        # 每簇 5 张照片 × 1 脸（实机形状：组照单脸）：真实照片行满足 FK。
        batch_observations = []
        for face_index in range(5):
            photo_file = tmp_path / f"scale_{cluster_index}_{face_index}.jpg"
            photo_file.write_bytes(b"x")
            photo = Photo(
                path=PhotoPath(photo_file, base=PhotoPathBase.ABSOLUTE),
                original_name=photo_file.name,
            )
            repos.photos.add(photo)
            observation = FaceObservation(
                run_id=run.id,
                photo_id=photo.id,
                face_index=0,
                photo_face_count=1,
                det_score=0.9,
                box=FaceBox(0, 0, 10, 10),
                embedding=FaceEmbedding(tuple(
                    0.02 * ((cluster_index + face_index + d) % 5) for d in range(8)
                )),
                scope_verdict="in_selected_scope",
            )
            observations.add_many([observation])
            batch_observations.append(observation)
        repos.face_clusters.add_clusters([cluster])
        repos.face_clusters.add_members([
            FaceClusterMember(
                cluster_id=cluster.id,
                observation_id=observation.id,
                confidence=0.9,
            )
            for observation in batch_observations
        ])
        clusters.append(cluster)
    cluster_run.start()
    cluster_run.complete(40, 200, 0)
    repos.face_clusters.update_cluster_run(cluster_run)
    items = [
        PairingBatchItem(
            action="promote",
            cluster_id=cluster.id,
            label=f"第 {index + 1} 组 · {persons[index].name}",
            payload=str(persons[index].id),
        )
        for index, cluster in enumerate(clusters)
    ]

    task = PairingBatchFinalizeTask(
        services.pairing_workbench, tuple(items), "批量通过",
    )
    started = time.monotonic()
    outcome = task.execute()
    elapsed = time.monotonic() - started

    assert outcome.succeeded == 40
    assert outcome.failed == 0
    print(f"[SCALE] 40 簇 x 5 脸批量终审耗时 {elapsed:.2f}s（真实 SQLite + run_immediate）")
    assert elapsed < 60.0, f"批量终审在真实 SQLite 上耗时 {elapsed:.1f}s（护栏 60s）"


def test_batch_pipeline_completes_on_worker_thread_at_scale(
    make_sqlite_context, tmp_path, qtbot, monkeypatch,
):
    """Owner 2026-10-31「卡住 0%」复现探针：真实 SQLite + 真实 QThreadPool
    工作线程 + 对话框派发全链路，40 簇 × 28 脸（1120 观测 / 200 照片）。
    若管线在该组合下会挂，本测试将超时——通过即证明管线健康，
    实机异常＝运行了旧构建。"""
    import time

    from photo_archiver.domain import (
        FaceBox,
        FaceCluster,
        FaceClusterMember,
        FaceClusterRun,
        FaceEmbedding,
        FaceObservation,
        Photo,
        PhotoPath,
        PhotoPathBase,
    )
    from photo_archiver.presentation.task_coordinator import TaskCoordinator
    from photo_archiver.workers.application_tasks import PairingBatchItem
    from photo_archiver.workers.qt_executor import QtWorkerExecutor

    context = make_sqlite_context(db_name="pairing_worker_scale.db")
    services = context.services
    repos = context.repositories

    from photo_archiver.domain import RecognitionRun

    run = RecognitionRun(parameters={})
    repos.recognition_runs.add_run(run)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="v1")
    repos.face_clusters.add_cluster_run(cluster_run)

    persons = [
        services.manage_people.add_person(
            AddPersonCommand(name=f"{index + 1}人员", identity=f"E{index:03d}"),
        )
        for index in range(40)
    ]

    observations = repos.face_observations
    clusters = []
    for cluster_index in range(40):
        cluster = FaceCluster(
            cluster_run_id=cluster_run.id,
            run_id=run.id,
            ordinal=cluster_index,
            member_count=28,
            sort_key=f"k|{cluster_index:04d}",
        )
        batch_observations = []
        for face_index in range(28):
            photo_file = tmp_path / f"scale_{cluster_index}_{face_index}.jpg"
            photo_file.write_bytes(b"x")
            photo = Photo(
                path=PhotoPath(photo_file, base=PhotoPathBase.ABSOLUTE),
                original_name=photo_file.name,
            )
            repos.photos.add(photo)
            batch_observations.append(FaceObservation(
                run_id=run.id,
                photo_id=photo.id,
                face_index=0,
                photo_face_count=1,
                det_score=0.9,
                box=FaceBox(0, 0, 10, 10),
                embedding=FaceEmbedding(tuple(
                    0.02 * ((cluster_index + face_index + d) % 5) for d in range(8)
                )),
                scope_verdict="in_selected_scope",
            ))
        observations.add_many(batch_observations)
        repos.face_clusters.add_clusters([cluster])
        repos.face_clusters.add_members([
            FaceClusterMember(
                cluster_id=cluster.id,
                observation_id=observation.id,
                confidence=0.9,
            )
            for observation in batch_observations
        ])
        clusters.append(cluster)
    cluster_run.start()
    cluster_run.complete(40, 1120, 0)
    repos.face_clusters.update_cluster_run(cluster_run)

    items = [
        PairingBatchItem(
            action="promote",
            cluster_id=cluster.id,
            label=f"第 {index + 1} 组 · {persons[index].name}",
            payload=str(persons[index].id),
        )
        for index, cluster in enumerate(clusters)
    ]

    coordinator = TaskCoordinator()
    dialog = ClusterResultsDialog(
        services.cluster_results, run.id,
        suggest_service=services.suggest_pairings,
        workbench_service=services.pairing_workbench,
        ignore_service=services.photo_ignore,
        list_persons=services.list_persons,
        task_coordinator=coordinator,
        task_executor=QtWorkerExecutor(),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.refresh()

    started = time.monotonic()
    dialog._dispatch_batch(
        "批量通过", tuple(items),
    )
    assert coordinator.is_busy
    assert dialog._batch_progress.isVisible()  # 分发期即显示（脉冲）

    qtbot.waitUntil(
        lambda: not coordinator.is_busy, timeout=120000,
    )
    elapsed = time.monotonic() - started
    print(f"[SCALE-WORKER] 40 簇 x 28 脸经工作线程完成，耗时 {elapsed:.2f}s")
    assert not dialog._busy
    assert "成功 40" in dialog._feedback_label.text()
    assert elapsed < 60.0


def test_cluster_rows_carry_status_tints(qtbot):
    """Owner 2026-11-01：簇卡片底色＝右侧配对状态徽章同色系——已确认=淡绿、
    待确认(suggested)=淡橘黄、自动确认待终审=淡蓝、未匹配=淡灰；颜色来自
    令牌淡染（alpha≈17%）。"""
    harness = _Harness()
    alice = harness.add_person("1张三", 1)
    photo_a = harness.add_photo("photos/a.jpg")
    photo_b = harness.add_photo("photos/b.jpg")
    photo_c = harness.add_photo("photos/c.jpg")
    photo_d = harness.add_photo("photos/d.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_b, 0, 60.0)
    o3 = harness.add_observation(photo_c, 0, 120.0)
    o4 = harness.add_observation(photo_d, 0, 180.0)
    _cluster_run, clusters = harness.add_generation([
        ("k|a|000000", [o1]),
        ("k|b|000001", [o2]),
        ("k|c|000002", [o3]),
        ("k|d|000003", [o4]),
    ])
    _suggest, workbench, _ignore, results, roster = harness.build_services()
    now = datetime.now()
    # 簇 1=建议行（suggested 淡橘黄）；簇 2=自动确认行（淡蓝）；
    # 簇 3=人工指派终审（confirmed 淡绿）；簇 4=无指派（未匹配 淡灰）。
    harness.assignments.add_assignments([
        ClusterPersonAssignment(
            cluster_id=clusters[0].id, person_id=alice.id,
            source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION, created_at=now,
        ),
        ClusterPersonAssignment(
            cluster_id=clusters[1].id, person_id=alice.id,
            source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM, created_at=now,
            status=ASSIGNMENT_STATUS_AUTO_CONFIRMED,
        ),
    ])
    workbench.assign_person(
        AssignClusterPersonCommand(cluster_id=clusters[2].id, person_id=alice.id),
        actor=HUMAN_ACTOR,
    )
    dialog = ClusterResultsDialog(
        results, harness.recognition_run.id,
        suggest_service=_suggest, workbench_service=workbench,
        ignore_service=_ignore, list_persons=roster,
    )
    qtbot.addWidget(dialog)
    dialog.refresh()

    def tinted(token_name):
        color = QColor(token(token_name))
        color.setAlpha(44)
        return color

    assert dialog._cluster_list.item(0).background().color() == tinted("pa-warning-fg")
    assert dialog._cluster_list.item(1).background().color() == tinted("pa-info-fg")
    assert dialog._cluster_list.item(2).background().color() == tinted("pa-success-fg")
    assert dialog._cluster_list.item(3).background().color() == tinted("pa-text-secondary")


def test_cluster_rows_render_status_tints(qtbot):
    """渲染级回归（Owner 2026-11-01「界面依旧没变」实锤）：QSS ``::item``
    规则存在时样式表引擎丢弃模型 BackgroundRole 画笔——状态染色必须经
    ``_StatusTintDelegate`` 显式补画才上屏。断言像素而非模型：行内采样色
    须等于背景色与令牌的 alpha 合成（容差 ±10，跨平台亮度调制模型同
    test_visual_system 探针）。"""
    harness = _Harness()
    alice = harness.add_person("1张三", 1)
    photos = [harness.add_photo(f"photos/{n}.jpg") for n in "abcd"]
    obs = [harness.add_observation(p, 0, 60.0 * i) for i, p in enumerate(photos)]
    _cluster_run, clusters = harness.add_generation([
        (f"k|{n}|{i:06d}", [o]) for i, (n, o) in enumerate(zip("abcd", obs))
    ])
    _suggest, workbench, _ignore, results, roster = harness.build_services()
    now = datetime.now()
    harness.assignments.add_assignments([
        ClusterPersonAssignment(
            cluster_id=clusters[0].id, person_id=alice.id,
            source=ASSIGNMENT_SOURCE_ORDERED_SUGGESTION, created_at=now,
        ),
        ClusterPersonAssignment(
            cluster_id=clusters[1].id, person_id=alice.id,
            source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM, created_at=now,
            status=ASSIGNMENT_STATUS_AUTO_CONFIRMED,
        ),
    ])
    workbench.assign_person(
        AssignClusterPersonCommand(cluster_id=clusters[2].id, person_id=alice.id),
        actor=HUMAN_ACTOR,
    )
    # 生产观感＝视觉系统 QSS 在场（无 QSS 时原生样式自己画模型底色，与
    # 委托补画叠加成双重合成——断言必须对着真实样式跑）。
    qapp = QApplication.instance()
    qapp.setStyleSheet(build_stylesheet())
    try:
        _assert_rendered_tints(qtbot, results, _suggest, workbench,
                               _ignore, roster, harness)
    finally:
        qapp.setStyleSheet("")


def _assert_rendered_tints(qtbot, results, _suggest, workbench, _ignore,
                           roster, harness) -> None:
    dialog = ClusterResultsDialog(
        results, harness.recognition_run.id,
        suggest_service=_suggest, workbench_service=workbench,
        ignore_service=_ignore, list_persons=roster,
    )
    qtbot.addWidget(dialog)
    dialog.resize(1100, 720)
    dialog.show()
    for _ in range(10):
        qtbot.wait(10)
    dialog._cluster_list.clearSelection()
    for _ in range(10):
        qtbot.wait(10)

    image = dialog.grab().toImage()
    list_widget = dialog._cluster_list
    origin = list_widget.viewport().mapTo(dialog, QPoint(0, 0))

    def dominant_at(points):
        """多点采样取众数（文字/圆角等异物被排除，行底色胜出）。"""
        counts: dict[tuple[int, int, int], int] = {}
        for px, py in points:
            color = image.pixelColor(px, py)
            key = (color.red(), color.green(), color.blue())
            counts[key] = counts.get(key, 0) + 1
        return max(counts.items(), key=lambda kv: kv[1])[0]

    def sample(row):
        rect = list_widget.visualItemRect(list_widget.item(row))
        return dominant_at([
            (origin.x() + rect.x() + int(rect.width() * fx),
             origin.y() + rect.y() + int(rect.height() * fy))
            for fx in (0.75, 0.85) for fy in (0.35, 0.65)
        ])

    # 背景参照：列表内、最后一行下方的确定空白带（同行 x 取样避文字）。
    rect3 = list_widget.visualItemRect(list_widget.item(3))
    backdrop = dominant_at([
        (origin.x() + int(list_widget.viewport().width() * fx),
         origin.y() + rect3.y() + rect3.height() + 12)
        for fx in (0.5, 0.75, 0.85)
    ])

    alpha = 44 / 255.0
    for row, token_name in [
        (0, "pa-warning-fg"), (1, "pa-info-fg"),
        (2, "pa-success-fg"), (3, "pa-text-secondary"),
    ]:
        fg = QColor(token(token_name))
        expected = tuple(
            round(backdrop[i] * (1 - alpha) + channel * alpha)
            for i, channel in enumerate((fg.red(), fg.green(), fg.blue()))
        )
        found = sample(row)
        assert all(abs(found[i] - expected[i]) <= 10 for i in range(3)), (
            f"row {row} ({token_name}): sampled {found}, expected ≈{expected} "
            f"(backdrop {backdrop}) — tint not painted"
        )
        # 有意义性守卫：染色必须真的偏离背景（防止全白回归下断言空转）。
        assert any(abs(found[i] - backdrop[i]) >= 5 for i in range(3)), (
            f"row {row} ({token_name}): sampled {found} ≈ backdrop {backdrop}"
        )
