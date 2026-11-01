"""People & grouping page — stage B of the people-import redesign (D5).

The roster is the ordered registry the photo library filters by, so this page
makes it editable: add, edit, delete (through the existing danger-confirm
dialog) and drag-reorder. ``来源批次`` shows which import brought a person in,
and the batch selector offers a read-only review of one batch at a time.

Layer note: the page talks to Application services only (DEP-010); it owns no
repository, no SQL and no business rule — validation errors come back from
``ManagePeopleService`` and are shown verbatim.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

from loguru import logger
from PySide6.QtCore import Qt, QSignalBlocker, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.commands import (
    AddPersonCommand,
    DeletePersonCommand,
    EditPersonCommand,
    ReorderPeopleCommand,
)
from photo_archiver.application.dtos import ImportBatchSummary, PersonDeletionResult
from photo_archiver.application.services import (
    ClusterResultsService,
    ListPersonsService,
    ListRecognitionRunsService,
    ManagePeopleService,
    RosterClusterStatsService,
)
from photo_archiver.domain import Person
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import (
    ROLE_DANGER,
    ROLE_PRIMARY,
    ROLE_SECONDARY,
    assign_label_icon,
    assign_role,
    assign_button_icon,
    style_card,
    style_page_subtitle,
    style_page_title,
    style_section_title,
    style_stat_value,
    token,
)
from photo_archiver.presentation.views.batch_person_deletion_dialog import (
    BatchPersonDeletionDialog,
    ClearAllPeopleDialog,
)
from photo_archiver.presentation.views.person_deletion_dialog import (
    MultiPersonDeletionDialog,
    PersonDeletionDialog,
)
from photo_archiver.presentation.views.person_edit_dialog import PersonEditDialog
from photo_archiver.presentation.views.run_deletion_dialog import (
    RunPeopleDeletionDialog,
    RunPhotosDeletionDialog,
    RunRecordDeletionDialog,
)

# 界面优化 §4.1：取消行内操作列——编辑移至工具栏（选中行生效），
# 减少操作栏占用；身份/排序/批次归属/删除能力全部保留。
# 阶段 2 方案 a：新增「组/序」合并列（组号与组内序号合一以控制宽度），
# 插在「顺序」列之后；各列定位常量供渲染与选中逻辑共用。
# P4：新增「匹配状态」列（末尾）——按统计锚点（最新代际）的当前有效决策
# 判定该人员是否已被指派（D3-A）。
_COLUMNS = (
    text.PEOPLE_PAGE_COL_ORDER,
    text.PEOPLE_PAGE_COL_GROUP_ORDINAL,
    text.PEOPLE_PAGE_COL_NAME,
    text.PEOPLE_PAGE_COL_IDENTITY,
    text.PEOPLE_PAGE_COL_DEPARTMENT,
    text.PEOPLE_PAGE_COL_NOTE,
    text.PEOPLE_PAGE_COL_BATCH,
    text.PEOPLE_PAGE_COL_MATCH_STATUS,
)
# 参考图 C1（Owner 2026-10-30 裁决：D5-A 复选框列按图推翻实施）：首列为
# 行选择复选框——勾选＝选中该行，与既有 ExtendedSelection/「删除所选」/
# 多选禁拖拽语义并存（选择模型仍是唯一选择语义源，复选框仅是镜像视图）。
_COLUMN_CHECK = 0
_COLUMN_SHIFT = 1
_COLUMN_GROUP_ORDINAL = 1 + _COLUMN_SHIFT
_COLUMN_NAME = 2 + _COLUMN_SHIFT
_COLUMN_MATCH_STATUS = 7 + _COLUMN_SHIFT

# 组内序号取姓名开头的连续数字前缀（如「3张三」→ 3；无前缀 → None）。
_NAME_ORDINAL_PATTERN = re.compile(r"^\d+")

# Owner 2026-10-31：复选框列固定宽度——ResizeToContents 对空文本复选框列
# 的重算在重渲染后可能漂移（实机报告「移动后第一列偏移」），固定后恒定；
# 表头全选框几何随之稳定。
_CHECK_COLUMN_WIDTH = 40
_HEADER_CHECK_MARGIN = 8


class _HeaderSelectAll(QCheckBox):
    """表头全选框：用户点击＝请求全选/全不选（三态仅用于显示部分选中）。

    覆盖 ``nextCheckState``——用户点击不再本地翻转三态，而是向页面发
    ``toggled_all``（页面据此 selectAll/clearSelection，选择模型仍是唯一
    语义源）；显示态由页面按选区程序化设置（含 PartiallyChecked）。
    """

    toggled_all = Signal(bool)

    def nextCheckState(self) -> None:  # noqa: N802  # Qt 虚函数名
        self.toggled_all.emit(self.checkState() != Qt.CheckState.Checked)

# 阶段 3 工具行分组（决策项 #3 保守值）：仅主操作｜次级｜危险三组之间加
# 组间距，不加分隔线、不赋 neutral 角色、按钮顺序零改动。
_TOOLBAR_GROUP_SPACING = 16


def derive_group_ordinals(
    names: Sequence[str],
) -> list[tuple[int | None, int | None]]:
    """按名单顺序派生每人的（组号, 组内序号）——阶段 2 方案 a 纯只读规则。

    输入顺序必须是 roster 顺序（``roster_order`` 升序，即页面展示顺序）。
    派生规则（任务书 §1.5；纯显示值，零 schema、零持久化）：

    - 组内序号 = 姓名开头的数字前缀（``^\\d+``）；无数字前缀为 ``None``
      （前缀非数字同样不匹配，降级为 ``None``）。
    - 组号 = 沿名单顺序行走序号链：首个带序号者开启第 1 组；此后凡序号
      不再接续「前一（带序号）者 + 1」——重新从 1 开始、重复或跳号——即
      视为一次跳变，跳变处组号 +1。无前缀者不参与链比较，继承当前组号
      （组链尚未开启时为 ``None``）。
    - 整份名单只派生出一组（无任何跳变）时组号无意义，全部返回 ``None``
      （展示层显示「—」）。

    Returns:
        与 ``names`` 等长的 (组号, 组内序号) 列表，两者均可为 ``None``。
    """
    ordinals = [
        int(match.group()) if (match := _NAME_ORDINAL_PATTERN.match(name)) else None
        for name in names
    ]
    groups: list[int | None] = []
    group_no: int | None = None
    previous_ordinal: int | None = None
    for ordinal in ordinals:
        if ordinal is None:
            groups.append(group_no)
            continue
        if group_no is None or previous_ordinal is None or ordinal != previous_ordinal + 1:
            group_no = 1 if group_no is None else group_no + 1
        groups.append(group_no)
        previous_ordinal = ordinal
    if group_no is not None and group_no == 1:
        # 仅一组：组号无区分意义，按任务书显示「—」。
        groups = [None] * len(groups)
    return list(zip(groups, ordinals, strict=True))


def format_group_ordinal(group: int | None, ordinal: int | None) -> str:
    """Render one（组号, 组内序号）pair as the「组/序」cell text."""
    if group is None and ordinal is None:
        return "—"
    return f"{'—' if group is None else group}/{'—' if ordinal is None else ordinal}"


_ROW_MIME_TYPE = "application/x-qabstractitemmodeldatalist"


class _ReorderableTable(QTableWidget):
    """Table whose rows can be dragged to re-ask the page for a new order.

    A drag is a *positional request*, never a model edit: the page re-renders
    from the domain roster after the drop, so the table model stays the single
    source of truth. Two Qt details make that work (both verified against the
    shipped PySide6 build — stage-B review fix #2):

    - ``setDragDropMode(DragOnly)`` turns ``acceptDrops`` back off, so drops
      arrive only when the view *and* its viewport re-enable it after the mode
      call;
    - accepting a drop with its proposed ``MoveAction`` makes
      ``QAbstractItemView::startDrag`` run its internal ``clearOrRemove()``
      afterwards, removing the source row from the model *after* the page had
      re-rendered — exactly the blank row of the stage-B review. The drop is
      accepted as ``CopyAction`` instead (a table drag offers ``Copy|Move``, so
      the downgrade always applies), and the stale selection is cleared as a
      second guard for a drag that could not be downgraded.

    P11（D5-A 最小版）：选择模式为 ``ExtendedSelection`` 支持多选删除；但
    拖拽重排仅属于单选——选中数 > 1 时页面统一关闭 ``dragEnabled``（互斥
    规则，见 ``PeopleAdminPage._render_action_state``）。
    """

    rows_dropped = Signal(int, int)  # (source_row, target_row)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Configure the table for extended (multi-row) selection with row dragging."""
        super().__init__(parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._drag_source_row: int | None = None
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        # Order matters: the mode call above turns both drop flags back off.
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(False)

    def startDrag(self, supported_actions) -> None:  # noqa: ANN001  # Qt signature
        """Remember which row the drag started from, then run Qt's drag loop."""
        self._drag_source_row = self.currentRow()
        super().startDrag(supported_actions)

    def dragEnterEvent(self, event) -> None:  # noqa: ANN001  # Qt signature
        """Accept this table's own row payload; ignore every foreign drag."""
        if self._is_row_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: ANN001  # Qt signature
        """Keep one of our own row drags alive while it is over the viewport."""
        if self._is_row_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: ANN001  # Qt signature
        """Translate a row drop into a reorder request instead of a copy."""
        source_row = self._drag_source_row
        self._drag_source_row = None
        if source_row is None:
            source_row = self.currentRow()
        target_row = self.indexAt(event.position().toPoint()).row()
        if target_row < 0:  # dropped in the empty area below the last row
            target_row = self.rowCount() - 1
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        if source_row < 0 or target_row < 0 or source_row == target_row:
            return
        self.rows_dropped.emit(source_row, target_row)
        if event.dropAction() != Qt.DropAction.CopyAction:
            # Qt could not downgrade this drop, so its internal clearOrRemove()
            # is about to delete the selected row from the model: no row (and
            # in particular not the freshly re-selected moved one) may stay
            # selected.
            self.clearSelection()

    def _is_row_drag(self, event) -> bool:  # noqa: ANN001  # Qt signature
        """Return True while one of our own draggable rows is over the table."""
        if not self.dragEnabled() or not event.mimeData().hasFormat(_ROW_MIME_TYPE):
            return False
        source = event.source()
        return source is None or source is self or source is self.viewport()


class PeopleAdminPage(QWidget):
    """Ordered roster table with add/edit/delete and drag reordering."""

    # structure_changed=False marks a pure reorder: the roster contents are
    # unchanged, so the window leaves the filter axis and the readiness
    # snapshot alone (the page has already re-rendered itself by then).
    people_changed = Signal(bool)
    # D-4 聚类入口：页面只发请求信号，运行/对话框由主窗口按既有任务管线处理。
    cluster_run_requested = Signal()
    cluster_results_requested = Signal()
    # 名单导入入口（Owner 2026-10-30：顶部工具栏撤除后，导入人员移入本页）。
    # 页面只发请求信号；主窗口接到后经既有 _import_action 触发（任务准入/
    # 忙碌置灰语义不变）。
    import_requested = Signal()

    def __init__(
        self,
        manage_people: ManagePeopleService,
        list_persons: ListPersonsService,
        delete_person,
        list_recognition_runs: ListRecognitionRunsService,
        cluster_results: ClusterResultsService,
        roster_cluster_stats: RosterClusterStatsService,
        delete_run_people=None,
        delete_run_photos=None,
        delete_run_record=None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the page with its Application services.

        Args:
            manage_people: Roster administration use case (add/edit/reorder).
            list_persons: Read-only catalog used to reload after deletions
                (the deletion use case is not on ``ManagePeopleService``).
            delete_person: The existing deletion use case (preview + execute),
                reused so cascade semantics stay in one place.
            list_recognition_runs: Read-only recognition runs for the D-4
                clustering entry's run selector.
            cluster_results: Read-only cluster generations/results for the
                clustering section's availability and results dialog.
            roster_cluster_stats: P4 read-only statistics use case — the
                anchor-generation four numbers and per-person match marks.
            delete_run_people: 运行级名单删除服务（批次删除功能 A）。
            delete_run_photos: 运行级照片删除服务（批次删除功能 B）。
            delete_run_record: 运行级记录清理服务（批次删除功能 C，追加轮 21）。
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._manage_people = manage_people
        self._list_persons = list_persons
        self._delete_person = delete_person
        self._list_recognition_runs = list_recognition_runs
        self._cluster_results = cluster_results
        self._roster_stats = roster_cluster_stats
        self._delete_run_people = delete_run_people
        self._delete_run_photos = delete_run_photos
        self._delete_run_record = delete_run_record
        self._rows: list[Person] = []
        self._batches: tuple[ImportBatchSummary, ...] = ()
        self._batch_filter: UUID | None = None
        self._matched_ids: set[UUID] = set()
        self._match_marks_loaded = False
        self._build_ui()
        self.refresh()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Lay out page header, batch review row, toolbar, table + stats panel."""
        layout = QVBoxLayout(self)

        # 参考图 A1/A2：页头大标题＋副标题（纯视觉容器）；原提示行整段语义
        # 保留（调序说明在批次提示行常驻，副标题后仍保留原 hint 作为补充说明）。
        # 参考图基线（Owner 2026-10-30）：页头加品牌蓝图标，五页同一语言。
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        page_icon = QLabel(self)
        assign_label_icon(page_icon, "people", token("pa-accent-fg"), 22)
        title_block = QWidget(self)
        header_v = QVBoxLayout(title_block)
        header_v.setContentsMargins(0, 0, 0, 0)
        header_v.setSpacing(2)
        title = QLabel(text.PEOPLE_PAGE_TITLE, title_block)
        style_page_title(title)
        subtitle = QLabel(text.PEOPLE_PAGE_SUBTITLE, title_block)
        style_page_subtitle(subtitle)
        header_v.addWidget(title)
        header_v.addWidget(subtitle)
        header_layout.addWidget(page_icon)
        header_layout.addWidget(title_block)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        hint = QLabel(text.PEOPLE_PAGE_HINT, self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        review_row = QHBoxLayout()
        review_row.addWidget(QLabel(text.PEOPLE_PAGE_BATCH_FILTER_LABEL, self))
        self._batch_combo = QComboBox(self)
        self._batch_combo.setMinimumWidth(260)
        self._batch_combo.currentIndexChanged.connect(self._on_batch_selected)
        review_row.addWidget(self._batch_combo)
        self._batch_hint = QLabel(text.PEOPLE_PAGE_BATCH_FILTER_HINT, self)
        review_row.addWidget(self._batch_hint)
        review_row.addStretch()
        layout.addLayout(review_row)

        toolbar_row = QHBoxLayout()
        self._add_button = QPushButton(text.PEOPLE_PAGE_ADD_BUTTON, self)
        self._add_button.clicked.connect(self._on_add_clicked)
        assign_role(self._add_button, ROLE_PRIMARY)
        # 参考图基线（Owner 2026-10-30）：编辑/上移/下移＝浅底描边次级形态。
        self._edit_button = QPushButton(text.PEOPLE_PAGE_EDIT_BUTTON, self)
        self._edit_button.clicked.connect(self._on_edit_selected_clicked)
        assign_role(self._edit_button, ROLE_SECONDARY)
        self._move_up_button = QPushButton(text.PEOPLE_PAGE_MOVE_UP, self)
        self._move_up_button.clicked.connect(lambda: self.move_selected(-1))
        assign_role(self._move_up_button, ROLE_SECONDARY)
        self._move_down_button = QPushButton(text.PEOPLE_PAGE_MOVE_DOWN, self)
        self._move_down_button.clicked.connect(lambda: self.move_selected(1))
        assign_role(self._move_down_button, ROLE_SECONDARY)
        self._delete_button = QPushButton(text.PEOPLE_PAGE_DELETE_BUTTON, self)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        assign_role(self._delete_button, ROLE_DANGER)
        self._delete_batch_button = QPushButton(text.PEOPLE_PAGE_DELETE_BATCH_BUTTON, self)
        self._delete_batch_button.clicked.connect(self._on_delete_batch_clicked)
        assign_role(self._delete_batch_button, ROLE_DANGER)
        self._clear_all_button = QPushButton(text.PEOPLE_PAGE_CLEAR_ALL_BUTTON, self)
        self._clear_all_button.clicked.connect(self._on_clear_all_clicked)
        assign_role(self._clear_all_button, ROLE_DANGER)
        # Fluent 图标（Owner 2026-10-30 裁决：DEC-10=A 按图推翻）——缺失字体
        # 时优雅降级为纯文字；按钮语义/角色赋值零变化。实底按钮上的图标取
        # 其文字色（Owner 2026-10-31：灰/红图标在实底上不可辨，全部对齐）。
        assign_button_icon(self._add_button, "add_friend", token("pa-accent-text"))
        assign_button_icon(self._edit_button, "edit", token("pa-text-secondary"))
        assign_button_icon(self._move_up_button, "up", token("pa-text-secondary"))
        assign_button_icon(self._move_down_button, "down", token("pa-text-secondary"))
        assign_button_icon(self._delete_button, "delete", token("pa-danger-text"))
        # Owner 2026-10-31：「⋯ 更多 ▾」收纳撤除——两个批量危险入口平铺回
        # 工具栏（图标/角色/处理器/确认对话框链零变化），菜单样式破碎问题
        # 随之消失。
        # 名单导入（Owner 2026-10-30 移入本页）：次级形态 + 文档图标；
        # 点击只发请求信号，处理器仍走主窗口的 _import_action（准入/置灰链
        # 零变化）。
        self._import_button = QPushButton(text.ACTION_IMPORT_PEOPLE, self)
        self._import_button.setToolTip(text.PEOPLE_PAGE_IMPORT_TOOLTIP)
        assign_role(self._import_button, ROLE_SECONDARY)
        assign_button_icon(self._import_button, "document", token("pa-text-secondary"))
        self._import_button.clicked.connect(self.import_requested.emit)
        toolbar_row.addWidget(self._add_button)
        toolbar_row.addWidget(self._import_button)
        toolbar_row.addSpacing(_TOOLBAR_GROUP_SPACING)
        toolbar_row.addWidget(self._edit_button)
        toolbar_row.addWidget(self._move_up_button)
        toolbar_row.addWidget(self._move_down_button)
        toolbar_row.addSpacing(_TOOLBAR_GROUP_SPACING)
        toolbar_row.addWidget(self._delete_button)
        toolbar_row.addWidget(self._delete_batch_button)
        toolbar_row.addWidget(self._clear_all_button)
        toolbar_row.addStretch()
        layout.addLayout(toolbar_row)

        body_row = QHBoxLayout()
        self._table = _ReorderableTable(self)
        self._table.setColumnCount(len(_COLUMNS) + _COLUMN_SHIFT)
        self._table.setHorizontalHeaderLabels(["", *list(_COLUMNS)])
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents,
        )
        # Owner 2026-10-31：首列固定宽度（见 _CHECK_COLUMN_WIDTH 注）。
        self._table.horizontalHeader().setSectionResizeMode(
            _COLUMN_CHECK, QHeaderView.ResizeMode.Fixed,
        )
        self._table.setColumnWidth(_COLUMN_CHECK, _CHECK_COLUMN_WIDTH)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setAlternatingRowColors(True)
        self._table.rows_dropped.connect(self._on_rows_dropped)
        self._table.itemSelectionChanged.connect(self._render_action_state)
        self._table.itemChanged.connect(self._on_check_item_changed)
        # 表头全选框（Owner 2026-10-31）：覆盖首列表头区块，点击＝全选/全不选。
        self._header_check = _HeaderSelectAll(self._table.horizontalHeader())
        self._header_check.setToolTip(text.PEOPLE_PAGE_HEADER_CHECK_TOOLTIP)
        self._header_check.toggled_all.connect(self._on_header_select_all)
        self._table.horizontalHeader().sectionResized.connect(
            lambda *_: self._sync_header_check_geometry(),
        )
        body_row.addWidget(self._table, 1)
        body_row.addWidget(self._build_stats_panel(self))
        layout.addLayout(body_row)

        self._empty_label = QLabel(self)
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        self._build_clustering_ui(layout)

    def _build_stats_panel(self, parent: QWidget) -> QFrame:
        """Build the P4 statistics card（锚点、四数、口径说明；P0-4 N4 卡组化）.

        阶段 3（P0-4 ``QFrame#Card`` 构建块，style_card）：外壳由 QGroupBox
        换为统计卡；标题复用既有键（零新键）、不加粗，标签属性名、空态
        语义与 ``maxWidth(280)`` 全部保持（决策项 #2 保守值）。
        空态（空名单 / 无 run / 无代际 / 读取失败）以 ``_stats_empty_label``
        呈现并隐藏四数字区；四数字区隐藏时面板本身仍可见（口径说明常驻）。
        """
        card = QFrame(parent)
        style_card(card)
        stats_layout = QVBoxLayout(card)
        # 同型参照 overview_page.py 步骤卡（任务书 §4）：卡内边距与行距。
        stats_layout.setContentsMargins(12, 10, 12, 10)
        stats_layout.setSpacing(6)
        title = QLabel(text.PEOPLE_PAGE_STATS_TITLE, card)
        style_section_title(title)
        stats_layout.addWidget(title)
        self._stats_anchor_label = QLabel("", card)
        self._stats_anchor_label.setWordWrap(True)
        stats_layout.addWidget(self._stats_anchor_label)
        self._stats_values = QWidget(card)
        values_layout = QVBoxLayout(self._stats_values)
        values_layout.setContentsMargins(0, 0, 0, 0)
        self._stats_photo_label = QLabel("", self._stats_values)
        self._stats_face_label = QLabel("", self._stats_values)
        self._stats_matched_label = QLabel("", self._stats_values)
        self._stats_unmatched_label = QLabel("", self._stats_values)
        for label in (
            self._stats_photo_label, self._stats_face_label,
            self._stats_matched_label, self._stats_unmatched_label,
        ):
            style_stat_value(label)
            values_layout.addWidget(label)
        stats_layout.addWidget(self._stats_values)
        self._stats_empty_label = QLabel("", card)
        self._stats_empty_label.setWordWrap(True)
        stats_layout.addWidget(self._stats_empty_label)
        note = QLabel(text.PEOPLE_PAGE_STATS_CALIBER_NOTE, card)
        note.setWordWrap(True)
        stats_layout.addWidget(note)
        stats_layout.addStretch()
        card.setMaximumWidth(280)
        return card

    # ── Data + rendering ────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload the roster from Application and re-render everything.

        The selection is anchored to the selected *person*, not to a row index:
        every re-render (import, deletion, reorder, the window's own refresh)
        keeps that person selected wherever the roster now puts them. Stage-B
        review follow-up: the highlight used to stay on the old row index,
        which after 「上移/下移」 is somebody else — so the next click moved the
        wrong person.
        """
        selected_id = self._selected_person_id()
        roster = self._manage_people.roster()
        self._rows = list(roster.people)
        self._batches = roster.batches
        self._load_match_marks()
        self._render_batch_combo()
        self._render_rows()
        self._restore_selection(selected_id)
        self.refresh_clustering()
        self._refresh_stats()

    def _load_match_marks(self) -> None:
        """Load the per-person match marks against the anchor generation（P4/D3-A）.

        锚点 = 当前选中识别运行的最新聚类代际；无 run 或无代际时无判定数据
        （``_match_marks_loaded=False``，行内显示「—」）。只读，零写入。
        """
        self._matched_ids = set()
        self._match_marks_loaded = False
        run_id = self.selected_recognition_run_id()
        if run_id is None:
            return
        try:
            self._matched_ids = self._roster_stats.matched_person_ids(run_id)
            self._match_marks_loaded = (
                self._roster_stats.anchor_generation(run_id) is not None
            )
        except Exception as exc:  # noqa: BLE001  UI boundary: degrade, log, no crash
            logger.warning("People page match-mark refresh failed: {}", exc)

    def _refresh_stats(self) -> None:
        """Re-render the statistics panel from the anchor generation（P4）.

        空态优先级（任务书 §1.1 边界）：空名单 → 无识别运行 → 无聚类代际；
        批次筛选不参与（``roster_total`` 取全名单 ``len(self._rows)``）。
        """
        try:
            if not self._rows:
                self._render_stats_empty(text.PEOPLE_PAGE_STATS_EMPTY_NO_ROSTER)
                return
            run_id = self.selected_recognition_run_id()
            if run_id is None:
                self._render_stats_empty(text.PEOPLE_PAGE_STATS_EMPTY_NO_RUN)
                return
            stats = self._roster_stats.stats(run_id, roster_total=len(self._rows))
            if stats is None:
                self._render_stats_empty(text.PEOPLE_PAGE_STATS_EMPTY_NO_GENERATION)
                return
            anchor = (
                stats.anchor_created_at.strftime("%Y-%m-%d %H:%M")
                if stats.anchor_created_at is not None else "—"
            )
            self._stats_anchor_label.setText(
                text.PEOPLE_PAGE_STATS_ANCHOR_LABEL.format(anchor=anchor),
            )
            self._stats_photo_label.setText(
                text.PEOPLE_PAGE_STATS_PHOTO_COUNT.format(count=stats.photo_count),
            )
            self._stats_face_label.setText(
                text.PEOPLE_PAGE_STATS_FACE_COUNT.format(count=stats.face_count),
            )
            self._stats_matched_label.setText(
                text.PEOPLE_PAGE_STATS_MATCHED_COUNT.format(
                    count=stats.matched_person_count,
                ),
            )
            self._stats_unmatched_label.setText(
                text.PEOPLE_PAGE_STATS_UNMATCHED_COUNT.format(
                    count=stats.unmatched_person_count,
                ),
            )
            self._stats_values.setVisible(True)
            self._stats_empty_label.setVisible(False)
        except Exception as exc:  # noqa: BLE001  UI boundary: degrade, log, no crash
            logger.warning("People page stats refresh failed: {}", exc)
            self._render_stats_empty(text.PEOPLE_PAGE_STATS_UNAVAILABLE)

    def _render_stats_empty(self, message: str) -> None:
        """Show the panel's empty-state text and hide the four-number block."""
        self._stats_anchor_label.setText("")
        self._stats_values.setVisible(False)
        self._stats_empty_label.setText(message)
        self._stats_empty_label.setVisible(True)

    def visible_people(self) -> list[Person]:
        """Return the rows the table currently shows (batch filter applied)."""
        if self._batch_filter is None:
            return list(self._rows)
        return [person for person in self._rows if person.source_batch_id == self._batch_filter]

    def _selected_person_id(self) -> UUID | None:
        """Return the id of the person behind the selected row, or ``None``."""
        person = self._selected_person()
        return person.id if person is not None else None

    def _restore_selection(self, person_id: UUID | None) -> None:
        """Re-select ``person_id`` when it is still part of the visible roster."""
        if person_id is None:
            return
        for index, person in enumerate(self.visible_people()):
            if person.id == person_id:
                self._focus_row(index)
                return

    def _focus_row(self, index: int) -> None:
        """Select row ``index``, make it the current row and reveal it.

        Focus is only taken when the table already owned it — a move started
        from the 「上移/下移」 buttons must leave those buttons keyboard-usable.
        """
        if not (0 <= index < self._table.rowCount()):
            return
        item = self._table.item(index, _COLUMN_NAME)
        if item is None:
            return
        self._table.setCurrentCell(index, _COLUMN_NAME)
        self._table.selectRow(index)
        self._table.scrollToItem(item)
        if self._table.hasFocus() or self._table.viewport().hasFocus():
            self._table.setFocus(Qt.FocusReason.OtherFocusReason)

    def _render_batch_combo(self) -> None:
        """Refill the batch selector, preserving the active filter.

        恢复用**值扫描**而非 findData——QVariant 对值相等但非同一实例的
        UUID 匹配不可靠（本文件 _select_person 与 refresh_clustering 同教
        训）；匹配失败（批次已消失）才回落「全部批次」。
        """
        self._batch_combo.blockSignals(True)
        self._batch_combo.clear()
        self._batch_combo.addItem(text.PEOPLE_PAGE_BATCH_ALL, None)
        for summary in self._batches:
            # D10：同名批次无法区分——标签必须带创建时间与状态，否则删除入口
            # 会出现误删风险。
            label = text.import_batch_entry_label(
                summary.batch.file_name,
                summary.batch.created_at,
                summary.batch.status,
                summary.person_count,
            )
            self._batch_combo.addItem(label, summary.batch.id)
        restore = 0
        for index in range(self._batch_combo.count()):
            if self._batch_combo.itemData(index) == self._batch_filter:
                restore = index
                break
        self._batch_combo.setCurrentIndex(restore)
        self._batch_filter = self._batch_combo.currentData()
        self._batch_combo.blockSignals(False)

    def _render_rows(self) -> None:
        """Render the (filtered) roster into the table.

        The rebuild runs with updates frozen and table signals blocked:
        per-row ``setItem``/``setCellWidget`` would otherwise repaint and fire
        selection signals row by row (probe ④ dominated every click at 300+
        rows). Row positions come from an id→position map instead of
        ``list.index`` — an equality scan per row made the loop O(N²).
        """
        batch_names = {summary.batch.id: summary.batch.file_name for summary in self._batches}
        people = self.visible_people()
        positions = {person.id: index + 1 for index, person in enumerate(self._rows)}
        # 阶段 2 方案 a：组/序为按展示顺序（roster_order）派生的只读显示值，
        # 拖拽排序/增删后随本次重渲染自然重算，无需持久化。
        group_ordinals = derive_group_ordinals([person.name for person in people])
        self._table.setUpdatesEnabled(False)
        try:
            with QSignalBlocker(self._table):
                self._table.setRowCount(len(people))
                for row_index, person in enumerate(people):
                    # 复选框选择列（DEC-06 按图推翻）：勾选态镜像行选中态。
                    check_item = QTableWidgetItem()
                    check_item.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsSelectable,
                    )
                    check_item.setToolTip(text.PEOPLE_PAGE_SELECT_TOOLTIP)
                    self._table.setItem(row_index, _COLUMN_CHECK, check_item)
                    values = (
                        str(positions[person.id]),
                        format_group_ordinal(*group_ordinals[row_index]),
                        person.name,
                        person.identity.value if person.identity else "",
                        person.department or "",
                        person.note or "",
                        batch_names.get(person.source_batch_id, text.PEOPLE_PAGE_MANUAL_SOURCE)
                        if person.source_batch_id is not None else text.PEOPLE_PAGE_MANUAL_SOURCE,
                        self._match_status_text(person),
                    )
                    for offset, value in enumerate(values):
                        column = offset + _COLUMN_SHIFT
                        item = QTableWidgetItem(value)
                        # 组/序列的 tooltip 说明派生依据；匹配状态列说明判定口径
                        # （其余列沿用值本身）。
                        if column == _COLUMN_GROUP_ORDINAL:
                            item.setToolTip(text.PEOPLE_PAGE_GROUP_ORDINAL_TOOLTIP)
                        elif column == _COLUMN_MATCH_STATUS:
                            item.setToolTip(text.PEOPLE_PAGE_MATCH_STATUS_TOOLTIP)
                            # 参考图基线：匹配状态按语义着色（已匹配=肯定绿、
                            # 未匹配=提醒琥珀、—=默认次要），文字承载零变化。
                            if value == text.PEOPLE_PAGE_MATCH_STATUS_MARKED:
                                item.setForeground(QBrush(QColor(token("pa-success-fg"))))
                            elif value == text.PEOPLE_PAGE_MATCH_STATUS_UNMATCHED:
                                item.setForeground(QBrush(QColor(token("pa-warning-fg"))))
                        else:
                            item.setToolTip(value)
                        self._table.setItem(row_index, column, item)
                if people:
                    self._empty_label.clear()
                else:
                    self._empty_label.setText(
                        text.PEOPLE_PAGE_EMPTY if not self._rows else text.PEOPLE_PAGE_EMPTY_FILTERED
                    )
                # Owner 裁决（2026-10-28）：批次视图可调序、全部批次只读——
                # 提示常驻并按视图状态切换文案。
                if self._batch_filter is not None:
                    self._batch_hint.setText(text.PEOPLE_PAGE_BATCH_FILTER_HINT)
                else:
                    self._batch_hint.setText(text.PEOPLE_PAGE_BATCH_READONLY_HINT)
                self._batch_hint.setVisible(True)
        finally:
            self._table.setUpdatesEnabled(True)
        self._render_action_state()
        self._sync_header_check_geometry()

    def _match_status_text(self, person: Person) -> str:
        """P4/D3-A：人员行的匹配状态显示值。

        无锚点代际（无 run / 无代际）→「—」（无判定数据）；有锚点 → 该人员
        在锚点代际无 active 决策即「未匹配」（批次筛选不影响本判定）。
        """
        if not self._match_marks_loaded:
            return text.PEOPLE_PAGE_MATCH_STATUS_NONE
        if person.id is not None and person.id in self._matched_ids:
            return text.PEOPLE_PAGE_MATCH_STATUS_MARKED
        return text.PEOPLE_PAGE_MATCH_STATUS_UNMATCHED

    def _render_action_state(self) -> None:
        """Re-render button/drag availability from the current selection.

        P11（D5-A）：上移/下移/编辑仅在**恰选中 1 行**时可用；「删除所选」
        对 1..n 行可用；拖拽重排与多选互斥——选中数 > 1 时关闭。
        Owner 2026-10-31 推翻 2026-10-28 只读裁决：全部批次视图同样可调序
        （拖拽与移动按钮随选区启用，语义＝全库名单顺序）。
        """
        rows = self._selected_row_indices()
        single = len(rows) == 1
        index = rows[0] if single else -1
        last_index = self._table.rowCount() - 1
        reorderable = single
        self._move_up_button.setEnabled(reorderable and index > 0)
        self._move_down_button.setEnabled(reorderable and 0 <= index < last_index)
        self._edit_button.setEnabled(single and self._selected_person() is not None)
        self._delete_button.setEnabled(bool(rows))
        # Owner 2026-10-31：两个批量危险入口平铺后按各自可用性置灰（原更多
        # 菜单的门＝有批次或选区任一）。
        self._delete_batch_button.setEnabled(bool(self._batches))
        self._clear_all_button.setEnabled(bool(self._rows))
        self._table.setDragEnabled(len(rows) <= 1)
        self._sync_check_marks(rows)
        self._sync_header_check_state()

    def _sync_check_marks(self, selected_rows: list[int]) -> None:
        """镜像行选中态到复选框列（blockSignals 防回环；DEC-06 按图推翻）."""
        with QSignalBlocker(self._table):
            for row_index in range(self._table.rowCount()):
                item = self._table.item(row_index, _COLUMN_CHECK)
                if item is None:
                    continue
                item.setCheckState(
                    Qt.CheckState.Checked if row_index in selected_rows
                    else Qt.CheckState.Unchecked,
                )

    # ── 表头全选框（Owner 2026-10-31）────────────────────────────────────

    def _on_header_select_all(self, select: bool) -> None:
        """表头全选框点击：全选/清空选择（选择模型仍是唯一语义源）。"""
        if select:
            self._table.selectAll()
        else:
            self._table.clearSelection()

    def _sync_header_check_state(self) -> None:
        """镜像选区到表头全选框（全选=✓、部分=半态、无=空；零行=禁用）。"""
        total = self._table.rowCount()
        with QSignalBlocker(self._header_check):
            self._header_check.setEnabled(total > 0)
            if total == 0:
                self._header_check.setCheckState(Qt.CheckState.Unchecked)
                return
            selected = len(self._selected_row_indices())
            if selected == 0:
                state = Qt.CheckState.Unchecked
            elif selected == total:
                state = Qt.CheckState.Checked
            else:
                state = Qt.CheckState.PartiallyChecked
            self._header_check.setCheckState(state)

    def _sync_header_check_geometry(self) -> None:
        """把全选框摆进首列表头区块（首列固定宽后几何恒定）。"""
        header = self._table.horizontalHeader()
        width = header.sectionSize(_COLUMN_CHECK)
        if width <= 0:
            self._header_check.hide()
            return
        self._header_check.setGeometry(
            _HEADER_CHECK_MARGIN,
            0,
            max(16, width - _HEADER_CHECK_MARGIN),
            max(16, header.height()),
        )
        self._header_check.show()

    def _on_check_item_changed(self, item: QTableWidgetItem) -> None:
        """复选框勾选 → 行选中/取消（与 ExtendedSelection 单一语义源并轨）."""
        if item.column() != _COLUMN_CHECK:
            return
        row_index = item.row()
        checked = item.checkState() == Qt.CheckState.Checked
        is_selected = row_index in self._selected_row_indices()
        if checked and not is_selected:
            self._table.selectRow(row_index)
        elif not checked and is_selected:
            from PySide6.QtCore import QItemSelectionModel

            self._table.selectionModel().select(
                self._table.model().index(row_index, 0),
                QItemSelectionModel.SelectionFlag.Deselect
                | QItemSelectionModel.SelectionFlag.Rows,
            )

    def _selected_row_indices(self) -> list[int]:
        """Return every selected table row (ascending, possibly empty)."""
        model = self._table.selectionModel()
        rows = model.selectedRows() if model else []
        return sorted(index.row() for index in rows)

    def _selected_row_index(self) -> int:
        """Return the first selected table row, or -1 when nothing is selected."""
        rows = self._selected_row_indices()
        return rows[0] if rows else -1

    def _selected_people(self) -> list[Person]:
        """Return the people behind every selected row (P11 multi-select)."""
        people = self.visible_people()
        return [
            people[index] for index in self._selected_row_indices()
            if 0 <= index < len(people)
        ]

    def _selected_person(self) -> Person | None:
        """Return the person behind the selected row, or None."""
        index = self._selected_row_index()
        people = self.visible_people()
        return people[index] if 0 <= index < len(people) else None

    # ── Batch review ────────────────────────────────────────────────────

    def _on_batch_selected(self, _index: int) -> None:
        """Switch the batch view and re-render（批次视图可调序；全部批次只读）."""
        self._batch_filter = self._batch_combo.currentData()
        self._render_rows()

    # ── Add / edit / delete ─────────────────────────────────────────────

    def _on_add_clicked(self) -> None:
        """Collect a new person and append them to the roster."""
        dialog = PersonEditDialog(parent=self)
        if not dialog.exec():
            return
        values = dialog.values()
        try:
            person = self._manage_people.add_person(AddPersonCommand(**values))
        except ValidationError as exc:
            self._warn(text.PEOPLE_PAGE_SAVE_FAILED.format(detail=exc))
            return
        logger.info("People page added person {}", person.id)
        self._after_mutation(text.PEOPLE_PAGE_ADDED.format(name=person.name))

    def _on_edit_selected_clicked(self) -> None:
        """编辑选中行的人员资料（工具栏入口；§4.1 去行内操作列）。"""
        person = self._selected_person()
        if person is not None:
            self._on_edit_clicked(person)

    def _on_edit_clicked(self, person: Person) -> None:
        """Edit one person's fields through the form dialog."""
        dialog = PersonEditDialog(person=person, parent=self)
        if not dialog.exec():
            return
        values = dialog.values()
        try:
            updated = self._manage_people.edit_person(
                EditPersonCommand(person_id=person.id, **values),  # type: ignore[arg-type]
            )
        except ValidationError as exc:
            self._warn(text.PEOPLE_PAGE_SAVE_FAILED.format(detail=exc))
            return
        logger.info("People page edited person {}", updated.id)
        self._after_mutation(text.PEOPLE_PAGE_EDITED.format(name=updated.name))

    def _on_delete_clicked(self) -> None:
        """Delete the selected people through the danger-confirm dialogs.

        P11（D5-A 最小版）：单选等价既有单人删除流（下拉确认对话框）；
        多选走批量预览 + 确认对话框 + 事务执行（``MultiPersonDeletionDialog``，
        复用 ``DeletePersonService.preview/execute`` 的级联语义）。
        """
        people = self._selected_people()
        if not people:
            return
        if len(people) == 1:
            self._delete_single_person(people[0])
            return
        dialog = MultiPersonDeletionDialog(
            [(person.id, person.name) for person in people],
            self._delete_person, parent=self,
        )
        if not dialog.exec():
            return
        logger.info("People page deleted {} selected people", len(people))
        self._after_mutation(dialog.last_message())

    def _delete_single_person(self, person: Person) -> None:
        """既有单人删除流：确认对话框（预选该人员）→ 事务执行。"""
        dialog = PersonDeletionDialog(
            self._list_persons, self._delete_person, parent=self, preselect_id=person.id,
        )
        if not dialog.exec():
            return
        person_id = dialog.selected_person_id()
        person_name = dialog.selected_person_name()
        if person_id is None:
            return
        try:
            result: PersonDeletionResult = self._delete_person.execute(
                DeletePersonCommand(person_ids=(person_id,)),
            )
        except Exception as exc:  # noqa: BLE001  # UI boundary: show, log the detail
            logger.exception("People page deletion failed")
            self._warn(
                text.PEOPLE_PAGE_DELETE_FAILED.format(detail=exc),
                text.PEOPLE_PAGE_DELETE_FAILED_TITLE,
            )
            return
        logger.info(
            "People page deleted person {} (embedded={} orphaned={})",
            person_id, result.embedding_cascade, result.recognition_orphaned,
        )
        self._after_mutation(text.PEOPLE_PAGE_DELETED.format(name=person_name))

    def _on_delete_batch_clicked(self) -> None:
        """按导入批次删除人员（界面优化 §4.3；预览+二次确认+可选清理）。"""
        if not self._batches:
            self._warn(text.PEOPLE_PAGE_EMPTY)
            return
        dialog = BatchPersonDeletionDialog(
            self._manage_people, self._delete_person, parent=self,
        )
        if not dialog.exec():
            return
        logger.info("People page deleted one import batch's people")
        self._after_mutation(dialog.last_message())

    def _on_clear_all_clicked(self) -> None:
        """清空所有人员（界面优化 §4.3；显式知悉勾选 + 单事务执行）。"""
        dialog = ClearAllPeopleDialog(
            self._manage_people, self._delete_person, parent=self,
        )
        if not dialog.exec():
            return
        logger.info("People page cleared all people")
        self._after_mutation(dialog.last_message())

    # ── Reordering ──────────────────────────────────────────────────────

    def move_selected(self, offset: int) -> None:
        """Move the selected row by ``offset`` places and persist the roster.

        The person stays selected at their new position (``refresh`` re-anchors
        the selection to the person), so pressing 「上移/下移」 again keeps moving
        the same person instead of whoever the old row index now holds.
        P11：仅恰选中 1 行时执行（多选禁用移动按钮；此处为第二道门）。
        Owner 2026-10-31 推翻 2026-10-28 只读裁决：全部批次视图同样可调序
        （调整的是全库名单顺序）；批次视图仍为批次内槽位置换。
        """
        if len(self._selected_row_indices()) != 1:
            return
        index = self._selected_row_index()
        if index < 0:
            return
        self.move_row(index, index + offset)

    def move_row(self, source_index: int, target_index: int) -> None:
        """Reorder the visible rows and persist the resulting roster order.

        批次筛选视图＝批次内槽位置换（Owner 裁决 2026-10-28：本批次成员按
        新序填回它们占有的全局名次槽位，其他批次人员的名次与相对位置完全
        不变）；全部批次视图（Owner 2026-10-31 推翻只读裁决）＝可见列表即
        全名单，置换结果本身就是全库名单顺序。
        """
        people = self.visible_people()
        if not (0 <= source_index < len(people)) or not (0 <= target_index < len(people)):
            return
        if source_index == target_index:
            return
        person = people.pop(source_index)
        people.insert(target_index, person)
        if self._batch_filter is None:
            self._persist_order(people)
        else:
            self._persist_batch_order(people)

    def _on_rows_dropped(self, source_row: int, target_row: int) -> None:
        """Handle a table drag: same semantics as the move buttons."""
        self.move_row(source_row, target_row)

    def _persist_batch_order(self, ordered_subset: list[Person]) -> None:
        """Batch-view slot permutation → full roster order → existing transaction.

        取全名单中本批次成员当前占有的名次槽位，把重排后的成员按序填回；
        其余人员原位保留。构造出的全量 ``ordered_ids`` 交给既有
        ``reorder_people`` 单事务写入（服务层零改动）。
        """
        subset_ids = {person.id for person in ordered_subset}
        merged: list[Person] = []
        cursor = 0
        for person in self._rows:
            if person.id is not None and person.id in subset_ids:
                merged.append(ordered_subset[cursor])
                cursor += 1
            else:
                merged.append(person)
        self._persist_order(merged)

    def _persist_order(self, ordered_people: list[Person]) -> None:
        """Write the full roster order and refresh dependent views."""
        try:
            updated = self._manage_people.reorder_people(
                ReorderPeopleCommand(ordered_ids=tuple(
                    person.id for person in ordered_people  # type: ignore[misc]
                )),
            )
        except ValidationError as exc:
            self._warn(text.PEOPLE_PAGE_SAVE_FAILED.format(detail=exc))
            self.refresh()
            return
        logger.info("People page reordered {} people", updated)
        self._after_mutation(
            text.PEOPLE_PAGE_REORDERED.format(count=updated)
            + " " + text.PEOPLE_PAGE_REORDER_HINT,
            structure_changed=False,
        )

    # ── D-4 聚类入口 ───────────────────────────────────────────────────

    def _build_clustering_ui(self, layout: QVBoxLayout) -> None:
        """Build the clustering group: run selector, run + results buttons.

        页面只发请求信号——运行走主窗口的 TaskCoordinator 管线（互斥/取消/
        状态栏），结果对话框由主窗口打开（父窗口与缩略图通道注入）。
        """
        # E1（taskbook-3 §3 [V]）：QGroupBox → Card 容器化（纯视觉；全部
        # 按钮与 D1-A 两个危险入口原位保留）。
        group = QFrame(self)
        style_card(group)
        group_layout = QVBoxLayout(group)
        group_title = QLabel(text.CLUSTER_PAGE_GROUP, group)
        style_section_title(group_title)
        group_layout.addWidget(group_title)
        row = QHBoxLayout()
        row.addWidget(QLabel(text.CLUSTER_PAGE_RUN_LABEL, group))
        self._cluster_run_combo = QComboBox(group)
        self._cluster_run_combo.setMinimumWidth(280)
        # P4：切换识别运行 → 锚点变化 → 行内匹配标记与统计面板联动重渲染
        # （刷新期间 refill 用 blockSignals 包裹，不会触发本槽）。
        self._cluster_run_combo.currentIndexChanged.connect(self._on_cluster_run_changed)
        row.addWidget(self._cluster_run_combo)
        self._cluster_run_button = QPushButton(text.CLUSTER_PAGE_RUN_BUTTON, group)
        self._cluster_run_button.clicked.connect(self.cluster_run_requested.emit)
        assign_role(self._cluster_run_button, ROLE_PRIMARY)
        assign_button_icon(self._cluster_run_button, "play", token("pa-accent-text"))
        row.addWidget(self._cluster_run_button)
        self._cluster_results_button = QPushButton(text.CLUSTER_PAGE_RESULTS_BUTTON, group)
        self._cluster_results_button.clicked.connect(self.cluster_results_requested.emit)
        assign_role(self._cluster_results_button, ROLE_SECONDARY)
        assign_button_icon(self._cluster_results_button, "view", token("pa-text-secondary"))
        row.addWidget(self._cluster_results_button)
        # 批次级删除（识别运行锚点）：两个入口与运行选择器同区——"批次"在这里
        # 指**识别运行**（照片只挂在运行下），与顶部「来源批次」（名单导入）
        # 是两套不同实体。
        self._delete_run_people_button = QPushButton(
            text.PEOPLE_PAGE_DELETE_RUN_PEOPLE_BUTTON, group,
        )
        self._delete_run_people_button.clicked.connect(
            self._on_delete_run_people_clicked,
        )
        assign_role(self._delete_run_people_button, ROLE_DANGER)
        row.addWidget(self._delete_run_people_button)
        self._delete_run_photos_button = QPushButton(
            text.PEOPLE_PAGE_DELETE_RUN_PHOTOS_BUTTON, group,
        )
        self._delete_run_photos_button.clicked.connect(
            self._on_delete_run_photos_clicked,
        )
        assign_role(self._delete_run_photos_button, ROLE_DANGER)
        row.addWidget(self._delete_run_photos_button)
        # 批次删除功能 C（追加轮 21）：运行记录清理——A/B 之后的第三级终口。
        self._delete_run_record_button = QPushButton(
            text.PEOPLE_PAGE_DELETE_RUN_RECORD_BUTTON, group,
        )
        self._delete_run_record_button.clicked.connect(
            self._on_delete_run_record_clicked,
        )
        assign_role(self._delete_run_record_button, ROLE_DANGER)
        row.addWidget(self._delete_run_record_button)
        row.addStretch()
        group_layout.addLayout(row)
        hint = QLabel(text.CLUSTER_PAGE_HINT, group)
        hint.setWordWrap(True)
        group_layout.addWidget(hint)
        self._cluster_hint = QLabel("", group)
        self._cluster_hint.setWordWrap(True)
        group_layout.addWidget(self._cluster_hint)
        layout.addWidget(group)

    def refresh_clustering(self) -> None:
        """Reload the recognition-run selector and clustering availability.

        选择按 run id 锚定（刷新后保持合理当前选择）；无运行时按钮禁用并
        给出明确空态文案。
        """
        selected = self.selected_recognition_run_id()
        runs = self._list_recognition_runs.execute()
        self._cluster_run_combo.blockSignals(True)
        self._cluster_run_combo.clear()
        for run in runs:
            self._cluster_run_combo.addItem(
                text.CLUSTER_PAGE_RUN_ENTRY.format(
                    created_at=run.created_at.strftime("%Y-%m-%d %H:%M")
                    if run.created_at is not None else "—",
                    status=text.cluster_run_status_label(run.status),
                    faces=run.face_count,
                ),
                run.id,
            )
        self._cluster_run_combo.blockSignals(False)
        if selected is not None:
            # findData 对值相等但非同一实例的 UUID 不可靠（QVariant 比较），
            # 这里用值扫描保持刷新后的当前选择。
            for index in range(self._cluster_run_combo.count()):
                if self._cluster_run_combo.itemData(index) == selected:
                    self._cluster_run_combo.setCurrentIndex(index)
                    break
        self._render_cluster_availability()

    def _render_cluster_availability(self) -> None:
        """Enable the run button on a selected run; results need a generation."""
        run_id = self.selected_recognition_run_id()
        has_results = False
        if run_id is not None:
            has_results = bool(self._cluster_results.list_cluster_runs(run_id))
        self._cluster_run_button.setEnabled(run_id is not None)
        self._cluster_results_button.setEnabled(has_results)
        # 批次级删除入口：无选中运行 / 服务未注入时禁用（不静默无响应）。
        self._delete_run_people_button.setEnabled(
            run_id is not None and self._delete_run_people is not None
        )
        self._delete_run_photos_button.setEnabled(
            run_id is not None and self._delete_run_photos is not None
        )
        self._delete_run_record_button.setEnabled(
            run_id is not None and self._delete_run_record is not None
        )
        self._cluster_hint.setText(
            "" if run_id is not None else text.CLUSTER_PAGE_NO_RUNS
        )

    def selected_recognition_run_id(self) -> UUID | None:
        """Return the recognition run id behind the selector, or ``None``."""
        data = self._cluster_run_combo.currentData()
        return data if isinstance(data, UUID) else None

    def _selected_run_label(self) -> str:
        """Return the selected run's readable label（对话框标题与披露用）."""
        index = self._cluster_run_combo.currentIndex()
        if index < 0:
            return "—"
        return self._cluster_run_combo.itemText(index)

    def _on_delete_run_people_clicked(self) -> None:
        """删除该识别运行的名单及记录（批次删除功能 A）。"""
        run_id = self.selected_recognition_run_id()
        if run_id is None or self._delete_run_people is None:
            return
        dialog = RunPeopleDeletionDialog(
            self._delete_run_people, run_id, self._selected_run_label(), parent=self,
        )
        if not dialog.exec():
            return
        logger.info("People page deleted one recognition run's people")
        self._after_mutation(dialog.last_message())

    def _on_delete_run_photos_clicked(self) -> None:
        """删除该识别运行的照片及记录（批次删除功能 B）。"""
        run_id = self.selected_recognition_run_id()
        if run_id is None or self._delete_run_photos is None:
            return
        dialog = RunPhotosDeletionDialog(
            self._delete_run_photos, run_id, self._selected_run_label(), parent=self,
        )
        if not dialog.exec():
            return
        logger.info("People page deleted one recognition run's photos")
        self._after_mutation(dialog.last_message())

    def _on_delete_run_record_clicked(self) -> None:
        """删除该识别运行的残留记录（批次删除功能 C，追加轮 21）。"""
        run_id = self.selected_recognition_run_id()
        if run_id is None or self._delete_run_record is None:
            return
        dialog = RunRecordDeletionDialog(
            self._delete_run_record, run_id, self._selected_run_label(), parent=self,
        )
        if not dialog.exec():
            return
        logger.info("People page deleted one recognition run's residual record")
        self._after_mutation(dialog.last_message())

    def _on_cluster_run_changed(self, _index: int) -> None:
        """P4：识别运行选择变化 → 锚点变化 → 标记/统计联动（批次筛选不联动）。"""
        self._load_match_marks()
        self._render_rows()
        self._render_cluster_availability()
        self._refresh_stats()

    # ── Shared helpers ──────────────────────────────────────────────────

    def _after_mutation(self, message: str, *, structure_changed: bool = True) -> None:
        """Reload the page, then let the window refresh dependent surfaces.

        ``structure_changed=False`` marks a pure reorder: the page has already
        re-rendered here, and the window skips its filter-axis / snapshot
        cascade — its extra ``refresh()`` used to double every table rebuild.
        """
        self.refresh()
        self._status_message = message
        self.people_changed.emit(structure_changed)

    def last_message(self) -> str:
        """Return the message of the last successful mutation (window status)."""
        return getattr(self, "_status_message", "")

    def _warn(self, message: str, title: str = text.PEOPLE_PAGE_SAVE_FAILED_TITLE) -> None:
        """Show a non-destructive warning for a rejected operation."""
        QMessageBox.warning(self, title, message)
