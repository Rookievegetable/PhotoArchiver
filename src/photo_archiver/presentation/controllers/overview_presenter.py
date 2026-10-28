"""Derive the five-step overview checklist and the single primary CTA.

Batch 3 (UI/UX 收口) information-architecture presenter: pure presentation
logic that translates the cached :class:`WorkspaceStatus` snapshot (Batch 2)
into a five-step archive checklist plus one primary call-to-action. No Qt
widgets here — the view (:mod:`overview_page`) only renders the resulting
model, and workspace facts are never queried from a widget (DEP-003/004).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from photo_archiver.presentation import ui_text as text

PrimaryActionId = Literal[
    "import", "scan", "review", "archive", "settings", "model",
]


class _WorkspaceSnapshot(Protocol):
    """Minimal read-side port the presenter needs from WorkspaceController."""

    @property
    def status(self):  # noqa: ANN202 - Protocol returns WorkspaceStatus | None
        """Return the cached workspace snapshot (or None before first refresh)."""
        ...

    def feature_guidance(self):  # noqa: ANN202
        """Return feature-extraction availability + first unmet prerequisite."""
        ...

    def archive_guidance(self):  # noqa: ANN202
        """Return archive availability + first unmet prerequisite."""
        ...

    def review_guidance(self):  # noqa: ANN202
        """Return the review-queue guidance (empty state or pending count)."""
        ...


@dataclass(frozen=True, slots=True)
class OverviewStep:
    """One checklist row: step label, completion flag and the explanation."""

    label: str
    done: bool
    detail: str


@dataclass(frozen=True, slots=True)
class OverviewModel:
    """Render-ready overview: five steps plus at most one primary action."""

    steps: tuple[OverviewStep, ...]
    primary: PrimaryActionId | None
    primary_label: str
    primary_tooltip: str


_PRIMARY_LABELS = {
    "import": text.OVERVIEW_PRIMARY_IMPORT,
    "scan": text.OVERVIEW_PRIMARY_SCAN,
    "review": text.OVERVIEW_PRIMARY_REVIEW,
    "archive": text.OVERVIEW_PRIMARY_ARCHIVE,
    "settings": text.OVERVIEW_PRIMARY_SETTINGS,
    "model": text.OVERVIEW_PRIMARY_MODEL,
}


class OverviewPresenter:
    """Translate the cached workspace snapshot into overview guidance."""

    def __init__(self, workspace: _WorkspaceSnapshot) -> None:
        """Hold the WorkspaceController-like collaborator (read-only use)."""
        self._workspace = workspace

    def build(self) -> OverviewModel:
        """Compose the checklist and pick the single most reasonable next step.

        任务书 §3：特征提取随扫描自动进行——第 3 步按"缺特征照片数"判定，
        缺特征时的主 CTA 指向扫描（增量补齐）；流程主链为
        导入 → 扫描（登记+特征）→ 审核 → 归档。``None``（空步骤）表示快照
        尚未加载。
        """
        status = self._workspace.status
        if status is None:
            return OverviewModel((), None, "", text.OVERVIEW_STATUS_NONE)
        feature_guidance = self._workspace.feature_guidance()
        archive_guidance = self._workspace.archive_guidance()
        review_guidance = self._workspace.review_guidance()
        features_done = status.has_photos and status.pending_match_count == 0
        steps = (
            OverviewStep(
                text.OVERVIEW_STEP_IMPORT, status.has_persons,
                text.OVERVIEW_STEP_DONE if status.has_persons
                else text.OVERVIEW_STEP_IMPORT_TODO,
            ),
            OverviewStep(
                text.OVERVIEW_STEP_SCAN, status.has_photos,
                text.OVERVIEW_STEP_DONE if status.has_photos
                else text.OVERVIEW_STEP_SCAN_TODO,
            ),
            OverviewStep(
                text.OVERVIEW_STEP_FEATURES, features_done,
                feature_guidance.tooltip,
            ),
            OverviewStep(
                text.OVERVIEW_STEP_REVIEW, status.pending_review_count == 0,
                review_guidance.tooltip,
            ),
            OverviewStep(
                text.OVERVIEW_STEP_ARCHIVE, status.archivable_count == 0,
                archive_guidance.tooltip if archive_guidance.tooltip
                else text.OVERVIEW_STEP_ARCHIVE_NOTE,
            ),
        )
        if not status.has_photos:
            # 扫描（登记+特征）在无模型时也可登记——先扫后装模型可增量补齐。
            primary: PrimaryActionId = "scan"
        elif feature_guidance.next_action == "model":
            primary = "model"
        elif status.pending_match_count:
            # 缺特征照片由下一次扫描按增量规则补齐——CTA 指向扫描。
            primary = "scan"
        elif status.pending_review_count:
            primary = "review"
        elif archive_guidance.enabled:
            primary = "archive"
        elif archive_guidance.next_action == "settings":
            primary = "settings"
        else:
            primary = "scan"
        tooltip = {
            "model": feature_guidance.tooltip,
            "scan": feature_guidance.tooltip if (
                status.pending_match_count or not status.has_photos
            ) else text.OVERVIEW_STEP_SCAN_TODO,
            "archive": archive_guidance.tooltip,
            "settings": archive_guidance.tooltip,
            "review": review_guidance.tooltip,
        }.get(primary, "")
        return OverviewModel(
            steps=steps,
            primary=primary,
            primary_label=_PRIMARY_LABELS.get(primary, ""),
            primary_tooltip=tooltip,
        )
