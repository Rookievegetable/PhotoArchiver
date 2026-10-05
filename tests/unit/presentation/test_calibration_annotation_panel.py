"""S4-B-1 / Checkpoint 7 — Ground Truth 标注 UI 验收测试。

覆盖 CP7 的核心要求：三态联动、blind view、confirmation-bias 防护、
cluster 切换不残留、submit payload、business isolation。

使用真实 CalibrationAnnotationService + in-memory 仓储，qtbot 驱动 UI。
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from PySide6.QtWidgets import QWidget

from photo_archiver.application.services.calibration_annotation_service import (
    CalibrationAnnotationService,
)
from photo_archiver.domain.entities.calibration_annotation import (
    VERDICT_OUT_OF_ROSTER,
    VERDICT_PERSON,
    VERDICT_UNDECIDABLE,
)
from photo_archiver.infrastructure.repositories.in_memory_calibration_annotation_repository import (
    InMemoryCalibrationAnnotationRepository,
)
from photo_archiver.presentation.views.calibration_annotation_panel import (
    CalibrationAnnotationPanel,
)


def _persons() -> list[tuple[UUID, str]]:
    """Persons in roster_order ASC（模拟 ListPersonsService 的仓储排序）。"""
    return [
        (uuid4(), "张三"),
        (uuid4(), "李四"),
        (uuid4(), "王五"),
    ]


@pytest.fixture
def service() -> CalibrationAnnotationService:
    return CalibrationAnnotationService(InMemoryCalibrationAnnotationRepository())


@pytest.fixture
def persons() -> list[tuple[UUID, str]]:
    return _persons()


@pytest.fixture
def persons_provider(persons):
    """Zero-arg callable returning roster-ordered persons (CP7.4 契约)."""
    return lambda: persons


@pytest.fixture
def annotator_id() -> str:
    return "annotator-test"


@pytest.fixture
def panel(qtbot, service, persons_provider, annotator_id) -> CalibrationAnnotationPanel:
    widget = CalibrationAnnotationPanel(
        calibration_service=service,
        annotator_id=annotator_id,
        persons_provider=persons_provider,
    )
    qtbot.addWidget(widget)
    return widget


def _set_verdict(panel: CalibrationAnnotationPanel, verdict: str) -> None:
    radio_map = {
        VERDICT_PERSON: panel._person_radio,
        VERDICT_OUT_OF_ROSTER: panel._out_of_roster_radio,
        VERDICT_UNDECIDABLE: panel._undecidable_radio,
    }
    radio_map[verdict].setChecked(True)


def _select_person(panel: CalibrationAnnotationPanel, person_id: UUID) -> None:
    for index in range(panel._person_combo.count()):
        if panel._person_combo.itemData(index) == person_id:
            panel._person_combo.setCurrentIndex(index)
            return


# ── UI 状态（CP7.6-7.8） ──────────────────────────────────────────────────


def test_default_state_no_verdict_selected(panel) -> None:
    """验收 1：默认未选 verdict。"""
    assert panel._selected_verdict() is None
    assert not panel._person_radio.isChecked()
    assert not panel._out_of_roster_radio.isChecked()
    assert not panel._undecidable_radio.isChecked()


def test_person_enables_person_selector_disables_difficulty(panel) -> None:
    """验收 2：person → Person selector enabled / Difficulty disabled。"""
    _set_verdict(panel, VERDICT_PERSON)
    assert panel._person_combo.isEnabled()
    assert not panel._difficulty_combo.isEnabled()


def test_out_of_roster_disables_both(panel) -> None:
    """验收 3：out_of_roster → Person 和 Difficulty 都禁用。"""
    _set_verdict(panel, VERDICT_OUT_OF_ROSTER)
    assert not panel._person_combo.isEnabled()
    assert not panel._difficulty_combo.isEnabled()


def test_undecidable_enables_difficulty_disables_person(panel) -> None:
    """验收 4：undecidable → Difficulty enabled / Person disabled。"""
    _set_verdict(panel, VERDICT_UNDECIDABLE)
    assert not panel._person_combo.isEnabled()
    assert panel._difficulty_combo.isEnabled()


def test_person_without_selection_cannot_submit(panel, service) -> None:
    """验收 5：person 未选人不能提交。"""
    cluster_id = uuid4()
    panel.set_cluster(cluster_id)
    _set_verdict(panel, VERDICT_PERSON)
    panel._on_submit()
    assert service.latest_own_annotation(cluster_id, "annotator-test") is None


def test_undecidable_without_reason_cannot_submit(panel, service) -> None:
    """验收 6：undecidable 未选 reason 不能提交。"""
    cluster_id = uuid4()
    panel.set_cluster(cluster_id)
    _set_verdict(panel, VERDICT_UNDECIDABLE)
    panel._on_submit()
    assert service.latest_own_annotation(cluster_id, "annotator-test") is None


# ── Blind view（CP7.10-7.11） ─────────────────────────────────────────────


def test_annotator_sees_own_latest(panel, service) -> None:
    """验收 7：当前标注者能看到自己的 latest。"""
    cluster_id = uuid4()
    person = _persons()[0][0]
    service.annotate(cluster_id, "annotator-test", VERDICT_PERSON, person_id=person)

    panel.set_cluster(cluster_id)
    assert "我的最新标注" in panel._status_label.text()


def test_annotator_cannot_see_other_annotator_result(panel, service) -> None:
    """验收 8/12：另一标注者已标注时，UI 不显示其 verdict/person。"""
    cluster_id = uuid4()
    other_person = _persons()[1][0]
    service.annotate(cluster_id, "annotator-OTHER", VERDICT_PERSON,
                     person_id=other_person)

    panel.set_cluster(cluster_id)
    status_text = panel._status_label.text()
    assert "未标注" in status_text, "当前标注者应看到'未标注'"
    assert "张三" not in status_text and "李四" not in status_text


def test_panel_does_not_call_list_annotations(panel, service, monkeypatch) -> None:
    """验收 9：blind view 不通过 list_annotations 实现。"""
    calls = []
    original = service.store.list_annotations
    monkeypatch.setattr(
        service.store, "list_annotations",
        lambda *a, **kw: calls.append(1) or original(*a, **kw),
    )
    panel.set_cluster(uuid4())
    panel._reload_own_annotation()
    assert calls == [], "blind view 不得调用 list_annotations"


def test_other_annotator_verdict_not_leaked(panel, service) -> None:
    """验收 10 补充：另一标注者的 verdict 不得出现在状态标签中。"""
    cluster_id = uuid4()
    service.annotate(cluster_id, "annotator-OTHER", VERDICT_OUT_OF_ROSTER)
    panel.set_cluster(cluster_id)
    assert VERDICT_OUT_OF_ROSTER not in panel._status_label.text()
    assert VERDICT_PERSON not in panel._status_label.text()


# ── Submit payload（CP7.16） ─────────────────────────────────────────────


def test_person_submit_payload(panel, service, persons) -> None:
    """验收 11：person 写入正确 payload。"""
    cluster_id = uuid4()
    panel.set_cluster(cluster_id)
    person_id = persons[0][0]
    _set_verdict(panel, VERDICT_PERSON)
    _select_person(panel, person_id)
    panel._on_submit()

    stored = service.latest_own_annotation(cluster_id, "annotator-test")
    assert stored is not None
    assert stored.verdict == VERDICT_PERSON
    assert stored.person_id == person_id
    assert stored.difficulty_reason is None
    assert stored.annotator_id == "annotator-test"


def test_out_of_roster_submit_payload(panel, service) -> None:
    """验收 12：out_of_roster payload 正确。"""
    cluster_id = uuid4()
    panel.set_cluster(cluster_id)
    _set_verdict(panel, VERDICT_OUT_OF_ROSTER)
    panel._on_submit()

    stored = service.latest_own_annotation(cluster_id, "annotator-test")
    assert stored is not None
    assert stored.verdict == VERDICT_OUT_OF_ROSTER
    assert stored.person_id is None
    assert stored.difficulty_reason is None


def test_undecidable_submit_payload_with_reason(panel, service) -> None:
    """验收 13：undecidable payload + difficulty_reason 正确。"""
    cluster_id = uuid4()
    panel.set_cluster(cluster_id)
    _set_verdict(panel, VERDICT_UNDECIDABLE)
    panel._difficulty_combo.setCurrentIndex(0)  # occlusion
    panel._on_submit()

    stored = service.latest_own_annotation(cluster_id, "annotator-test")
    assert stored is not None
    assert stored.verdict == VERDICT_UNDECIDABLE
    assert stored.person_id is None
    assert stored.difficulty_reason is not None


def test_resubmit_creates_new_annotation(panel, service, persons) -> None:
    """验收 14：重新提交产生新 annotation（append-only）。"""
    cluster_id = uuid4()
    panel.set_cluster(cluster_id)
    person_id = persons[0][0]
    _set_verdict(panel, VERDICT_PERSON)
    _select_person(panel, person_id)
    panel._on_submit()
    first = service.latest_own_annotation(cluster_id, "annotator-test")

    panel._on_submit()
    second = service.latest_own_annotation(cluster_id, "annotator-test")
    assert second is not None
    assert first.id != second.id, "重新标注必须是新行"
    assert len(service.store.list_annotations(cluster_id)) == 2


def test_resubmit_does_not_modify_old_annotation(panel, service, persons) -> None:
    """验收 15：重新提交不修改旧 annotation。"""
    cluster_id = uuid4()
    panel.set_cluster(cluster_id)
    person_id = persons[0][0]
    _set_verdict(panel, VERDICT_PERSON)
    _select_person(panel, person_id)
    panel._on_submit()
    first = service.latest_own_annotation(cluster_id, "annotator-test")

    panel._on_submit()
    all_rows = service.store.list_annotations(cluster_id)
    assert all_rows[0].created_at == first.created_at, "旧 annotation 不变"
    assert all_rows[0].verdict == VERDICT_PERSON


# ── Cluster 切换（CP7.15） ───────────────────────────────────────────────


def test_cluster_switch_does_not_residual_person(panel, persons) -> None:
    """验收 16：A → B 切换不残留 Person 选择。"""
    cluster_a = uuid4()
    cluster_b = uuid4()
    panel.set_cluster(cluster_a)
    _set_verdict(panel, VERDICT_PERSON)
    _select_person(panel, persons[0][0])

    panel.set_cluster(cluster_b)
    assert panel._person_combo.currentData() is None, "切换后不残留 Person"
    assert panel._selected_verdict() is None


def test_cluster_switch_loads_correct_annotation(panel, service) -> None:
    """验收 17：切换后加载正确 cluster 的标注。"""
    cluster_a = uuid4()
    cluster_b = uuid4()
    person_a = _persons()[0][0]
    service.annotate(cluster_a, "annotator-test", VERDICT_PERSON, person_id=person_a)

    panel.set_cluster(cluster_a)
    assert "我的最新标注" in panel._status_label.text()

    panel.set_cluster(cluster_b)
    assert "未标注" in panel._status_label.text()


def test_cluster_switch_refreshes_status(panel, service) -> None:
    """验收 18：状态正确刷新。"""
    cluster_a = uuid4()
    panel.set_cluster(cluster_a)
    assert "未标注" in panel._status_label.text()

    person_id = _persons()[0][0]
    service.annotate(cluster_a, "annotator-test", VERDICT_PERSON, person_id=person_id)
    panel.set_cluster(cluster_a)
    assert "我的最新标注" in panel._status_label.text()


# ── Person 排序（CP7.4） ─────────────────────────────────────────────────


def test_person_combo_is_roster_order(panel, persons) -> None:
    """验收 9：Person 下拉按 roster_order ASC（即 provider 提供的顺序）。"""
    combo_order = [
        panel._person_combo.itemData(i) for i in range(panel._person_combo.count())
    ]
    assert combo_order == [p[0] for p in persons]


def test_person_search_filters_without_reordering(panel, persons) -> None:
    """CP7.5：搜索只过滤显示项，不改变排序语义。"""
    panel._person_search.setText("张")
    combo_order = [
        panel._person_combo.itemData(i) for i in range(panel._person_combo.count())
    ]
    expected = [pid for pid, name in persons if "张" in name]
    assert combo_order == expected
    panel._person_search.setText("")
    assert panel._person_combo.count() == len(persons)


# ── Business isolation（真实 in-memory 仓储，非 mock） ────────────────────


def test_calibration_panel_does_not_create_business_assignment(service, persons) -> None:
    """验收 17：标注后 cluster_person_assignments 零变化。"""

    cluster_id = uuid4()
    person_id = persons[0][0]
    panel = CalibrationAnnotationPanel(
        calibration_service=service,
        annotator_id="annotator-test",
        persons_provider=lambda: persons,
    )
    panel.set_cluster(cluster_id)
    _set_verdict(panel, VERDICT_PERSON)
    _select_person(panel, person_id)
    panel._on_submit()

    assert hasattr(service.store, "add_annotation"), (
        "service.store 必须是 calibration 仓储"
    )
    assert not hasattr(service.store, "add_assignments"), (
        "calibration store 不得暴露业务方法"
    )
    assert service.latest_own_annotation(cluster_id, "annotator-test") is not None


def test_no_machine_signal_in_panel_widgets(panel) -> None:
    """CP7.3：面板 widget 树中不存在机器信号相关文本。"""
    forbidden = {"score", "top-1", "top-2", "margin", "confidence",
                 "det_score", "quality_score", "assignment"}
    widgets = panel.findChildren(QWidget)
    for widget in widgets:
        for attr in ("toolTip", "statusTip", "whatsThis"):
            value = getattr(widget, attr, lambda: "")()
            if value:
                lowered = value.lower()
                for signal in forbidden:
                    assert signal.lower() not in lowered, (
                        f"面板泄露机器信号 {signal!r} 于 {attr}: {value!r}"
                    )
    status_text = panel._status_label.text().lower()
    for signal in forbidden:
        assert signal not in status_text, f"状态标签泄露 {signal!r}"