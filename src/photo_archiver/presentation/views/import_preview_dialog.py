"""Import preview and confirmation dialog (people-import redesign stage A).

Owner plan §4.2: the dialog shows every draft row as
原始内容 / 解析结果 / 告警 / 处理动作 and lets the user split multi-name
cells, switch actions, edit fields, and re-parse with different options
(header, sheet, field mapping) before anything touches the formal registry.

The dialog never writes people itself — it persists draft edits through
``ParseImportDraftService`` and, on accept, hands the batch back to the
window, which runs ``ConfirmImportService`` synchronously (≤500 rows) or
submits ``ConfirmImportTask`` for larger rosters. Cancel keeps the formal
registry untouched and offers no draft-revisit entry (P10/D6-A: the status
message tells the user the draft is dropped and a re-import re-picks the
file).
"""

from __future__ import annotations

import html
from uuid import UUID

import shiboken6
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.commands.import_draft import (
    ReparseImportDraftCommand,
)
from photo_archiver.application.dtos.import_draft import ImportDraft
from photo_archiver.application.services.parse_import_draft_service import (
    split_name_segments,
)
from photo_archiver.domain.entities import (
    DRAFT_ACTION_CREATE,
    DRAFT_ACTION_MERGE_EXISTING,
    DRAFT_ACTION_SKIP,
)
from photo_archiver.presentation import ui_text as text, visual_style
from photo_archiver.presentation.visual_style import (
    ROLE_PRIMARY,
    assign_role,
    assign_button_icon,
    style_card,
    style_page_subtitle,
    style_page_title,
    token,
)

CONFIRM_SYNC_LIMIT = 500

_ACTION_LABELS = (
    (DRAFT_ACTION_CREATE, text.IMPORT_PREVIEW_ACTION_CREATE),
    (DRAFT_ACTION_MERGE_EXISTING, text.IMPORT_PREVIEW_ACTION_MERGE),
    (DRAFT_ACTION_SKIP, text.IMPORT_PREVIEW_ACTION_SKIP),
)
_FIELDS = ("name", "identity", "department", "note", "group")


class _ActionCombo(QComboBox):
    """处理动作下拉（每行一个）：禁止滚轮切换（Owner 追加轮 26）.

    表格单元格内嵌的下拉在滚轮扫过时会被误换值（默认 WheelFocus 策略）。
    本类把滚轮事件 **ignore**——不消费即向父级传播，表格照常滚动；换值
    只允许点击展开后选择。
    """

    def wheelEvent(self, event) -> None:  # noqa: N802  # Qt 虚函数名
        event.ignore()

# P8 告警分级：每级的（前缀符号, 前景 token, 背景 token）——三级两两可
# 区分；未知 code 走 ``_IMPORT_WARNING_DEFAULT_STYLE``（默认样式，不崩溃）。
# 配色以富文本 span 落在告警行内（不经 widget 级 stylesheet，遵循视觉系统
# 单一样式表约定）。色值经 visual_style token 在调用时按当前主题解析
# （P0-8 C1 迁移：浅色值＝现值冻结 VERIFIED；深色＝P0-1 §1.5 建议值
# UNVERIFIED，三级明度排序不变）。
_IMPORT_WARNING_TOKEN_STYLES = {
    text.IMPORT_WARNING_SEVERITY_STRONG: ("⛔", "pa-alert-fg", "pa-alert-bg"),
    text.IMPORT_WARNING_SEVERITY_WEAK: ("⚠", "pa-warning-fg", "pa-warning-bg"),
    text.IMPORT_WARNING_SEVERITY_INFO: ("ℹ", "pa-info-fg", "pa-info-bg"),
}
_IMPORT_WARNING_DEFAULT_STYLE: tuple[str, None, None] = ("•", None, None)


def import_warning_style(severity: str) -> tuple[str, str | None, str | None]:
    """Return (前缀符号, 前景色, 背景色)，色值按当前激活主题解析（P0-8 C1）。

    未知 severity 返回默认样式（无配色，不崩溃）；token 名取自 P0-1 冻结表。
    """
    symbol, fg_token, bg_token = _IMPORT_WARNING_TOKEN_STYLES.get(
        severity, _IMPORT_WARNING_DEFAULT_STYLE
    )
    if fg_token is None or bg_token is None:
        return symbol, None, None
    return symbol, visual_style.token(fg_token), visual_style.token(bg_token)
# 严重级排序（小 = 更严重）：用于多告警行的 tooltip 排序与整体定级。
_IMPORT_WARNING_SEVERITY_RANK = {
    text.IMPORT_WARNING_SEVERITY_STRONG: 0,
    text.IMPORT_WARNING_SEVERITY_WEAK: 1,
    text.IMPORT_WARNING_SEVERITY_INFO: 2,
    text.IMPORT_WARNING_SEVERITY_DEFAULT: 3,
}


def classify_import_warning(code: str) -> str:
    """Return a warning code's severity class（P8）.

    已知 7 种 code 按现有文案语义归入 强冲突/弱冲突/提示 三级；未知 code
    一律 ``default``（默认样式，绝不因未知值崩溃）。
    """
    return text.IMPORT_WARNING_SEVERITIES.get(code, text.IMPORT_WARNING_SEVERITY_DEFAULT)


def warning_severity_rank(severity: str) -> int:
    """Return the severity's rank (smaller = more severe)."""
    return _IMPORT_WARNING_SEVERITY_RANK.get(severity, len(_IMPORT_WARNING_SEVERITY_RANK))


def build_warning_label(warnings, parent=None) -> QLabel:  # noqa: ANN001
    """Render structured warnings as one graded, color-coded label（P8）.

    每条告警一行：分级前缀符号 + 前景/背景配色（富文本 span，HTML 转义防
    注入）；未知 code 使用默认样式。返回的 QLabel 由调用方决定挂载位置。
    """
    label = QLabel(parent)
    label.setWordWrap(True)
    lines = []
    for code, detail in warnings:
        severity = classify_import_warning(code)
        symbol, fg, bg = import_warning_style(severity)
        template = text.IMPORT_WARNING_TEXTS.get(code, text.IMPORT_PREVIEW_DEFAULT_WARNING)
        body = html.escape(template.format(code=code, detail=detail))
        if fg is not None and bg is not None:
            body = (
                f'<span style="color:{fg}; background-color:{bg};">'
                f"{symbol} {body}</span>"
            )
        else:
            body = f"{symbol} {body}"
        lines.append(body)
    label.setText("<br>".join(lines))
    return label


class ImportPreviewDialog(QDialog):
    """Edit a parsed import draft; accept = ready for the window to confirm."""

    def __init__(self, draft: ImportDraft, services, source_path, parent=None) -> None:  # noqa: ANN001
        """Build the four-zone preview over the persisted draft batch.

        Args:
            draft: The parsed draft from ``ParseImportDraftService``.
            services: Application service container (parse/confirm services).
            source_path: Absolute roster file path (reparse/sheet listing).
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self.setWindowTitle(text.IMPORT_PREVIEW_TITLE)
        self.resize(960, 560)
        self._services = services
        self._draft = draft
        self._source_file = source_path
        self._has_header = draft.batch.has_header
        self._sheet_name = draft.batch.sheet_name
        self._build_ui()
        self._repopulate()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Lay out page header, options card, draft table, counts row, buttons.

        参考图视觉对齐（taskbook-8 §4 纯视觉项，Owner 2026-10-30 基线裁决）：
        页头标题＋副标题、选项行 Card 化、按钮挂 Fluent 图标；差异①-⑥按
        保守值不实施（无查看映射/查看/…、保留 8 列、无右侧统计面板）。
        """
        layout = QVBoxLayout(self)

        # 参考图区块 #1：页头标题＋副标题（纯视觉；副标题经 ui_text 新键）。
        header = QWidget(self)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)
        title = QLabel(text.IMPORT_PREVIEW_TITLE, header)
        style_page_title(title)
        subtitle = QLabel(text.IMPORT_PREVIEW_SUBTITLE, header)
        style_page_subtitle(subtitle)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        # 参考图区块 #2：选项行 Card 化（文件/编码/分隔符/表头/工作表/重新解析，
        # 全部既有控件与语义零变化）。
        card = QFrame(self)
        style_card(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        options_row = QHBoxLayout()
        self._file_label = QLabel(
            text.IMPORT_PREVIEW_FILE_LABEL + str(self._draft.batch.file_name), card,
        )
        options_row.addWidget(self._file_label)
        options_row.addWidget(QLabel(
            text.IMPORT_PREVIEW_ENCODING_LABEL + str(self._draft.batch.encoding or "—"), card,
        ))
        options_row.addWidget(QLabel(
            text.IMPORT_PREVIEW_DELIMITER_LABEL + str(self._draft.batch.delimiter or "—"), card,
        ))
        self._header_check = QCheckBox(text.IMPORT_PREVIEW_HEADER_LABEL, card)
        self._header_check.setChecked(self._has_header)
        self._header_check.toggled.connect(self._on_options_changed)
        options_row.addWidget(self._header_check)
        self._sheet_combo: QComboBox | None = None
        if self._draft.batch.source_type in ("xlsx", "xlsm", "xls"):
            sheet_names = self._services.parse_import_draft.list_sheets(self._source_file)
            if sheet_names:
                options_row.addWidget(QLabel(text.IMPORT_PREVIEW_SHEET_LABEL, card))
                self._sheet_combo = QComboBox(card)
                self._sheet_combo.addItems(sheet_names)
                if self._sheet_name:
                    index = self._sheet_combo.findText(self._sheet_name)
                    if index >= 0:
                        self._sheet_combo.setCurrentIndex(index)
                self._sheet_combo.currentIndexChanged.connect(self._on_options_changed)
                options_row.addWidget(self._sheet_combo)
        reparse = QPushButton(text.IMPORT_PREVIEW_REPARSE_BUTTON, card)
        reparse.clicked.connect(self._on_options_changed)
        assign_button_icon(reparse, "sync", token("pa-text-secondary"))
        options_row.addWidget(reparse)
        options_row.addStretch()
        card_layout.addLayout(options_row)
        layout.addWidget(card)

        self._height_probe = QLabel()  # F-IMP-1 行高度量用（不挂父、不显示）
        self._height_probe.setWordWrap(True)  # heightForWidth 需开启换行
        self._row_height_resize_pending = False  # F-IMP-1 延迟重算去重
        self._table = QTableWidget(0, 8, self)
        # F-IMP-1 配套：告警列（列 5）Stretch——wordWrap 告警 QLabel 有可用
        # 宽度，行高自适应后长告警完整可读（不截断、不省略）。
        self._table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.Stretch,
        )
        # F-IMP-1 N3：窗口缩小或用户拖宽他列时，Stretch 告警列随之变窄 →
        # wordWrap 换行行数增加，行高必须按新列宽重算，否则长告警再次被
        # 裁剪（resizeRowsToContents 只在 (re)populate 时算一次）。
        self._table.horizontalHeader().sectionResized.connect(
            self._on_table_section_resized,
        )
        self._table.setAlternatingRowColors(True)
        self._table.setHorizontalHeaderLabels([
            text.IMPORT_PREVIEW_COL_RAW,
            text.IMPORT_PREVIEW_COL_NAME,
            text.IMPORT_PREVIEW_COL_IDENTITY,
            text.IMPORT_PREVIEW_COL_DEPARTMENT,
            text.IMPORT_PREVIEW_COL_NOTE,
            text.IMPORT_PREVIEW_COL_WARNINGS,
            text.IMPORT_PREVIEW_COL_ACTION,
            "",
        ])
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed,
        )
        self._table.verticalHeader().setVisible(False)
        self._table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._table, 1)

        counts_row = QHBoxLayout()
        self._counts_label = QLabel(self)
        self._counts_label.setWordWrap(True)
        counts_row.addWidget(self._counts_label)
        counts_row.addStretch()
        layout.addLayout(counts_row)
        # P9：逐次动作反馈（如拆分 no-op 的可见提示），不随重绘清除。
        self._feedback_label = QLabel(self)
        self._feedback_label.setWordWrap(True)
        layout.addWidget(self._feedback_label)
        if len(self._draft.rows) > CONFIRM_SYNC_LIMIT:
            notice = QLabel(
                text.IMPORT_PREVIEW_CONFIRM_LARGE.format(limit=CONFIRM_SYNC_LIMIT), self,
            )
            notice.setWordWrap(True)
            layout.addWidget(notice)

        buttons = QHBoxLayout()
        cancel = QPushButton(text.IMPORT_PREVIEW_CANCEL_BUTTON, self)
        cancel.setDefault(True)
        cancel.clicked.connect(self.reject)
        confirm = QPushButton(text.IMPORT_PREVIEW_CONFIRM_BUTTON, self)
        assign_role(confirm, ROLE_PRIMARY)
        assign_button_icon(confirm, "download", token("pa-accent-text"))
        confirm.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

    def _on_table_section_resized(self, logical_index: int, _old: int, _new: int) -> None:
        """F-IMP-1 N3：告警列宽度变化时重算行高（窄列/窗口缩小不裁剪）。

        只响应告警列（列 5）；信号回调时列宽可能仍是过渡值，统一延迟到
        事件循环内按最终列宽度量；行高重算不改列宽，无级联回环。
        """
        if logical_index == 5 and self._table.rowCount() > 0:
            self._schedule_row_height_resize()

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        """F-IMP-1 N3：窗口尺寸变化（Stretch 列随之变宽/变窄）后重算行高。"""
        super().resizeEvent(event)
        self._schedule_row_height_resize()

    def _schedule_row_height_resize(self) -> None:
        """延迟到事件循环内重算行高（等待列宽分布/过渡值最终稳定）。"""
        if self._row_height_resize_pending:
            return
        self._row_height_resize_pending = True
        # NB-1：以 self 为连接上下文的单发定时器——对话框销毁后连接随对象
        # 一并失效，已排队的回调不再触发；回调内另有 shiboken6.isValid
        # 守卫双保险：无论经哪条路径在销毁后被调用，都安全退出，不访问
        # 已销毁的 Qt 对象（不吞 RuntimeError 掩盖生命周期问题）。
        QTimer.singleShot(0, self, self._run_deferred_row_height_resize)

    def _run_deferred_row_height_resize(self) -> None:
        """NB-1：事件循环内的延迟行高重算；对话框已销毁时安全退出。"""
        if not shiboken6.isValid(self):
            return
        self._row_height_resize_pending = False
        self._resize_rows_to_content()

    def _resize_rows_to_content(self) -> None:
        """F-IMP-1：行高 = 告警富文本按当前告警列宽换行后的完整高度。

        ``resizeRowsToContents`` 依据 widget 的 sizeHint（按其自身提示宽度
        折算），在窄告警列下会低估换行行数导致残余裁剪；已挂载 QLabel 的
        ``heightForWidth`` 又受内部文档布局状态影响可能返回旧值。这里用
        独立的隐藏 QLabel（每次 setText 后度量，无挂载状态）按当前告警
        列宽度量告警富文本的换行高度（F-IMP-1 验收：告警文字完整可读），
        并与整行其他内容的 sizeHint 取大者，不裁剪动作列等既有内容。
        度量不可用（≤0）或非告警行回退 Qt 默认计算。调用时机经
        :meth:`_schedule_row_height_resize` 延迟到事件循环内，保证按
        稳定后的最终列宽度量。
        """
        table = self._table
        available_width = max(table.columnWidth(5) - 2, 1)
        probe = self._height_probe
        for row_index in range(table.rowCount()):
            needed = table.sizeHintForRow(row_index)
            widget = table.cellWidget(row_index, 5)
            if isinstance(widget, QLabel) and widget.wordWrap():
                probe.setFont(widget.font())
                probe.setText(widget.text())
                wrapped = probe.heightForWidth(available_width)
                if wrapped > 0:
                    needed = max(needed, wrapped)
            if needed > 0:
                table.setRowHeight(row_index, needed)

    # ── Data plumbing ────────────────────────────────────────────────────

    @property
    def batch_id(self) -> UUID:
        """The confirmed draft batch id (valid after :meth:`exec` accepts)."""
        return self._draft.batch.id  # type: ignore[return-value]

    @property
    def row_count(self) -> int:
        """Draft row count at accept time (drives sync vs worker confirm)."""
        return len(self._draft.rows)

    def set_source_file(self, path) -> None:  # noqa: ANN001
        """Record the absolute source path (needed for sheet listing/reparse)."""
        self._source_file = path

    def _on_options_changed(self) -> None:
        """Re-parse the file with the current header/sheet options."""
        self._has_header = self._header_check.isChecked()
        if self._sheet_combo is not None:
            self._sheet_name = self._sheet_combo.currentText() or None
        mapping = {field: index for field, index in self._draft.field_mapping.items()}
        self._draft = self._services.parse_import_draft.reparse(
            ReparseImportDraftCommand(
                batch_id=self._draft.batch.id,  # type: ignore[arg-type]
                source_path=self._source_file,
                has_header=self._has_header,
                sheet_name=self._sheet_name,
                field_mapping=mapping,
            ),
        )
        self._repopulate()

    def _repopulate(self) -> None:
        """Rebuild the table from the current draft rows."""
        rows = self._draft.rows
        self._table.blockSignals(True)
        # 追加轮 24：先清空行集再重建——拆分/重新解析后行数与行位都会变化，
        # 列 7 的拆分按钮是唯一条件化设置的 cellWidget，复用旧行位会继承上
        # 一次填充残留的按钮（拆分结果行带出幽灵拆分键——Owner 实机实证）。
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self._table.setItem(row_index, 0, self._readonly_cell("　".join(row.raw_values)))
            name_item = QTableWidgetItem(row.parsed_name)
            self._table.setItem(row_index, 1, name_item)
            self._table.setItem(row_index, 2, self._editable_cell(row.parsed_identity))
            self._table.setItem(row_index, 3, self._editable_cell(row.parsed_department))
            self._table.setItem(row_index, 4, self._editable_cell(row.parsed_note))
            # P8：告警列改为分级渲染的 QLabel（前缀符号 + 配色），完整纯文本
            # 保留在 tooltip；未知 code 降级为默认样式，不崩溃。
            warnings_label = build_warning_label(row.warnings, self)
            warnings_label.setToolTip(self._warnings_text(row))
            self._table.setCellWidget(row_index, 5, warnings_label)
            action = _ActionCombo(self)
            for value, label in _ACTION_LABELS:
                action.addItem(label, value)
            current = _ACTION_LABELS_INDEX.get(row.action, 0)
            action.setCurrentIndex(current)
            action.currentIndexChanged.connect(
                lambda index, r=row: self._on_action_changed(r, index),
            )
            self._table.setCellWidget(row_index, 6, action)
            if any(w[0] == "multi_name" for w in row.warnings) and len(
                split_name_segments(row.parsed_name),
            ) > 1:
                # 追加轮 24：显示判定与实际拆分同口径——单段名（拆分结果行）
                # 即使残留 multi_name 警告也不再显示拆分键（点了也只能 no-op）。
                split = QPushButton(text.IMPORT_PREVIEW_SPLIT_BUTTON, self)
                split.clicked.connect(lambda _=False, r=row: self._on_split(r))
                self._table.setCellWidget(row_index, 7, split)
        self._table.blockSignals(False)
        # F-IMP-1：行高随内容自适应——wordWrap 告警 QLabel 的行全高显示
        # （不截断、不省略；tooltip 全文保留）。重绘后（拆分/重新解析/动作
        # 切换路径均经 _repopulate）行高保持正确；⛔/⚠/ℹ 分级与排序零变化。
        self._schedule_row_height_resize()
        self._refresh_counts()

    @staticmethod
    def _readonly_cell(value: str) -> QTableWidgetItem:
        """Non-editable cell with full text in the tooltip."""
        item = QTableWidgetItem(value)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setToolTip(value)
        return item

    @staticmethod
    def _editable_cell(value: str | None) -> QTableWidgetItem:
        """Editable cell (empty string for None)."""
        return QTableWidgetItem(value or "")

    def _warnings_text(self, row) -> str:  # noqa: ANN001
        """Format the row's structured warnings into one user-readable line."""
        formatted = []
        for code, detail in row.warnings:
            template = text.IMPORT_WARNING_TEXTS.get(code, text.IMPORT_PREVIEW_DEFAULT_WARNING)
            formatted.append(template.format(code=code, detail=detail))
        return "；".join(formatted)

    def _row_for(self, table_row: int):
        """Return the draft row backing a table row (order_index == table order)."""
        return self._draft.rows[table_row]

    _EDITABLE_COLUMNS = {1: "parsed_name", 2: "parsed_identity", 3: "parsed_department", 4: "parsed_note"}

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Persist a committed cell edit back into the draft row."""
        field_name = self._EDITABLE_COLUMNS.get(item.column())
        if field_name is None or item.row() >= len(self._draft.rows):
            return
        row = self._draft.rows[item.row()]
        value = item.text().strip()
        if field_name == "parsed_name":
            row.parsed_name = value  # 姓名保持空串语义（实体校验负责拒绝真空名）
        else:
            setattr(row, field_name, value or None)
        self._draft = self._services.parse_import_draft.save_draft_rows(
            self._draft.batch.id, self._draft.rows,
        )
        self._refresh_counts()

    def _on_action_changed(self, row, index: int) -> None:  # noqa: ANN001
        """Persist an action switch from the per-row combo."""
        row.action = _ACTION_LABELS[index][0]
        self._draft = self._services.parse_import_draft.save_draft_rows(
            self._draft.batch.id, self._draft.rows,
        )
        self._refresh_counts()

    def _on_split(self, row) -> None:  # noqa: ANN001
        """Split one multi-name draft row into one row per name.

        P9：无可拆内容时给出可见反馈（此前为静默 no-op）。
        """
        self._draft, changed = self._services.parse_import_draft.split_draft_row_with_status(
            self._draft.batch.id, row.id,
        )
        if not changed:
            self._feedback_label.setText(text.IMPORT_PREVIEW_SPLIT_NOOP)
        else:
            self._feedback_label.clear()
        self._repopulate()

    def _refresh_counts(self) -> None:
        """Refresh the will-create/merge/skip/warnings counters."""
        warning_rows = sum(1 for row in self._draft.rows if row.warnings)
        self._counts_label.setText(text.IMPORT_PREVIEW_COUNTS.format(
            total=len(self._draft.rows),
            create=self._draft.create_count,
            merge=self._draft.merge_count,
            skip=self._draft.skip_count,
            warnings=warning_rows,
        ))


_ACTION_LABELS_INDEX = {value: index for index, (value, _) in enumerate(_ACTION_LABELS)}
