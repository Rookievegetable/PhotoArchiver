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
from datetime import datetime
from uuid import uuid4

from photo_archiver.application.commands.photo_ignore import (
    IgnorePhotosCommand,
)
from photo_archiver.application.services import (
    ClusterResultsService,
    ListPersonsService,
    PairingWorkbenchService,
    PhotoIgnoreService,
    SuggestPairingsService,
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
from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR
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


def test_ignore_and_restore_photos_via_grid(qtbot, monkeypatch):
    harness = _Harness()
    person = harness.add_person("张三", 1)
    photo_a = harness.add_photo("photos/a.jpg")
    photo_b = harness.add_photo("photos/b.jpg")
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(photo_b, 0, 0.0)
    cluster_run, cluster = harness.add_generation([("k|a|000000", [o1, o2])])
    cluster = cluster[0]
    harness.build_services()[1].assign_person(
        AssignClusterPersonCommand(cluster_id=cluster.id, person_id=person.id),
        actor=HUMAN_ACTOR,
    )
    dialog = harness.build_dialog(qtbot)
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)

    # 仅选中 photo_a 所在行并忽略。
    dialog._photo_grid.item(0).setSelected(True)
    monkeypatch.setattr(
        "photo_archiver.presentation.views.cluster_results_dialog.QMessageBox.exec",
        lambda self: __import__("PySide6").QtWidgets.QMessageBox.StandardButton.Ok,
    )
    dialog._on_ignore_clicked()

    summary = dialog._feedback_label.text()
    assert "成功 1" in summary
    assert "撤销投影 1 条" in summary
    dialog.refresh()
    dialog._cluster_list.setCurrentRow(0)
    texts = [dialog._photo_grid.item(i).text()
             for i in range(dialog._photo_grid.count())]
    assert any("（已忽略）" in t for t in texts)
    assert harness.ignores.find(cluster_run.id, photo_a) is not None

    # 恢复：标记消失，状态行删除。
    dialog._photo_grid.item(0).setSelected(True)
    dialog._on_restore_clicked()
    assert "成功 1" in dialog._feedback_label.text()
    assert harness.ignores.find(cluster_run.id, photo_a) is None


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
        def show(self): pass
        def raise_(self): pass
        def close(self): pass
        def deleteLater(self): pass
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


def test_detail_nav_buttons_track_detail_dialog_lifecycle(qtbot, tmp_path):
    """P6：上一张/下一张绑定详图生命周期——未开禁用/打开启用/关闭禁用。"""
    dialog, _photo_a, _photo_b = _two_photo_dialog(qtbot, tmp_path)
    assert dialog._detail_prev_button.isEnabled() is False
    assert dialog._detail_next_button.isEnabled() is False

    dialog._photo_grid.itemDoubleClicked.emit(dialog._photo_grid.item(0))
    assert dialog._detail_dialog is not None
    assert dialog._detail_prev_button.isEnabled() is True
    assert dialog._detail_next_button.isEnabled() is True

    # 任何关闭路径（此处标题栏/程序化 close → finished）都回到禁用态。
    dialog._detail_dialog.close()
    assert dialog._detail_dialog is None
    assert dialog._detail_prev_button.isEnabled() is False
    assert dialog._detail_next_button.isEnabled() is False


def test_generation_switch_closes_open_detail(qtbot, tmp_path):
    """P6：切换代际 = 快照失效——已打开的详图自动关闭并回到禁用态。"""
    dialog, _photo_a, _photo_b = _two_photo_dialog(qtbot, tmp_path)
    other_index = 1 if dialog._generation_combo.currentIndex() == 0 else 0
    dialog._photo_grid.itemDoubleClicked.emit(dialog._photo_grid.item(0))
    assert dialog._detail_dialog is not None

    dialog._generation_combo.setCurrentIndex(other_index)

    assert dialog._detail_dialog is None
    assert dialog._detail_prev_button.isEnabled() is False
    assert dialog._detail_next_button.isEnabled() is False


def test_refresh_closes_open_detail(qtbot, tmp_path):
    """P6：refresh（簇列表重载入口）同样关闭已打开的详图。"""
    dialog, _photo_a, _photo_b = _two_photo_dialog(qtbot, tmp_path)
    dialog._photo_grid.itemDoubleClicked.emit(dialog._photo_grid.item(0))
    assert dialog._detail_dialog is not None

    dialog.refresh()

    assert dialog._detail_dialog is None
    assert dialog._detail_next_button.isEnabled() is False


def test_detail_nav_missing_photo_reports_and_keeps_index(qtbot, tmp_path):
    """P6：目标照片构建不出详图 → 可见反馈且不推进索引（不静默、不跳位）。"""
    dialog, _photo_a, _photo_b = _two_photo_dialog(qtbot, tmp_path)
    dialog._photo_grid.itemDoubleClicked.emit(dialog._photo_grid.item(0))
    assert dialog._detail_dialog is not None
    assert dialog._detail_index == 0
    feedback_before = dialog._feedback_label.text()

    # 模拟快照失效（正常路径已在切代际/刷新时关闭详图；此处覆盖防御分支）。
    dialog._current = None
    dialog._detail_next_button.click()

    assert dialog._feedback_label.text() != feedback_before
    assert text.CLUSTER_DETAIL_PHOTO_MISSING in dialog._feedback_label.text()
    assert dialog._detail_index == 0  # 未命中不推进索引
    assert dialog._detail_dialog is not None  # 现有详图保持原样
