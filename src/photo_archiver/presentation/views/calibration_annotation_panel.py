"""Ground Truth 标注面板（S4-B-1 Checkpoint 7）。

嵌入 :class:`ClusterResultsDialog` 的独立标注区域。**与业务 Assignment 严格
分离**：本面板只经 :class:`CalibrationAnnotationService` 写入
``calibration_annotations``，结构上无法触达 Assignment / Review / Archive /
Recognition——构造函数**不注入**任何业务仓储或服务。

Confirmation bias 防护（CP7.3，硬要求）：

* **不显示**任何机器信号：assignment score、cosine、det_score、quality_score、
  top-1/top-2、margin、machine-confirmed/suggested、RecognitionResult、
  Assignment status、Archive status。
* Person 下拉**严格按 roster_order ASC**（由调用方经 ``persons_provider``
  提供已排序列表；SQLite 仓储的 ``list_all`` 契约即此排序）。搜索框只过滤
  显示项，**不改变排序语义**。
* 盲标注（CP7.10/7.11）：标注者只能经 ``find_latest_own_annotation`` 看到自己
  的最新标注；**不调用** ``list_annotations``（那是审计/仲裁视图）。

三态联动（CP7.6-7.8）：

* ``person`` → Person 选择器启用、Difficulty 禁用；Person 必选才能提交。
* ``out_of_roster`` → 两者都禁用/清空。
* ``undecidable`` → Difficulty 启用（词表**直接读取 Domain 定义**，UI 不复制）、
  Person 禁用；reason 必选才能提交。
"""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.services.calibration_annotation_service import (
    CalibrationAnnotationService,
)
from photo_archiver.domain.entities.calibration_annotation import (
    DIFFICULTY_OCCLUSION,
    DIFFICULTY_PROFILE,
    DIFFICULTY_TOO_SMALL,
    DIFFICULTY_BLUR,
    DIFFICULTY_LIGHTING,
    DIFFICULTY_COMPRESSION,
    DIFFICULTY_OTHER,
    VERDICT_OUT_OF_ROSTER,
    VERDICT_PERSON,
    VERDICT_UNDECIDABLE,
)
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import ROLE_PRIMARY, assign_role


class CalibrationAnnotationPanel(QWidget):
    """Ground Truth annotation form for one FaceCluster.

    Embeds into :class:`ClusterResultsDialog`. All writes go through
    :class:`CalibrationAnnotationService`; the panel holds **no** repository
    reference and **no** business service reference.
    """

    def __init__(
        self,
        calibration_service: CalibrationAnnotationService,
        annotator_id: str,
        persons_provider,
        parent: QWidget | None = None,
    ) -> None:
        """Build the annotation form.

        Args:
            calibration_service: The only write path (CP7.13).
            annotator_id: Explicit annotator identity injected by the caller
                (CP7.9) — never guessed, never defaulted.
            persons_provider: Zero-arg callable returning
                ``list[(person_id, display_name)]`` **already sorted by
                roster_order ASC** (CP7.4). Re-invoked on every cluster switch
                so the roster stays current.
            parent: Qt parent.
        """
        super().__init__(parent)
        self._calibration_service = calibration_service
        self._annotator_id = annotator_id
        self._persons_provider = persons_provider
        self._cluster_id: UUID | None = None
        self._persons: list[tuple[UUID, str]] = []
        self._build_ui()
        self._reload_persons()

    # ── UI 构建 ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QLabel(text.CALIBRATION_PANEL_TITLE, self)
        layout.addWidget(header)

        # 三态 radio（互斥）
        verdict_row = QHBoxLayout()
        self._verdict_group = QButtonGroup(self)
        self._person_radio = QRadioButton(text.CALIBRATION_VERDICT_PERSON, self)
        self._out_of_roster_radio = QRadioButton(
            text.CALIBRATION_VERDICT_OUT_OF_ROSTER, self
        )
        self._undecidable_radio = QRadioButton(
            text.CALIBRATION_VERDICT_UNDECIDABLE, self
        )
        for radio in (self._person_radio, self._out_of_roster_radio,
                      self._undecidable_radio):
            self._verdict_group.addButton(radio)
            verdict_row.addWidget(radio)
        verdict_row.addStretch()
        layout.addLayout(verdict_row)

        # Person 选择器（roster_order ASC；搜索框只过滤不改序）
        person_row = QHBoxLayout()
        person_row.addWidget(QLabel(text.CALIBRATION_PERSON_LABEL, self))
        self._person_search = QLineEdit(self)
        self._person_search.setPlaceholderText(text.CALIBRATION_PERSON_SEARCH)
        self._person_search.textChanged.connect(self._filter_persons)
        person_row.addWidget(self._person_search, 1)
        self._person_combo = QComboBox(self)
        person_row.addWidget(self._person_combo, 2)
        layout.addLayout(person_row)

        # Difficulty 选择器（词表直接读 Domain 常量）
        difficulty_row = QHBoxLayout()
        difficulty_row.addWidget(QLabel(text.CALIBRATION_DIFFICULTY_LABEL, self))
        self._difficulty_combo = QComboBox(self)
        for reason in (DIFFICULTY_OCCLUSION, DIFFICULTY_PROFILE,
                       DIFFICULTY_TOO_SMALL, DIFFICULTY_BLUR,
                       DIFFICULTY_LIGHTING, DIFFICULTY_COMPRESSION,
                       DIFFICULTY_OTHER):
            self._difficulty_combo.addItem(text.calibration_difficulty_label(reason),
                                           reason)
        difficulty_row.addWidget(self._difficulty_combo, 1)
        layout.addLayout(difficulty_row)

        # 提交按钮
        submit_row = QHBoxLayout()
        self._submit_button = QPushButton(text.CALIBRATION_SUBMIT, self)
        assign_role(self._submit_button, ROLE_PRIMARY)
        self._submit_button.clicked.connect(self._on_submit)
        submit_row.addWidget(self._submit_button)
        submit_row.addStretch()
        layout.addLayout(submit_row)

        # 状态（只显示自己的最新标注）
        self._status_label = QLabel(self)
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # 三态联动
        self._verdict_group.buttonToggled.connect(self._on_verdict_toggled)
        self._set_verdict_ui()

    # ── 三态联动（CP7.6-7.8） ─────────────────────────────────────────

    def _selected_verdict(self) -> str | None:
        if self._person_radio.isChecked():
            return VERDICT_PERSON
        if self._out_of_roster_radio.isChecked():
            return VERDICT_OUT_OF_ROSTER
        if self._undecidable_radio.isChecked():
            return VERDICT_UNDECIDABLE
        return None

    def _on_verdict_toggled(self) -> None:
        self._set_verdict_ui()

    def _set_verdict_ui(self) -> None:
        verdict = self._selected_verdict()
        self._person_combo.setEnabled(verdict == VERDICT_PERSON)
        self._person_search.setEnabled(verdict == VERDICT_PERSON)
        self._difficulty_combo.setEnabled(verdict == VERDICT_UNDECIDABLE)
        if verdict != VERDICT_PERSON:
            self._person_combo.setCurrentIndex(-1)
        if verdict != VERDICT_UNDECIDABLE:
            self._difficulty_combo.setCurrentIndex(-1)

    def _filter_persons(self, search_text: str) -> None:
        """Filter the person combo in place — **does not change sort order**.

        CP7.5：搜索只负责过滤显示项；重填时保持 roster_order ASC（构建序即
        排序序，QComboBox 不重排）。
        """
        needle = search_text.strip().lower()
        self._person_combo.blockSignals(True)
        for index in range(self._person_combo.count()):
            item_text = self._person_combo.itemText(index)
            visible = not needle or needle in item_text.lower()
            self._person_combo.setItemData(
                index, not visible, Qt.ItemDataRole.UserRole - 1
            )
            # setItemHidden 走 view 层；此处用 setItemData + view 不可行，
            # 直接改用 QComboBox 的过滤代理——最简方式是重建匹配项。
        self._person_combo.blockSignals(False)
        # 简化：重建匹配项保持排序
        current = self._person_combo.currentData()
        self._person_combo.clear()
        for person_id, display_name in self._filtered_persons(needle):
            self._person_combo.addItem(display_name, person_id)
        if current is not None:
            for index in range(self._person_combo.count()):
                if self._person_combo.itemData(index) == current:
                    self._person_combo.setCurrentIndex(index)
                    break

    def _filtered_persons(self, needle: str):
        for person_id, display_name in self._persons:
            if not needle or needle in display_name.lower():
                yield person_id, display_name

    # ── Cluster 切换（CP7.15） ────────────────────────────────────────

    def set_cluster(self, cluster_id: UUID | None) -> None:
        """Switch to a new cluster; reset all form state and reload own view.

        不得残留上一个 Cluster 的选择（CP7.15）：verdict 清空、person/difficulty
        重置、状态标签重载当前标注者的 own latest。
        """
        self._cluster_id = cluster_id
        self._verdict_group.setExclusive(False)
        for radio in (self._person_radio, self._out_of_roster_radio,
                      self._undecidable_radio):
            radio.setChecked(False)
        self._verdict_group.setExclusive(True)
        self._person_search.clear()
        self._reload_persons()
        self._set_verdict_ui()
        self._reload_own_annotation()

    def _reload_persons(self) -> None:
        """Rebuild the person combo from the provider (roster_order ASC)."""
        self._persons = list(self._persons_provider())
        self._person_combo.clear()
        for person_id, display_name in self._persons:
            self._person_combo.addItem(display_name, person_id)

    def _reload_own_annotation(self) -> None:
        """Blind view：只读自己最新标注（CP7.10），不触碰 list_annotations。"""
        if self._cluster_id is None:
            self._status_label.setText(text.CALIBRATION_STATUS_NO_CLUSTER)
            return
        own = self._calibration_service.latest_own_annotation(
            self._cluster_id, self._annotator_id
        )
        if own is None:
            self._status_label.setText(text.CALIBRATION_STATUS_UNLABELED)
        else:
            self._status_label.setText(
                text.CALIBRATION_STATUS_OWN_LATEST.format(
                    verdict=text.calibration_verdict_label(own.verdict),
                    person=own.person_id if own.person_id is not None else "—",
                    time=own.created_at.strftime("%Y-%m-%d %H:%M")
                    if own.created_at is not None else "—",
                )
            )

    # ── 提交（CP7.16） ────────────────────────────────────────────────

    def _on_submit(self) -> None:
        """Validate and submit one annotation via the calibration service."""
        if self._cluster_id is None:
            self._show_error(text.CALIBRATION_ERROR_NO_CLUSTER)
            return
        verdict = self._selected_verdict()
        if verdict is None:
            self._show_error(text.CALIBRATION_ERROR_NO_VERDICT)
            return
        person_id: UUID | None = None
        difficulty_reason: str | None = None
        if verdict == VERDICT_PERSON:
            person_id = self._person_combo.currentData()
            if person_id is None:
                self._show_error(text.CALIBRATION_ERROR_NO_PERSON)
                return
        if verdict == VERDICT_UNDECIDABLE:
            difficulty_reason = self._difficulty_combo.currentData()
            if difficulty_reason is None:
                self._show_error(text.CALIBRATION_ERROR_NO_DIFFICULTY)
                return
        self._calibration_service.annotate(
            cluster_id=self._cluster_id,
            annotator_id=self._annotator_id,
            verdict=verdict,
            person_id=person_id,
            difficulty_reason=difficulty_reason,
        )
        self._reload_own_annotation()

    def _show_error(self, message: str) -> None:
        self._status_label.setText(message)