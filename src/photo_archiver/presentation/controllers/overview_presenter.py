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
    "import", "scan", "match", "review", "archive", "settings", "model",
]


class _WorkspaceSnapshot(Protocol):
    """Minimal read-side port the presenter needs from WorkspaceController."""

    @property
    def status(self):  # noqa: ANN202 - Protocol returns WorkspaceStatus | None
        """Return the cached workspace snapshot (or None before first refresh)."""
        ...

    def match_guidance(self):  # noqa: ANN202
        """Return recognition availability + first unmet prerequisite."""
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
    "match": text.OVERVIEW_PRIMARY_RUN_MATCH,
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

        The primary CTA follows the archival flow (import → scan → recognize
        → review → archive): the first unmet prerequisite wins; when the
        library is fully processed, scanning more photos becomes the next
        step. ``None`` (with empty steps) means the snapshot is not loaded.
        """
        status = self._workspace.status
        if status is None:
            return OverviewModel((), None, "", text.OVERVIEW_STATUS_NONE)
        match_guidance = self._workspace.match_guidance()
        archive_guidance = self._workspace.archive_guidance()
        review_guidance = self._workspace.review_guidance()
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
                text.OVERVIEW_STEP_MATCH,
                status.has_photos and status.pending_match_count == 0,
                match_guidance.tooltip,
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
        if match_guidance.enabled:
            primary: PrimaryActionId = "match"
        elif match_guidance.next_action == "model":
            primary = "model"
        elif match_guidance.next_action in ("import", "scan"):
            primary = match_guidance.next_action
        elif status.pending_review_count:
            primary = "review"
        elif archive_guidance.enabled:
            primary = "archive"
        elif archive_guidance.next_action == "settings":
            primary = "settings"
        else:
            primary = "scan"
        tooltip = {
            "match": match_guidance.tooltip,
            "model": match_guidance.tooltip,
            "import": match_guidance.tooltip,
            "scan": match_guidance.tooltip if not status.has_photos
            else text.OVERVIEW_STEP_SCAN_TODO,
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
