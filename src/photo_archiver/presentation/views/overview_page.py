"""Overview page: welcome banner, five step cards and one primary CTA.

Batch 3 (UI/UX 收口) flow-driven workbench home. The widget renders an
:class:`OverviewModel` produced by :class:`OverviewPresenter` and re-emits
the chosen primary action; it performs no queries and holds no business
rules (Widget 不访问 Repository/SQLite, DEP-003/DEP-004).

阶段 2（§4-B 布局重组）：五步文本行改为五张步骤卡（P0-4 ``QFrame#Card``），
页首新增欢迎横幅（P0-4 ``QFrame#Banner`` severity=info）。数据语义不变：
仍由 :class:`OverviewModel` 单独驱动渲染，单一 primary CTA，任务期经
:func:`set_busy` 禁用；``render_model``/``set_busy``/``primary_clicked``/
``_primary_button``/``_model`` 签名与属性名不变。
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.controllers.overview_presenter import (
    OverviewModel,
)
from photo_archiver.presentation.visual_style import (
    ROLE_PRIMARY,
    assign_label_icon,
    assign_role,
    style_banner,
    style_card,
    style_page_subtitle,
    style_page_title,
    set_badge_severity,
    token,
)

from loguru import logger

_STEP_COUNT = 5


class OverviewPage(QWidget):
    """Checklist of the archival flow with a single guided next action."""

    primary_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the static frame: title, welcome banner, five step cards,
        primary CTA and the privacy note."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 参考图基线（Owner 2026-10-30）：页头＝品牌蓝图标 + 大标题。
        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        page_icon = QLabel(header)
        assign_label_icon(page_icon, "home", token("pa-accent-fg"), 22)
        title = QLabel(text.OVERVIEW_TITLE, header)
        style_page_title(title)
        header_layout.addWidget(page_icon)
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addWidget(header)

        # 欢迎横幅（P0-4 Banner 构建块；QSS padding 8px 12px 提供内边距）。
        banner = QFrame(self)
        style_banner(banner, "info")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(0, 0, 0, 0)
        welcome = QLabel(text.OVERVIEW_WELCOME, banner)
        welcome.setWordWrap(True)
        banner_layout.addWidget(welcome)
        layout.addWidget(banner)

        self._step_cards: list[QFrame] = []
        self._step_titles: list[QLabel] = []
        self._step_states: list[QLabel] = []
        self._step_details: list[QLabel] = []
        for _ in range(_STEP_COUNT):
            card = QFrame(self)
            style_card(card)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(6)
            card_header = QHBoxLayout()
            title = QLabel(card)
            bold = title.font()
            bold.setBold(True)
            title.setFont(bold)
            # 参考图基线：步骤状态用语义徽章（已完成＝success、待办＝warning），
            # 告别「✓ 已完成」裸文本（文案不变，仅容器化）；severity 由
            # render_model 按步骤态设定（构造期不预置）。
            state = QLabel(card)
            card_header.addWidget(title)
            card_header.addStretch()
            card_header.addWidget(state)
            detail = QLabel(card)
            detail.setWordWrap(True)
            card_layout.addLayout(card_header)
            card_layout.addWidget(detail)
            layout.addWidget(card)
            self._step_cards.append(card)
            self._step_titles.append(title)
            self._step_states.append(state)
            self._step_details.append(detail)

        layout.addStretch()
        # 参考图基线：主 CTA 右对齐常规尺寸（不再全宽横贯页面）。
        cta_row = QHBoxLayout()
        cta_row.addStretch()
        self._primary_button = QPushButton(self)
        assign_role(self._primary_button, ROLE_PRIMARY)
        self._primary_button.clicked.connect(self._emit_primary)
        # Owner 2026-10-30：概览页不再显示该 CTA（构造期即隐藏；render_model
        # 也恒定 setVisible(False)）。
        self._primary_button.setVisible(False)
        cta_row.addWidget(self._primary_button)
        layout.addLayout(cta_row)

        privacy = QLabel(text.OVERVIEW_PRIVACY_NOTE, self)
        privacy.setWordWrap(True)
        style_page_subtitle(privacy)
        layout.addWidget(privacy)
        self._model = OverviewModel((), None, "", "")

    @Slot()
    def _emit_primary(self) -> None:
        """Re-emit the rendered primary action id for the window to dispatch."""
        if self._model.primary is not None:
            logger.debug("Overview primary action {} requested", self._model.primary)
            self.primary_clicked.emit(self._model.primary)

    def render_model(self, model: OverviewModel) -> None:
        """Replace the step cards' text, CTA label and CTA enablement.

        语义与阶段 2 前一致：只渲染模型内容；模型步数不足时多余卡片隐藏
        （空快照 → 五卡全隐、无 CTA），不引入任何新行为分支。
        """
        self._model = model
        for index, card in enumerate(self._step_cards):
            if index >= len(model.steps):
                card.setVisible(False)
                continue
            card.setVisible(True)
            step = model.steps[index]
            mark = (
                text.OVERVIEW_STEP_DONE_MARK if step.done
                else text.OVERVIEW_STEP_TODO_MARK
            )
            state = text.OVERVIEW_STEP_DONE if step.done else text.OVERVIEW_STEP_TODO
            self._step_titles[index].setText(step.label)
            self._step_states[index].setText(f"{mark} {state}")
            set_badge_severity(
                self._step_states[index], "success" if step.done else "warning",
            )
            self._step_details[index].setText(step.detail)
        has_primary = model.primary is not None
        # Owner 2026-10-30：概览页不再显示主 CTA 按钮（指导入口统一在
        # 照片库页头部「下一步」+ 各页面内）。按钮对象保留以承载引导态数据
        # （文本/tooltip/启用语义与既有测试核对面不变），恒不显示。
        self._primary_button.setVisible(False)
        self._primary_button.setText(model.primary_label)
        self._primary_button.setToolTip(model.primary_tooltip)
        self._primary_button.setEnabled(has_primary)

    def set_busy(self, busy: bool, label: str) -> None:
        """Keep the CTA unusable while another long task owns the window."""
        if busy:
            self._primary_button.setEnabled(False)
            self._primary_button.setToolTip(
                text.OVERVIEW_PRIMARY_BUSY.format(label=label),
            )
        elif self._model.primary is not None:
            self._primary_button.setEnabled(True)
            self._primary_button.setToolTip(self._model.primary_tooltip)
