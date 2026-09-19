"""Archive plan preview dialog — 落裁决 #3 plan 预览 + execute 确认.

调 ArchiveController.preview() 得 ArchivePlan，展示按 person 聚合的预览，
用户确认 conflict_strategy / dry_run 后调 execute() 走 Worker。

Batch 6（安全表达）：预览首行声明本次范围（全部已通过 / 已选 N 张），
逐条列出前若干"源 → 目标"样本，冲突策略附带后果解释，试运行默认勾选
（owner 决策：首次归档默认不写盘），确认按钮随模式显示"执行试运行"或
"开始归档"——正式写入永远不是通用 OK。
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.dtos import ArchivePlan
from photo_archiver.presentation.ui_text import (
    ARCHIVE_CONFLICT_HINTS,
    ARCHIVE_CONFLICT_LABELS,
    ARCHIVE_DRY_RUN_BUTTON,
    ARCHIVE_DRY_RUN_CHECK,
    ARCHIVE_EXECUTE_BUTTON,
    ARCHIVE_PREVIEW_CONFLICT_LABEL,
    ARCHIVE_PREVIEW_PERSON_PHOTOS,
    ARCHIVE_PREVIEW_PLANNED,
    ARCHIVE_PREVIEW_ROOT,
    ARCHIVE_PREVIEW_SKIPPED,
    ARCHIVE_PREVIEW_TITLE,
    ARCHIVE_SAMPLE_HEADER,
    ARCHIVE_SAMPLE_ROW,
    ARCHIVE_SAMPLE_TRUNCATED,
    ARCHIVE_SCOPE_ALL,
    ARCHIVE_SCOPE_LABEL,
    ARCHIVE_SCOPE_SELECTED,
)
from photo_archiver.presentation.visual_style import (
    ROLE_DANGER,
    ROLE_PRIMARY,
    assign_role,
)

# How many source→target samples to render inline; the plan itself stays the
# complete truth (the executor reports every item's outcome).
_SAMPLE_LIMIT = 8


class ArchivePreviewDialog(QDialog):
    """Show an ArchivePlan preview and collect conflict-strategy + dry-run confirmation."""

    def __init__(
        self,
        plan: ArchivePlan,
        archive_root: Path,
        parent: QWidget | None = None,
        selected_count: int = 0,
    ) -> None:
        """Initialize the dialog with the plan and the configured archive root.

        Args:
            plan: ArchivePlan from ArchiveController.preview().
            archive_root: Root path shown in the dialog header for context.
            selected_count: Number of user-selected photos this plan covers;
                ``0`` means the plan covers all approved photos (scope honesty
                is a Batch 6 requirement — the user must know what will run).
        """
        super().__init__(parent)
        self.setWindowTitle(ARCHIVE_PREVIEW_TITLE)
        self.setMinimumWidth(520)
        self._plan = plan
        self._archive_root = archive_root
        self._selected_count = selected_count
        self._build_ui()

    def _build_ui(self) -> None:
        """Lay out scope, plan summary, samples, strategy, dry-run and buttons."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        scope_text = (
            ARCHIVE_SCOPE_SELECTED.format(count=self._selected_count)
            if self._selected_count
            else ARCHIVE_SCOPE_ALL
        )
        form.addRow(ARCHIVE_SCOPE_LABEL, QLabel(scope_text, self))
        form.addRow(ARCHIVE_PREVIEW_ROOT, QLabel(str(self._archive_root), self))
        form.addRow(ARCHIVE_PREVIEW_PLANNED, QLabel(str(self._plan.planned_count), self))
        form.addRow(ARCHIVE_PREVIEW_SKIPPED, QLabel(str(self._plan.skipped_count), self))

        # Per-person breakdown so the user can sanity-check the plan shape.
        by_person: dict[str, int] = {}
        for item in self._plan.items:
            by_person[item.person_name] = by_person.get(item.person_name, 0) + 1
        for person_name, count in by_person.items():
            form.addRow(
                f"  {person_name}:",
                QLabel(ARCHIVE_PREVIEW_PERSON_PHOTOS.format(count=count), self),
            )

        # Source → destination samples (Batch 6): a bounded, side-effect-free
        # peek at where files will land. ArchivePath.resolve() is pure.
        layout.addWidget(QLabel(ARCHIVE_SAMPLE_HEADER, self))
        self._sample_list = QListWidget(self)
        for item in self._plan.items[:_SAMPLE_LIMIT]:
            self._sample_list.addItem(ARCHIVE_SAMPLE_ROW.format(
                source=item.source_path.name,
                target=item.target_path.resolve(),
            ))
        self._sample_list.setSelectionMode(
            QListWidget.SelectionMode.NoSelection,
        )
        self._sample_list.setMaximumHeight(120)
        self._sample_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self._sample_list)
        if self._plan.planned_count > _SAMPLE_LIMIT:
            note = QLabel(ARCHIVE_SAMPLE_TRUNCATED.format(
                shown=_SAMPLE_LIMIT, total=self._plan.planned_count,
            ), self)
            layout.addWidget(note)

        self._strategy_combo = QComboBox(self)
        # 显示中文标签，userData 携带契约值（skip/overwrite/rename，镜像
        # AppSettings / CLI；冲突策略值是执行器契约，不随 UI 语言变化）。
        for label, value in ARCHIVE_CONFLICT_LABELS:
            self._strategy_combo.addItem(label, value)
        form.addRow(ARCHIVE_PREVIEW_CONFLICT_LABEL, self._strategy_combo)

        # Consequence hint (Batch 6): the strategy's effect stated in words.
        self._strategy_hint = QLabel(self._current_strategy_hint(), self)
        self._strategy_hint.setWordWrap(True)
        layout.addWidget(self._strategy_hint)
        self._strategy_combo.currentIndexChanged.connect(
            lambda _: self._strategy_hint.setText(self._current_strategy_hint()),
        )

        # Owner decision (Batch 0 / Batch 6): dry-run is the default; the real
        # write requires unchecking it and pressing the explicit "开始归档".
        self._dry_run_check = QCheckBox(ARCHIVE_DRY_RUN_CHECK, self)
        self._dry_run_check.setChecked(True)
        self._dry_run_check.toggled.connect(self._update_accept_label)
        layout.addWidget(self._dry_run_check)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self,  # type: ignore[attr-defined]
        )
        self._accept_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)
        self._update_accept_label()

    def _current_strategy_hint(self) -> str:
        """Return the consequence explanation for the selected strategy."""
        data = self._strategy_combo.currentData()
        return ARCHIVE_CONFLICT_HINTS.get(
            str(data) if data is not None else "",
            "",
        )

    def _update_accept_label(self) -> None:
        """Label and color the accept button with what it will actually start.

        Dry-run (the default) keeps the safe "执行试运行" as a primary button
        and the default; once real writing is armed, the accept button reads
        the explicit "开始归档", switches to the danger tone and default
        focus moves to Cancel — a stray Enter must never launch a disk write.
        """
        dry_run = self._dry_run_check.isChecked()
        self._accept_button.setText(
            ARCHIVE_DRY_RUN_BUTTON if dry_run else ARCHIVE_EXECUTE_BUTTON,
        )
        assign_role(
            self._accept_button,
            ROLE_PRIMARY if dry_run else ROLE_DANGER,
        )
        self._accept_button.setDefault(dry_run)
        cancel = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setDefault(not dry_run)

    @property
    def conflict_strategy(self) -> str:
        """Return the selected conflict strategy (the contract value, not the label)."""
        data = self._strategy_combo.currentData()
        return str(data) if data is not None else self._strategy_combo.currentText()

    @property
    def dry_run(self) -> bool:
        """Return whether dry-run was checked."""
        return self._dry_run_check.isChecked()

    # review m-4 fix: removed planned_count and person_ids properties —
    # the caller already holds the plan (for planned_count) and must pass
    # the SAME person_ids to execute() that it passed to preview() (for
    # symmetry); the dialog must not silently substitute a subset.
