"""Archive plan preview dialog — 落裁决 #3 plan 预览 + execute 确认.

调 ArchiveController.preview() 得 ArchivePlan，展示按 person 聚合的预览，
用户确认 conflict_strategy / dry_run 后调 execute() 走 Worker。
"""

from pathlib import Path
from uuid import UUID

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QComboBox,
)

from photo_archiver.application.dtos import ArchivePlan
from photo_archiver.domain import ArchiveStatus

# Conflict strategy choices mirror AppSettings / CLI; the combo box exposes
# them in user-friendly order with descriptions trailing for clarity.
_CONFLICT_CHOICES = ("skip", "overwrite", "rename")


class ArchivePreviewDialog(QDialog):
    """Show an ArchivePlan preview and collect conflict-strategy + dry-run confirmation."""

    def __init__(
        self,
        plan: ArchivePlan,
        archive_root: Path,
        parent=None,
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

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok, self)
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

    @property
    def person_ids(self) -> tuple[UUID, ...]:
        """Return the person_ids covered by the previewed plan, for execute() reuse.

        Extracted from the plan items so the caller doesn't have to track which
        persons were previewed — the dialog hands back the exact set the plan
        covered, keeping the UI's execute call symmetric with the preview.
        """
        seen: set[UUID] = set()
        result: list[UUID] = []
        for item in self._plan.items:
            if item.person_id not in seen:
                seen.add(item.person_id)
                result.append(item.person_id)
        return tuple(result)

    @property
    def planned_count(self) -> int:
        """Return the plan's planned_count for the caller's sanity assertion."""
        return self._plan.planned_count

    # Sentinel exported for tests that want to assert status enums flow through
    # without importing the domain directly.
    ARCHIVED_STATUS = ArchiveStatus.ARCHIVED
