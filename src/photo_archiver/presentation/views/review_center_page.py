"""Review center page — the persistent review surface (2026-10-01 页面化).

Formerly the modal ``ReviewDialog`` (Step 13 fix + Batch 5); the owner ruled
the review center should be a fixed navigation page instead of a dialog. The
page holds NO business logic and the review semantics are unchanged:

- load via the injected ``ReviewController`` (list_pending / bulk_approve /
  bulk_reject, synchronous <10ms SQLite per Step 12 裁决 A);
- after each transition the list re-fetches so the queue visibly shrinks;
  an emptied queue stays open and inspectable (Batch 2);
- the D-1 identity selector stays: approving without an identity yields a
  row the archive planner cannot select, so the user is asked explicitly;
- rows render through the shared async thumbnail channel — the page itself
  never touches disk.

Differences from the dialog era (页化带来的行为差异，业务语义零变化):

- no Close button — a page does not close; the queue refreshes when the
  navigation enters the page and after each task completes;
- action buttons disable while a task is busy (:meth:`set_busy`), mirroring
  the window-level admission rules;
- :attr:`review_changed` fires after every mutation so the MainWindow
  refreshes the photo wall immediately (the modal did that only on close);
- a guidance banner separates the two identity-establishing paths: the
  cold-start pairing workbench (ordered_suggestion → 人工确认) vs. this
  page's D-1 manual approval — 业务规则（K-3/D-1）不做任何自动化。

Layout:
    [引导条：冷启动配对 vs 本页个别处理]        [前往人物配对工作台]
    [待审核 N 条。…]
    QListWidget rows: "照片={file}　人员={name}" / "置信度：较高（0.87）· 状态：待审核"
    [批准时指定人员 ▾] 提示行
    [通过所选（n）] [拒绝所选（n）] [全部通过（N）]
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.domain import RecognitionResult
from photo_archiver.presentation.controllers.review_controller import ReviewController
from photo_archiver.presentation.combo_search import NameSearchComboBinder
from photo_archiver.domain.exceptions import (
    ConcurrentDecisionConflictError,
    ManualDecisionProtectedError,
    PhotoNotClusteredError,
    ReviewAnchorAmbiguousError,
    ValidationError,
)
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import mark_searchable_combo
from photo_archiver.presentation.ui_text import (
    REVIEW_APPROVE_ALL,
    REVIEW_APPROVE_ALL_CONFIRM,
    REVIEW_APPROVE_ALL_CONFIRM_TITLE,
    REVIEW_APPROVE_ALL_COUNTED,
    REVIEW_APPROVE_SELECTED,
    REVIEW_APPROVE_SELECTED_COUNTED,
    REVIEW_CONFIDENCE_FORMAT,
    REVIEW_CONFIDENCE_HIGH,
    REVIEW_CONFIDENCE_LOW,
    REVIEW_CONFIDENCE_MEDIUM,
    REVIEW_CONFIDENCE_NO_EVIDENCE,
    REVIEW_CONFIDENCE_VERY_HIGH,
    REVIEW_EMPTY,
    REVIEW_GUIDANCE_PAIRING_BUTTON,
    REVIEW_GUIDANCE_TEXT,
    REVIEW_IDENTITY_HINT,
    REVIEW_IDENTITY_LABEL,
    REVIEW_NO_IDENTITY_WARNING,
    REVIEW_REJECT_SELECTED,
    REVIEW_REJECT_SELECTED_COUNTED,
    REVIEW_ROW_DETAIL_FORMAT,
    REVIEW_ROW_FORMAT,
    REVIEW_STATUS_LINE,
    STATUS_BADGE_PENDING,
)
from photo_archiver.presentation.views.review_preview_dialog import ReviewPreviewDialog

# 行上的附加数据角色：UserRole = 结果 id（批量动作），UserRole+1 = 结果对象
# （双击 → controller.photo_for → 高清预览）。
RESULT_DATA_ROLE = Qt.UserRole + 1  # type: ignore[attr-defined]

if TYPE_CHECKING:
    from photo_archiver.presentation.controllers.photo_list_controller import (
        PhotoListController,
    )

# Confidence bands for the textual reading (exact value stays on the row for
# audit — these thresholds only pick the wording, never gate any decision).
_CONFIDENCE_VERY_HIGH_FLOOR = 0.90
_CONFIDENCE_HIGH_FLOOR = 0.75
_CONFIDENCE_MEDIUM_FLOOR = 0.60


def confidence_band(confidence: float | None) -> str:
    """Return the textual band for a match confidence (Batch 5 wording only).

    Stage 4 BLK-5: ``None`` means "no similarity evidence" (positional pairing
    or manual assignment) and is stated as such — it must never be rendered as
    a numeric ``0.00``, which would claim a measured similarity of zero.
    """
    if confidence is None:
        return REVIEW_CONFIDENCE_NO_EVIDENCE
    if confidence >= _CONFIDENCE_VERY_HIGH_FLOOR:
        return REVIEW_CONFIDENCE_VERY_HIGH
    if confidence >= _CONFIDENCE_HIGH_FLOOR:
        return REVIEW_CONFIDENCE_HIGH
    if confidence >= _CONFIDENCE_MEDIUM_FLOOR:
        return REVIEW_CONFIDENCE_MEDIUM
    return REVIEW_CONFIDENCE_LOW


class ReviewCenterPage(QWidget):
    """常驻审核中心页：待审核识别结果队列 + D-1 身份选择器 + 批量动作。"""

    # 任一通过/拒绝成功后发射——主窗口据此立即刷新照片墙（原模态关闭后刷新）。
    review_changed = Signal()
    # 引导条按钮 → 主窗口切换到「人员与分组」页（聚类 / 配对工作台所在处）。
    pairing_requested = Signal()

    def __init__(
        self,
        controller: ReviewController,
        parent: QWidget | None = None,
        thumbnail_source: PhotoListController | None = None,
    ) -> None:
        """Build the page and load the pending queue.

        Args:
            controller: Bridge to the Application-layer ReviewRecognitionService.
            parent: Optional Qt parent for ownership / cleanup.
            thumbnail_source: Optional PhotoListController-like object providing
                ``load_thumbnail(photo_id, source_path)`` and a
                ``thumbnail_loaded(object, object)`` signal — the existing
                async, off-UI-thread thumbnail channel. The page only renders
                what arrives; it never reads the disk itself.
        """
        super().__init__(parent)
        self._controller = controller
        self._thumbnail_source = thumbnail_source
        self._items_by_photo_id: dict[UUID, list[QListWidgetItem]] = {}
        self._busy = False
        self._build_ui()
        if thumbnail_source is not None:
            # Connect once — _request_row_thumbnail may register many rows and
            # a per-row connect would multiply every arriving signal.
            thumbnail_source.thumbnail_loaded.connect(self._attach_thumbnail)
        self._refresh_list()

    def _build_ui(self) -> None:
        """Lay out the guidance banner, queue and action buttons."""

        # 2026-10-01 引导条（WS1）：两条身份建立路径的分工——冷启动配对链
        # （ordered_suggestion → 人工确认）在本页之外；本页只做 D-1 个别处理。
        # 只做引导，不做任何自动化身份归属（K-3/D-1 冻结语义不变）。
        guidance = QLabel(REVIEW_GUIDANCE_TEXT, self)
        guidance.setWordWrap(True)
        self._pairing_button = QPushButton(REVIEW_GUIDANCE_PAIRING_BUTTON, self)
        self._pairing_button.clicked.connect(self.pairing_requested.emit)
        guidance_row = QHBoxLayout()
        guidance_row.addWidget(guidance, 1)
        guidance_row.addWidget(self._pairing_button)

        self._status = QLabel(self)
        self._status.setWordWrap(True)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.setWordWrap(True)

        self._approve_selected = QPushButton(REVIEW_APPROVE_SELECTED, self)
        self._approve_selected.clicked.connect(self._on_approve_selected)
        self._reject_selected = QPushButton(REVIEW_REJECT_SELECTED, self)
        self._reject_selected.clicked.connect(self._on_reject_selected)
        self._approve_all = QPushButton(REVIEW_APPROVE_ALL, self)
        self._approve_all.clicked.connect(self._on_approve_all)

        # Stage 4 D-1：新识别链路的兼容行 person_id 恒 NULL，仅靠「通过」不会
        # 写入身份，批准结果永远进不了归档。这里给审核人一个显式身份选择器，
        # 让"人工最终结果"能真正落到 person_id 上。
        self._identity_combo = QComboBox(self)
        self._identity_combo.addItem(text.REVIEW_IDENTITY_UNRESOLVED, None)
        for person_id, name in self._available_persons():
            self._identity_combo.addItem(name, person_id)
        # 2026-10-01：身份下拉接智能搜索 + 放大展开按钮（Owner 功能完善）。
        mark_searchable_combo(self._identity_combo)
        self._identity_search = NameSearchComboBinder(
            self._identity_combo, parent=self._identity_combo,
        )
        self._identity_label = QLabel(REVIEW_IDENTITY_LABEL, self)
        self._identity_hint = QLabel(REVIEW_IDENTITY_HINT, self)
        self._identity_hint.setWordWrap(True)

        identity_row = QHBoxLayout()
        identity_row.addWidget(self._identity_label)
        identity_row.addWidget(self._identity_combo, 1)

        button_row = QHBoxLayout()
        button_row.addWidget(self._approve_selected)
        button_row.addWidget(self._reject_selected)
        button_row.addWidget(self._approve_all)

        layout = QVBoxLayout(self)
        layout.addLayout(guidance_row)
        layout.addWidget(self._status)  # 待审核总数常驻列表顶部（Batch 5）
        layout.addWidget(self._list, 1)
        layout.addLayout(identity_row)
        layout.addWidget(self._identity_hint)
        layout.addLayout(button_row)

        # Wire selection changes → per-button enablement + counted texts (done
        # after the first refresh so construction-time selection changes are
        # inert). Keyboard multi-select works via ExtendedSelection defaults.
        self._list.itemSelectionChanged.connect(self._update_action_buttons)
        # 双击行 → 该照片的高清预览（人工辨别身份；打开即自动受控解码）。
        self._list.itemDoubleClicked.connect(self._on_row_double_clicked)

    def refresh(self) -> None:
        """Public re-query hook：切页进入与任务完成时由 MainWindow 调用。"""
        self._refresh_list()

    def set_busy(self, busy: bool) -> None:
        """任务运行期间禁用审核动作（与窗口级任务准入一致；选区保留）。"""
        self._busy = busy
        self._update_action_buttons()

    def _refresh_list(self) -> None:
        """Reload pending results; keep the page open with an empty state."""
        pending = self._controller.list_pending()
        self._list.clear()
        self._items_by_photo_id = {}
        for result in pending:
            self._list.addItem(self._make_row(result))
        # Batch 2: an emptied queue stays open and inspectable instead of
        # auto-closing; the entry must never appear to "flash and vanish".
        has_pending = bool(pending)
        self._list.setVisible(has_pending)
        self._status.setText(
            REVIEW_STATUS_LINE.format(count=len(pending)) if has_pending else REVIEW_EMPTY
        )
        self._update_action_buttons()

    def _update_action_buttons(self) -> None:
        """Enable queue actions and state the exact object counts (Batch 5)."""
        has_rows = self._list.count() > 0
        selection = self._list.selectedItems()
        self._approve_all.setEnabled(has_rows and not self._busy)
        self._approve_all.setText(
            REVIEW_APPROVE_ALL_COUNTED.format(count=self._list.count())
            if has_rows
            else REVIEW_APPROVE_ALL
        )
        self._approve_selected.setEnabled(has_rows and bool(selection) and not self._busy)
        self._reject_selected.setEnabled(has_rows and bool(selection) and not self._busy)
        if selection:
            counted = REVIEW_APPROVE_SELECTED_COUNTED.format(count=len(selection))
            rejected = REVIEW_REJECT_SELECTED_COUNTED.format(count=len(selection))
        else:
            counted = REVIEW_APPROVE_SELECTED
            rejected = REVIEW_REJECT_SELECTED
        self._approve_selected.setText(counted)
        self._reject_selected.setText(rejected)

    def _make_row(self, result: RecognitionResult) -> QListWidgetItem:
        """Build a two-line review row carrying the result id for actions.

        ADR-036: rows show human-readable photo file name and person name
        (resolved through the controller's read-side lookups) instead of bare
        UUIDs; unknown entities fall back to the UUID / 未知人员. Batch 5:
        the confidence is a textual band with the exact value kept in
        parentheses for audit, and the row states its status explicitly.
        """
        photo_label, person_label = self._controller.resolve_row_labels(result)
        confidence_text = (
            REVIEW_CONFIDENCE_NO_EVIDENCE
            if result.confidence is None
            else REVIEW_CONFIDENCE_FORMAT.format(
                band=confidence_band(result.confidence), value=result.confidence,
            )
        )
        item = QListWidgetItem("\n".join((
            REVIEW_ROW_FORMAT.format(
                photo_label=photo_label, person_label=person_label,
            ),
            REVIEW_ROW_DETAIL_FORMAT.format(
                confidence_text=confidence_text, status=STATUS_BADGE_PENDING,
            ),
        )))
        item.setData(Qt.ItemDataRole.UserRole, result.id)
        item.setData(RESULT_DATA_ROLE, result)
        self._request_row_thumbnail(item, result)
        return item

    def _request_row_thumbnail(self, item: QListWidgetItem, result: RecognitionResult) -> None:
        """Route one row's thumbnail through the shared async loader, if given.

        The photo entity comes from the controller's read-side lookup; a
        missing entity simply leaves the row without an icon. Items register
        under their photo id so the loader's signal can attach the image.
        """
        if self._thumbnail_source is None:
            return
        photo = self._controller.photo_for(result)
        if photo is None or photo.id is None:
            return
        self._items_by_photo_id.setdefault(photo.id, []).append(item)
        self._thumbnail_source.load_thumbnail(photo.id, photo.path.raw_path)

    def _attach_thumbnail(self, photo_id: object, thumbnail: object) -> None:
        """Attach an arrived thumbnail to every row of that photo (no-op on miss)."""
        if not isinstance(photo_id, UUID) or thumbnail is None:
            return
        items = self._items_by_photo_id.get(photo_id)
        if not items:
            return
        icon = QIcon(str(thumbnail))
        for item in items:
            item.setIcon(icon)

    @Slot(QListWidgetItem)
    def _on_row_double_clicked(self, item: QListWidgetItem) -> None:
        """双击行 → 打开该照片的高清审核预览（D1-A/D2-A/D3-B/D4-A）。

        队列快照 = 页面当前展示行（与用户所见一致），游标定位双击行；
        身份取页面当前选择器值（预览内只读展示，D2-A）；通过/拒绝经回调
        走与页面按钮相同的 bulk 路径并触发照片墙刷新。
        """
        result = item.data(RESULT_DATA_ROLE)
        if not isinstance(result, RecognitionResult):
            return
        photo = self._controller.photo_for(result)
        if photo is None:
            return
        entries: list[RecognitionResult] = []
        index = 0
        for row in range(self._list.count()):
            entry = self._list.item(row).data(RESULT_DATA_ROLE)
            if not isinstance(entry, RecognitionResult):
                continue
            if entry.id == result.id:
                index = len(entries)
            entries.append(entry)
        if not entries:
            return
        identity = self._selected_identity()
        preview = ReviewPreviewDialog(
            entries,
            index,
            photo_for=self._controller.photo_for,
            persons=self._available_persons(),
            identity=identity,
            on_approve=self._apply_preview_approve,
            on_reject=self._apply_preview_reject,
            parent=self,
        )
        # 预览内改选身份 → 回写本页选择器（连续双击时身份保持连续）。
        preview.identity_changed.connect(self._apply_preview_identity)
        preview.exec()

    def _apply_preview_identity(self, value: object) -> None:
        """预览内改选身份 → 回写页面选择器（连续双击时身份保持连续）。"""
        index = next(
            (i for i in range(self._identity_combo.count())
             if self._identity_combo.itemData(i) == value),
            0,
        )
        self._identity_combo.setCurrentIndex(index)

    def _apply_preview_approve(self, result: RecognitionResult, identity: UUID | None) -> None:
        """预览「通过本条」回调：单条批准路径 + 领域异常显式提示（S1-F6）。

        D-2 = B：照片未聚类等业务拒绝经 :meth:`approve_single` 传播到这里，
        以模态提示告知用户（与 D-1 未指定身份告警同一处理模式），队列随后
        刷新——被拒的行保持在队列中可见。
        """
        try:
            self._controller.approve_single(result.id, identity)
        except (
            PhotoNotClusteredError,
            ManualDecisionProtectedError,
            ConcurrentDecisionConflictError,
            ValidationError,
        ) as exc:
            message = (
                text.REVIEW_PHOTO_UNCLUSTERED
                if isinstance(exc, PhotoNotClusteredError)
                else (
                    text.REVIEW_PHOTO_AMBIGUOUS
                    if isinstance(exc, ReviewAnchorAmbiguousError)
                    else (str(exc) or text.REVIEW_DECISION_BLOCKED_FALLBACK)
                )
            )
            QMessageBox.warning(self, text.REVIEW_DECISION_BLOCKED_TITLE, message)
        self._refresh_list()
        self.review_changed.emit()

    def _apply_preview_reject(self, result: RecognitionResult) -> None:
        """预览「拒绝本条」回调：与页面按钮同一条 bulk 路径 + 即时刷新。"""
        self._controller.bulk_reject((result.id,))
        self._refresh_list()
        self.review_changed.emit()

    def _selected_ids(self) -> tuple[UUID, ...]:
        """Return the UUIDs carried by the currently selected list rows."""
        ids: list[UUID] = []
        for item in self._list.selectedItems():
            value = item.data(Qt.ItemDataRole.UserRole)
            if value is not None:
                ids.append(value)
        return tuple(ids)

    def _available_persons(self) -> list[tuple[UUID, str]]:
        """Return picker options, degrading to none when unsupported.

        The controller may be a light test double without the person read-side;
        an empty picker keeps the queue usable (approving then falls back to the
        explicit "no identity" warning) instead of failing construction.
        """
        lister = getattr(self._controller, "list_persons", None)
        if lister is None:
            return []
        try:
            return list(lister())
        except Exception:  # noqa: BLE001 - UI must not fail on a read-side stub
            return []

    def _selected_identity(self) -> UUID | None:
        """Return the identity chosen for approval (Stage 4 D-1), if any."""
        value = self._identity_combo.currentData()
        return value if isinstance(value, UUID) else None

    def _confirm_without_identity(self) -> bool:
        """Ask before approving without an identity; True to proceed anyway.

        D-1 says the human decision is final, so we never silently block it —
        but approving without an identity yields a row the archive planner
        cannot select, which the user must be told about explicitly.
        """
        answer = QMessageBox.question(
            self,
            REVIEW_APPROVE_ALL_CONFIRM_TITLE,
            REVIEW_NO_IDENTITY_WARNING,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _on_approve_selected(self) -> None:
        """Approve each selected pending result; refresh the list afterwards."""
        ids = self._selected_ids()
        if ids:
            person_id = self._selected_identity()
            if person_id is None and not self._confirm_without_identity():
                return
            self._controller.bulk_approve(ids, person_id)
        self._refresh_list()
        self.review_changed.emit()

    def _on_reject_selected(self) -> None:
        """Reject each selected pending result; refresh the list afterwards."""
        ids = self._selected_ids()
        if ids:
            self._controller.bulk_reject(ids)
        self._refresh_list()
        self.review_changed.emit()

    def _on_approve_all(self) -> None:
        """Approve every pending result — behind an explicit count confirmation.

        Batch 5: a full-queue approval is the one blind-batch hazard, so it
        must be confirmed with the exact count and an honest statement that
        the app offers no bulk undo. Cancel (the default) changes nothing.
        """
        all_ids = tuple(
            item.data(Qt.ItemDataRole.UserRole)
            for item in [self._list.item(i) for i in range(self._list.count())]
        )
        if not all_ids:
            return
        answer = QMessageBox.question(
            self,
            REVIEW_APPROVE_ALL_CONFIRM_TITLE,
            REVIEW_APPROVE_ALL_CONFIRM.format(count=len(all_ids)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        person_id = self._selected_identity()
        if person_id is None and not self._confirm_without_identity():
            return
        self._controller.bulk_approve(all_ids, person_id)
        self._refresh_list()
        self.review_changed.emit()
