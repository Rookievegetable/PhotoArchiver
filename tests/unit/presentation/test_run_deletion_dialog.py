"""按识别运行删除对话框 + 名册页入口的界面测试（批次删除功能 D1~D7/D10）.

覆盖：

- 名单对话框：默认 A3 披露、A1 模式切换文案、硬阻断禁用执行按钮、
  知悉勾选门控确认按钮（取消持默认焦点）；
- 照片对话框：级联披露、purge 勾选警告、空快照空态、硬阻断禁用执行；
- 名册页：两个「删除该运行…」按钮随运行选择启停；来源批次标签带
  创建时间与状态（D10——同名批次不可再混淆）。

服务为真实应用服务 + 真实 SQLite（与服务层测试同构），不弹模态。
"""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDialogButtonBox, QPushButton

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.dtos import (
    RunPeopleDeletionPreview,
    RunPhotosDeletionPreview,
    RunRecordDeletionPreview,
    RunRecordDeletionResult,
)
from photo_archiver.application.services import (
    ClusterResultsService,
    DeletePersonService,
    DeleteRunPeopleService,
    DeleteRunPhotosService,
    DeleteRunRecordService,
    ListPersonsService,
    ListRecognitionRunsService,
    ManagePeopleService,
    RosterClusterStatsService,
)
from photo_archiver.domain.entities.import_batch import ImportBatch
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.people_admin_page import PeopleAdminPage
from photo_archiver.presentation.views.run_deletion_dialog import (
    RunPeopleDeletionDialog,
    RunPhotosDeletionDialog,
    RunRecordDeletionDialog,
)

_PEOPLE_BLOCKED = RunPeopleDeletionPreview(
    run_found=True, run_created_at=None, run_status="completed",
    cluster_count=2, decision_count=2,
    person_ids=(uuid4(), uuid4()), people_names=("人员甲", "人员乙"),
    embedding_count=0, recognition_count=2, assignment_count=2,
    sample_count=3, archive_count=1, ground_truth_count=1,
    blocked_reasons=("归档记录", "GT 裁定", "样本库"),
)
_PEOPLE_FREE = RunPeopleDeletionPreview(
    run_found=True, run_created_at=None, run_status="completed",
    cluster_count=2, decision_count=2,
    person_ids=(uuid4(), uuid4()), people_names=("人员甲", "人员乙"),
    embedding_count=0, recognition_count=2, assignment_count=2,
    sample_count=0, archive_count=0, ground_truth_count=0,
)
_PHOTOS_BLOCKED = RunPhotosDeletionPreview(
    run_found=True, run_created_at=None, run_status="completed",
    photo_count=2, recognition_count=2, archive_count=1,
    observation_count=2, sample_count=3, member_count=2,
    other_run_snapshot_count=0, cluster_count=2, decision_count=2,
    ground_truth_count=1, blocked_reasons=("归档记录",),
)
_PHOTOS_FREE = RunPhotosDeletionPreview(
    run_found=True, run_created_at=None, run_status="completed",
    photo_count=2, recognition_count=2, archive_count=0,
    observation_count=2, sample_count=0, member_count=2,
    other_run_snapshot_count=1, cluster_count=2, decision_count=2,
    ground_truth_count=0,
)


class _StubPeopleService:
    """预览可编排的名单删除服务替身（对话框纯展示，不执行）。"""

    def __init__(self, preview: RunPeopleDeletionPreview) -> None:
        self._preview = preview

    def preview(self, _run_id):
        return self._preview


class _StubPhotosService:
    """预览可编排的照片删除服务替身（对话框纯展示，不执行）。"""

    def __init__(self, preview: RunPhotosDeletionPreview) -> None:
        self._preview = preview

    def preview(self, _run_id):
        return self._preview


_RECORD_BLOCKED = RunRecordDeletionPreview(
    run_found=True, run_created_at=None, run_status="completed",
    photo_count=2, generation_count=1, cluster_count=2, decision_count=2,
    ground_truth_count=0, observation_count=0, snapshot_count=2,
    blocked_reasons=("该运行仍有 2 张照片登记——请先使用「删除该运行照片…」"
                    "清理照片及其级联数据",),
)
_RECORD_FREE = RunRecordDeletionPreview(
    run_found=True, run_created_at=None, run_status="completed",
    photo_count=0, generation_count=1, cluster_count=2, decision_count=2,
    ground_truth_count=0, observation_count=0, snapshot_count=0,
)
_RECORD_GONE = RunRecordDeletionPreview(
    run_found=False, run_created_at=None, run_status="",
    photo_count=0, generation_count=0, cluster_count=0, decision_count=0,
    ground_truth_count=0, observation_count=0, snapshot_count=0,
)


class _StubRecordService:
    """预览/执行可编排的记录清理服务替身（对话框纯展示 + 执行断言）。"""

    def __init__(self, preview: RunRecordDeletionPreview) -> None:
        self._preview = preview
        self.executed_run_ids: list = []

    def preview(self, _run_id):
        return self._preview

    def execute(self, command):
        self.executed_run_ids.append(command.run_id)
        return RunRecordDeletionResult(
            run_removed=1, generations_purged=1, decision_cascade=2,
            observation_cascade=0, snapshot_cascade=0,
        )


def _ok_button(dialog) -> QPushButton:
    return dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)


# ── 名单对话框 ──────────────────────────────────────────────────────────


def test_people_dialog_blocks_execution_on_evidence(qtbot) -> None:
    """D5 硬阻断：阻断原因展示 + 知悉勾选与执行按钮禁用。"""
    dialog = RunPeopleDeletionDialog(
        _StubPeopleService(_PEOPLE_BLOCKED), "run-1", "2026-10-28 17:07 · 已完成",
    )
    qtbot.addWidget(dialog)
    assert _ok_button(dialog).isEnabled() is False
    assert dialog._aware_checkbox.isEnabled() is False
    assert "归档记录" in dialog._blocked_label.text()


def test_people_dialog_gates_ok_on_aware_checkbox(qtbot) -> None:
    """知悉勾选前确认按钮禁用；勾选后启用（A3 默认披露）。"""
    dialog = RunPeopleDeletionDialog(
        _StubPeopleService(_PEOPLE_FREE), "run-1", "2026-10-28 17:07 · 已完成",
    )
    qtbot.addWidget(dialog)
    assert _ok_button(dialog).isEnabled() is False
    dialog._aware_checkbox.setChecked(True)
    assert _ok_button(dialog).isEnabled() is True
    assert "人员甲" in dialog._impact_label.text()


def test_people_dialog_unassign_mode_switches_impact(qtbot) -> None:
    """A1 模式：展示解除匹配语义且不受硬阻断约束。"""
    dialog = RunPeopleDeletionDialog(
        _StubPeopleService(_PEOPLE_BLOCKED), "run-1", "2026-10-28 17:07 · 已完成",
    )
    qtbot.addWidget(dialog)
    dialog._unassign_mode.setChecked(True)
    assert "解除" in dialog._impact_label.text()
    # A1 不删除证据——阻断解除，可勾选知悉并执行
    assert dialog._aware_checkbox.isEnabled() is True
    assert dialog._blocked_label.isVisibleTo(dialog) is False


# ── 照片对话框 ──────────────────────────────────────────────────────────


def test_photos_dialog_blocks_execution_on_evidence(qtbot) -> None:
    """D5 硬阻断：归档记录非空 → 执行按钮与知悉勾选禁用。"""
    dialog = RunPhotosDeletionDialog(
        _StubPhotosService(_PHOTOS_BLOCKED), "run-1", "2026-10-28 17:07 · 已完成",
    )
    qtbot.addWidget(dialog)
    assert _ok_button(dialog).isEnabled() is False
    assert dialog._aware_checkbox.isEnabled() is False


def test_photos_dialog_purge_toggle_shows_warning(qtbot) -> None:
    """B2 勾选：先披露代际与决策行的级联删除，再允许执行。"""
    dialog = RunPhotosDeletionDialog(
        _StubPhotosService(_PHOTOS_FREE), "run-1", "2026-10-28 17:07 · 已完成",
    )
    qtbot.addWidget(dialog)
    assert dialog._purge_warning.isVisibleTo(dialog) is False
    dialog._aware_checkbox.setChecked(True)
    assert _ok_button(dialog).isEnabled() is True
    dialog._purge_checkbox.setChecked(True)
    assert dialog._purge_warning.isVisibleTo(dialog) is True
    assert "决策行" in dialog._purge_warning.text()
    assert "2" in dialog._purge_warning.text()  # 簇数/决策数进入披露文案


def test_photos_dialog_empty_snapshot_shows_explicit_empty_state(qtbot) -> None:
    """历史运行无快照：明确空态，执行按钮禁用（不静默 no-op）。"""
    empty = RunPhotosDeletionPreview(
        run_found=True, run_created_at=None, run_status="completed",
        photo_count=0, recognition_count=0, archive_count=0,
        observation_count=0, sample_count=0, member_count=0,
        other_run_snapshot_count=0, cluster_count=0, decision_count=0,
        ground_truth_count=0,
    )
    dialog = RunPhotosDeletionDialog(_StubPhotosService(empty), "run-1", "历史运行")
    qtbot.addWidget(dialog)
    assert "快照" in dialog._impact_label.text()
    assert _ok_button(dialog).isEnabled() is False


# ── 记录清理对话框（功能 C，追加轮 21）─────────────────────────────────


def test_record_dialog_blocks_execution_while_photos_registered(qtbot) -> None:
    """照片仍在登记 → 阻断原因展示 + 知悉勾选与执行按钮禁用。"""
    dialog = RunRecordDeletionDialog(
        _StubRecordService(_RECORD_BLOCKED), "run-1", "2026-10-28 17:07 · 已完成",
    )
    qtbot.addWidget(dialog)
    assert _ok_button(dialog).isEnabled() is False
    assert dialog._aware_checkbox.isEnabled() is False
    assert "删除该运行照片" in dialog._blocked_label.text()


def test_record_dialog_gates_ok_on_aware_checkbox(qtbot) -> None:
    """知悉勾选前确认按钮禁用；勾选后启用并披露残留代际/决策计数。"""
    service = _StubRecordService(_RECORD_FREE)
    dialog = RunRecordDeletionDialog(
        service, "run-1", "2026-10-28 17:07 · 已完成",
    )
    qtbot.addWidget(dialog)
    assert _ok_button(dialog).isEnabled() is False
    assert "残留聚类代际 1 个" in dialog._impact_label.text()
    assert "身份决策 2 条" in dialog._impact_label.text()

    dialog._aware_checkbox.setChecked(True)
    assert _ok_button(dialog).isEnabled() is True

    dialog._on_confirm()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert service.executed_run_ids == ["run-1"]
    assert "残留代际 1 个" in dialog.last_message()
    assert "决策 2 条级联清除" in dialog.last_message()


def test_record_dialog_unknown_run_shows_empty_state(qtbot) -> None:
    """运行不存在（已被删除）→ 空态文案 + 执行按钮禁用。"""
    dialog = RunRecordDeletionDialog(
        _StubRecordService(_RECORD_GONE), "run-1", "2026-10-28 17:07 · 已完成",
    )
    qtbot.addWidget(dialog)
    assert "没有任何可删除的对象" in dialog._impact_label.text()
    assert _ok_button(dialog).isEnabled() is False


# ── 名册页入口 + D10 标签 ───────────────────────────────────────────────


def _page(tmp_path: Path):
    repositories = build_sqlite_repositories(tmp_path / "run_delete_page.db")
    delete_person = DeletePersonService(
        repositories.people, repositories.photos, repositories.recognition,
        repositories.face_embeddings,
        assignment_repository=repositories.cluster_assignments,
        sample_repository=repositories.person_face_samples,
    )
    delete_run_people = DeleteRunPeopleService(
        repositories.recognition_runs, repositories.face_clusters,
        repositories.cluster_assignments, repositories.people, delete_person,
        repositories.archive_records, repositories.calibration_annotations,
    )
    delete_run_photos = DeleteRunPhotosService(
        repositories.recognition_runs, repositories.photos, repositories.recognition,
        repositories.archive_records, repositories.face_observations,
        repositories.person_face_samples, repositories.face_clusters,
        repositories.cluster_assignments, repositories.calibration_annotations,
    )
    delete_run_record = DeleteRunRecordService(
        repositories.recognition_runs, repositories.face_observations,
        repositories.face_clusters, repositories.cluster_assignments,
        repositories.calibration_annotations,
    )
    page = PeopleAdminPage(
        ManagePeopleService(repositories.people, repositories.import_batches),
        ListPersonsService(repositories.people),
        delete_person,
        ListRecognitionRunsService(repositories.recognition_runs),
        ClusterResultsService(
            repositories.recognition_runs,
            repositories.face_observations,
            repositories.face_clusters,
        ),
        RosterClusterStatsService(
            repositories.face_clusters,
            repositories.face_observations,
            repositories.cluster_assignments,
        ),
        delete_run_people=delete_run_people,
        delete_run_photos=delete_run_photos,
        delete_run_record=delete_run_record,
    )
    return page, repositories


def test_page_run_delete_buttons_disabled_without_runs(qtbot, tmp_path) -> None:
    """无运行时两个删除入口禁用（不静默无响应）。"""
    page, _repos = _page(tmp_path)
    qtbot.addWidget(page)
    assert page._delete_run_people_button.isEnabled() is False
    assert page._delete_run_photos_button.isEnabled() is False
    assert page._delete_run_record_button.isEnabled() is False


def test_page_batch_label_carries_time_and_status(qtbot, tmp_path) -> None:
    """D10：来源批次标签 = 文件名 · 创建时间 · 状态（同名批次可区分）。"""
    page, repositories = _page(tmp_path)
    qtbot.addWidget(page)
    repositories.import_batches.add_batch(ImportBatch(
        file_name="名单_test.txt", file_hash="h", source_type="txt",
        status="confirmed", created_at=datetime(2026, 10, 28, 9, 30),
    ))
    page.refresh()
    labels = [
        page._batch_combo.itemText(index)
        for index in range(page._batch_combo.count())
    ]
    matching = [label for label in labels if "名单_test.txt" in label]
    assert matching, labels
    assert matching[0].startswith("名单_test.txt · 2026-10-28 09:30 · 已确认")


def test_import_batch_entry_label_disambiguates_same_names() -> None:
    """同名批次因时间/状态差异可区分（D10 的动机用例）。"""
    first = text.import_batch_entry_label(
        "名单_test.txt", datetime(2026, 10, 28, 9, 30), "confirmed", 36,
    )
    second = text.import_batch_entry_label(
        "名单_test.txt", datetime(2026, 10, 28, 10, 0), "draft", 0,
    )
    assert first != second
    assert "草稿" in second
    assert "（36 人）" in first
