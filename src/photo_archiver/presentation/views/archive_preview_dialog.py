"""Archive plan preview dialog — 落裁决 #3 plan 预览 + execute 确认.

调 ArchiveController.preview() 得 ArchivePlan，展示按 person 聚合的预览，
用户确认 conflict_strategy / dry_run 后调 execute() 走 Worker。
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QWidget,
)

from photo_archiver.application.dtos import ArchivePlan

# Conflict strategy choices mirror AppSettings / CLI; the combo box exposes
# them in user-friendly order with descriptions trailing for clarity.
_CONFLICT_CHOICES = ("skip", "overwrite", "rename")


class ArchivePreviewDialog(QDialog):
    """Show an ArchivePlan preview and collect conflict-strategy + dry-run confirmation."""

    def __init__(
        self,
        plan: ArchivePlan,
        archive_root: Path,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the dialog with the plan and the configured archive root.

        Args:
            plan: ArchivePlan from ArchiveController.preview().
            archive_root: Root path shown in the dialog header for context.
        """
        super().__init__(parent)
        self.setWindowTitle("Archive Plan Preview")
        self._plan = plan
        self._archive_root = archive_root
        self._build_ui()

    def _build_ui(self) -> None:
        """Lay out the plan summary, strategy combo, dry-run checkbox, and buttons."""
        layout = QFormLayout(self)

        layout.addRow("Archive root:", QLabel(str(self._archive_root)))
        layout.addRow("Planned items:", QLabel(str(self._plan.planned_count)))
        layout.addRow("Skipped:", QLabel(str(self._plan.skipped_count)))

        # Per-person breakdown so the user can sanity-check the plan shape.
        by_person: dict[str, int] = {}
        for item in self._plan.items:
            by_person[item.person_name] = by_person.get(item.person_name, 0) + 1
        for person_name, count in by_person.items():
            layout.addRow(f"  {person_name}:", QLabel(f"{count} photos"))

        self._strategy_combo = QComboBox(self)
        for choice in _CONFLICT_CHOICES:
            self._strategy_combo.addItem(choice)
        layout.addRow("Conflict strategy:", self._strategy_combo)

        self._dry_run_check = QCheckBox("Dry-run (preview only, no files written)", self)
        layout.addRow(self._dry_run_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok, self)  # type: ignore[attr-defined]
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @property
    def conflict_strategy(self) -> str:
        """Return the selected conflict strategy."""
        return self._strategy_combo.currentText()

    @property
    def dry_run(self) -> bool:
        """Return whether dry-run was checked."""
        return self._dry_run_check.isChecked()

    # review m-4 fix: removed planned_count and person_ids properties —
    # the caller already holds the plan (for planned_count) and must pass
    # the SAME person_ids to execute() that it passed to preview() (for
    # symmetry); the dialog must not silently substitute a subset.
