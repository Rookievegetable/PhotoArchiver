"""Batch 7 visual system: centralized hierarchy, focus ring, a11y hooks.

The look is defined once in ``presentation/visual_style.py`` and applied as a
single application-level stylesheet; widgets only opt in via roles. No
widget calls ``setStyleSheet`` itself (UI-rules §16), and status semantics
stay text-first (badges, ✓/○ marks) rather than color-only.

AUDIT-UI-001/002 defense-in-depth: beyond QSS text assertions this module
runs (a) Qt parse-warning capture with a negative control, and (b) minimal
offscreen render probes that pixel-sample real widgets under the production
stylesheet. A future ``palette(Highlight)`` → ``palette.Highlight`` revert
fails ``test_production_stylesheet_parses_without_qt_warning`` AND the
render probes (Qt rejects the whole stylesheet, so primary/danger/focus
colors collapse to the default button look).

Cross-platform note (run #126, the first Linux/macOS CI run of the probes):
native button styles modulate painted brightness while preserving the hue
family (ubuntu ×0.97 / macOS ×0.46 value scaling of the same highlight hue),
so the role probes assert platform-stable color axes — hue family,
saturation, brightness floor and a saturation gap versus the neutral normal
button — never absolute pixel RGB. See the tolerance model above the probe
helpers.
"""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSize, Qt, qInstallMessageHandler
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.application.dtos import ArchivePlan, ArchivePlanItem
from photo_archiver.domain import ArchivePath
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.archive_preview_dialog import (
    ArchivePreviewDialog,
)
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.presentation.views.overview_page import OverviewPage
from photo_archiver.presentation.views.photo_deletion_confirm_dialog import (
    PhotoDeletionConfirmDialog,
)
from photo_archiver.presentation.views.person_deletion_dialog import (
    PersonDeletionDialog,
)
from photo_archiver.presentation.visual_style import (
    BADGE_OBJECT_NAME,
    BANNER_OBJECT_NAME,
    CARD_OBJECT_NAME,
    NAV_RAIL_OBJECT_NAME,
    ROLE_DANGER,
    ROLE_NEUTRAL,
    ROLE_PRIMARY,
    ROLE_SUCCESS,
    ROLE_WARNING,
    SEVERITY_PROPERTY,
    THEME_DARK,
    THEME_LIGHT,
    apply_visual_system,
    assign_role,
    build_stylesheet,
    button_role,
    style_badge,
    style_banner,
    style_card,
    style_empty_state_card,
    theme_tokens,
    token,
)


# ── Stylesheet module (single replacement point) ─────────────────────────────


def test_stylesheet_declares_hierarchy_focus_and_card() -> None:
    qss = build_stylesheet()
    assert 'QPushButton[styleRole="primary"]' in qss
    assert 'QPushButton[styleRole="danger"]' in qss
    assert ":focus" in qss          # visible focus ring for keyboard users
    assert "EmptyStateCard" in qss  # shared empty-state card look


@pytest.mark.parametrize("theme", [THEME_LIGHT, THEME_DARK])
def test_stylesheet_uses_only_valid_palette_function_form(theme: str) -> None:
    """AUDIT-UI-001 syntax guard: ``palette(Role)`` only — never dotted.

    A single ``palette.Highlight`` style rule makes Qt reject the ENTIRE
    application stylesheet (see the parse-warning test below), so the dot
    syntax must stay out even inside comments of the shipped QSS. 阶段 1
    双主题化：两个主题的产物各验一遍（§6.5）。
    """
    qss = build_stylesheet(theme)
    assert "palette(" in qss
    assert not re.search(r"\bpalette\.[A-Za-z_]+", qss)
    # Disabled is a pseudo-state, never a second palette() argument.
    assert not re.search(r"palette\(\s*Disabled\b", qss)


# ── AUDIT-UI-002 layer 1: Qt parse-warning capture ───────────────────────────


@pytest.mark.parametrize("theme", [THEME_LIGHT, THEME_DARK])
def test_production_stylesheet_parses_without_qt_warning(qapp, theme: str) -> None:
    """The shipped stylesheet must not trip Qt's stylesheet parser.

    With the AUDIT-UI-001 defect, Qt emitted
    ``Could not parse application stylesheet`` here and silently dropped
    every Batch 7 rule — the tests stayed green because they only read the
    QSS string. This closes that gap. 阶段 1 双主题化：两主题产物都须零告警。
    """
    messages: list[str] = []
    previous = qInstallMessageHandler(lambda _m, _c, msg: messages.append(msg))
    try:
        qapp.setStyleSheet(build_stylesheet(theme))
        probe = QPushButton()
        probe.ensurePolished()
        probe.grab()  # force style resolution
    finally:
        qInstallMessageHandler(previous)
        qapp.setStyleSheet("")
    parse_failures = [m for m in messages if "Could not parse" in m]
    assert parse_failures == []


def test_broken_palette_syntax_is_detected_by_warning_capture(qapp) -> None:
    """Negative control: the parse detector must fire on the old defect.

    If this ever fails, the parse-warning test above is vacuous (it cannot
    detect the regression it exists for).
    """
    messages: list[str] = []
    previous = qInstallMessageHandler(lambda _m, _c, msg: messages.append(msg))
    try:
        qapp.setStyleSheet("QPushButton { color: palette.Highlight; }")
        probe = QPushButton()
        probe.ensurePolished()
        probe.grab()
    finally:
        qInstallMessageHandler(previous)
        qapp.setStyleSheet("")
    assert any("Could not parse" in m for m in messages)


# ── AUDIT-UI-002 layer 2: minimal render probes (pixel sampling) ─────────────
#
# Platform tolerance model (evidence: run #126, the first Linux/macOS CI run
# of these probes). Native button styles modulate painted brightness while
# preserving the hue family, so absolute pixel equality is a Windows-only
# coincidence, not the visual contract:
#
#   ubuntu  primary painted #247bc1 vs highlight #308cc6 → hue Δ3.6°, value ×0.97
#   macOS   primary painted #16415c vs highlight #308cc6 → hue Δ0.0°, value ×0.46
#   macOS   danger  painted #d66666 vs #c62828           → hue Δ0.0°, tinted lighter
#
# The probes therefore sample a text-less interior strip (no glyph
# anti-aliasing) and assert the platform-stable axes: hue family relative to
# the live palette, enough saturation to read as the role color, enough
# brightness to not collapse toward black, and a saturation gap separating
# the role paint from the neutral idle button. Every window is sized from
# the observed cross-platform span (≥1.4× margin) and every window still
# fails when a rule is dropped or the whole stylesheet is rejected — the
# paint then collapses to the default neutral button look.

PROBE_SIZE = QSize(140, 44)
# Interior strip: ≥20px clear of the 1px QSS border and its AA halo.
_PROBE_SAMPLE_FRACTIONS = (0.15, 0.325, 0.5, 0.675, 0.85)

PRIMARY_HUE_TOLERANCE_DEG = 15.0  # drift observed ≤3.6°; teal (180°, 23° away) stays out
DANGER_HUE_TOLERANCE_DEG = 15.0  # drift observed 0°; magenta (330°) and orange (≥25°) stay out
ROLE_SATURATION_FLOOR = 0.35  # observed ≥0.52; default-button neutrals sit at ≤0.06
ROLE_VALUE_FLOOR = 0.25  # observed ≥0.36; rejects renders too dark to read as the role color
NORMAL_SATURATION_GAP = 0.30  # observed gap ≥0.46; a dropped/rejected rule collapses it to ~0
HIGHLIGHT_PRECONDITION_SAT = 0.5  # Qt6 default highlight #308cc6 sits at sat 0.76


@pytest.fixture
def styled_app(qapp):
    """Production stylesheet installed for the probe, restored afterwards."""
    apply_visual_system(qapp)
    yield qapp
    qapp.setStyleSheet("")


def _button_color(widget: QPushButton, x: int) -> str:
    image = widget.grab().toImage()
    return image.pixelColor(x, widget.height() // 2).name().lower()


def _center_color(widget: QWidget) -> str:
    widget.adjustSize()
    widget.resize(max(widget.width(), 120), max(widget.height(), 34))
    image = widget.grab().toImage()
    return image.pixelColor(widget.width() // 3, widget.height() // 2).name().lower()


def _highlight(qapp) -> str:
    color = qapp.palette().color(qapp.palette().ColorRole.Highlight)
    return color.name().lower()


def _interior_colors(widget: QWidget) -> list[QColor]:
    """Sample a horizontal interior strip of a rendered, text-less widget.

    Callers MUST pass a button without text: glyphs and their anti-aliasing
    are the main source of single-pixel instability. The strip (not a single
    point) keeps the probe stable when a native style shades the interior.
    """
    widget.resize(PROBE_SIZE)
    image = widget.grab().toImage()
    assert image.width() >= 120 and image.height() >= 36, (
        "probe geometry regressed: button rendered smaller than the sampled strip"
    )
    y = image.height() // 2
    return [image.pixelColor(int(image.width() * f), y) for f in _PROBE_SAMPLE_FRACTIONS]


def _median_color(colors: list[QColor]) -> QColor:
    """Per-channel median — robust to residual anti-aliasing or shading."""
    def median(values: list[int]) -> int:
        return sorted(values)[len(values) // 2]

    return QColor(
        median([c.red() for c in colors]),
        median([c.green() for c in colors]),
        median([c.blue() for c in colors]),
    )


def _hsv(color: QColor) -> tuple[float | None, float, float]:
    """(hue in degrees — None when achromatic, saturation, value)."""
    hue, sat, value, _alpha = color.getHsvF()
    return (None if hue < 0 else hue * 360.0), sat, value


def _hue_distance_deg(hue: float, center: float) -> float:
    """Circular hue distance in degrees (red wraps 350° → 10°)."""
    delta = abs(hue - center) % 360.0
    return min(delta, 360.0 - delta)


def _assert_role_paint(
    paint: QColor, hue_center: float, hue_tolerance: float, label: str,
) -> float:
    """Assert the painted median carries the role's platform-stable color axes.

    Each window rejects a specific collapse: desaturation = the role rule is
    gone (default-button neutral paint), hue drift = a different palette role
    or a hardcoded color, near-black = the paint no longer reads as the role
    color. Returns the median saturation for the normal-button gap check.
    """
    hue, sat, value = _hsv(paint)
    assert sat >= ROLE_SATURATION_FLOOR, (
        f"{label} paint is desaturated (sat={sat:.2f} < {ROLE_SATURATION_FLOOR}): "
        "role rule likely dropped or the stylesheet was rejected"
    )
    assert hue is not None and _hue_distance_deg(hue, hue_center) <= hue_tolerance, (
        f"{label} paint left its hue family (hue={hue}, center={hue_center}°): "
        "wrong palette role or hardcoded color"
    )
    assert value >= ROLE_VALUE_FLOOR, (
        f"{label} paint collapsed toward black (value={value:.2f} < {ROLE_VALUE_FLOOR})"
    )
    return sat


def _assert_distinct_from_normal(role_sat: float, normal: QPushButton, label: str) -> None:
    """The role paint must be far more saturated than the neutral idle button."""
    normal_sat = _hsv(_median_color(_interior_colors(normal)))[1]
    gap = role_sat - normal_sat
    assert gap >= NORMAL_SATURATION_GAP, (
        f"{label} paint is not visually distinct from a normal button "
        f"(saturation gap={gap:.2f} < {NORMAL_SATURATION_GAP}): role rule likely dropped"
    )


def test_render_primary_differs_from_normal_button(styled_app) -> None:
    """Primary must really paint palette(Highlight) — not just carry a property.

    Platform-stable contract: the interior stays in the live palette
    Highlight hue family (read here, not hardcoded), saturated and bright
    enough to read as the primary color, and clearly more saturated than the
    neutral normal button. Windows paints the exact palette RGB; Linux/macOS
    shade brightness while keeping the hue (see the tolerance model above).
    """
    highlight = styled_app.palette().color(styled_app.palette().ColorRole.Highlight)
    hue_center, highlight_sat, _value = _hsv(highlight)
    assert highlight_sat >= HIGHLIGHT_PRECONDITION_SAT and hue_center is not None, (
        "probe precondition: palette Highlight must be a saturated color "
        f"(sat={highlight_sat:.2f}) — a neutral highlight voids the primary contract"
    )

    normal = QPushButton()
    primary = QPushButton()
    assign_role(primary, ROLE_PRIMARY)
    role_sat = _assert_role_paint(
        _median_color(_interior_colors(primary)),
        hue_center, PRIMARY_HUE_TOLERANCE_DEG, "primary",
    )
    _assert_distinct_from_normal(role_sat, normal, "primary")

    # Hierarchy beyond color, metric-level: text-ful buttons so the primary's
    # emphasized padding/weight shows up in the size hint (text width dominates
    # the hint on every platform, keeping this comparison safe).
    text_normal = QPushButton("Normal")
    text_primary = QPushButton("Primary")
    assign_role(text_primary, ROLE_PRIMARY)
    assert (
        text_primary.font().bold()
        or text_primary.minimumSizeHint().width() > text_normal.minimumSizeHint().width()
    )


@pytest.mark.parametrize("theme", [THEME_LIGHT, THEME_DARK])
def test_render_danger_paints_the_danger_color(qapp, theme: str) -> None:
    """Danger must really paint the brand red — recognizably, on every theme.

    The danger red is a token (C4 迁移：浅色 #c62828 现值不变，深色 #d13438
    UNVERIFIED——红系色相必须保留，P0-8)，so the exact constant is pinned at
    string level per theme; the render probe then proves it actually paints:
    red hue family, saturated and bright enough to read as danger, clearly
    apart from the neutral normal button. Native styles may tint the paint —
    the windows absorb that without admitting neutrals or other hues.
    """
    apply_visual_system(qapp, theme=theme)
    try:
        expected_red = token("pa-danger-fg", theme)
        assert re.search(rf"background-color:\s*{expected_red}", build_stylesheet(theme)), (
            f"danger rule must keep the {theme} red literal {expected_red} (P0-1 token)"
        )

        normal = QPushButton()
        danger = QPushButton()
        assign_role(danger, ROLE_DANGER)
        role_sat = _assert_role_paint(
            _median_color(_interior_colors(danger)), 0.0, DANGER_HUE_TOLERANCE_DEG, "danger",
        )
        _assert_distinct_from_normal(role_sat, normal, "danger")
    finally:
        _restore_default_look(qapp)


def _restore_default_look(qapp) -> None:
    """Drop the probe stylesheet and restore the captured default palette."""
    apply_visual_system(qapp, theme=THEME_LIGHT)
    qapp.setStyleSheet("")


@pytest.fixture
def dark_styled_app(qapp):
    """Dark-theme production stylesheet + dark palette installed, then restored."""
    apply_visual_system(qapp, theme=THEME_DARK)
    yield qapp
    _restore_default_look(qapp)


def test_render_disabled_roles_keep_disabled_semantics(styled_app) -> None:
    """Disabled primary/danger shed their role colors entirely."""
    primary = QPushButton("P")
    assign_role(primary, ROLE_PRIMARY)
    primary.setEnabled(False)
    danger = QPushButton("D")
    assign_role(danger, ROLE_DANGER)
    danger.setEnabled(False)

    disabled_primary = _center_color(primary)
    disabled_danger = _center_color(danger)
    # Both disabled variants render the same flat disabled look...
    assert disabled_primary == disabled_danger
    # ...never the enabled role colors.
    assert disabled_danger != "#c62828"
    assert disabled_primary != _highlight(styled_app)


def test_render_focus_ring_is_visible(styled_app, qtbot) -> None:
    """A focused button paints a highlight border; an unfocused one does not."""
    host = QWidget()
    qtbot.addWidget(host)
    first = QPushButton("First")
    second = QPushButton("Second")
    QVBoxLayout(host).addWidget(first)
    QVBoxLayout(host).addWidget(second)
    host.show()
    qtbot.waitExposed(host)
    host.activateWindow()
    first.setFocus()
    qtbot.wait(50)
    if styled_app.focusWidget() is not first:
        pytest.skip("window activation unavailable on this platform")

    focused_border = _button_color(first, 0)
    unfocused_border = _button_color(second, 0)
    assert focused_border == _highlight(styled_app)
    assert focused_border != unfocused_border


def test_render_empty_state_card_paints_background_border_radius(styled_app, qtbot) -> None:
    """The card must really paint tint, border and rounded corners.

    AUDIT-UI-001's parse failure killed this rule entirely; also note the
    card paints through the plain-QWidget path where ``palette(<Role>)``
    collapses to the window color on Qt 6.11.1 — hence the rgba() scheme.
    """
    host = QWidget()
    host.resize(400, 300)
    card = QWidget(host)
    style_empty_state_card(card)
    card.setGeometry(0, 0, 400, 300)
    QVBoxLayout(card).addWidget(QLabel("empty"))
    host.show()
    qtbot.addWidget(host)

    image = host.grab().toImage()
    center = image.pixelColor(200, 150).name().lower()
    border = image.pixelColor(0, 150).name().lower()
    corner = image.pixelColor(0, 0).name().lower()
    # Tinted background actually painted (not the host window color).
    assert center != corner
    # Border actually painted and distinct from the fill.
    assert border != center
    # Rounded corner: the exact corner pixel shows through to the host.
    assert corner != border


def test_assign_role_roundtrip(qtbot) -> None:
    button = QPushButton()
    qtbot.addWidget(button)
    assign_role(button, ROLE_DANGER)
    assert button.property("styleRole") == ROLE_DANGER
    assert button_role(button) == ROLE_DANGER


# ── Role assignment across the workflow surfaces ────────────────────────────


def test_overview_primary_cta_is_primary() -> None:
    page = OverviewPage()
    assert button_role(page._primary_button) == ROLE_PRIMARY


@pytest.fixture
def library(qtbot, make_sqlite_context, monkeypatch, tmp_path):
    """A shown MainWindow over a mockable readiness snapshot; no workers.

    Mirrors the fixture in test_photo_library_page (that module owns it for
    its own assertions; the role checks here need the same harness).
    """
    from photo_archiver.application.dtos.workspace import (
        ModelAvailability, WorkspaceStatus,
    )

    empty = WorkspaceStatus(
        has_persons=False, has_photos=False, pending_match_count=0,
        pending_review_count=0, archivable_count=0, archive_root_available=False,
        model_availability=ModelAvailability.UNKNOWN,
    )
    state = SimpleNamespace(value=empty)
    context = make_sqlite_context(
        db_name="visual_ui.db", model_path=tmp_path / "missing-models",
    )
    monkeypatch.setattr(context.services.workspace_readiness, "execute",
                        Mock(side_effect=lambda root: state.value))
    monkeypatch.setattr(context.worker_executor, "submit", Mock(
        side_effect=AssertionError("Visual-system tests must not launch workers"),
    ))
    monkeypatch.setattr(context.photo_list_controller, "load_thumbnail", Mock())
    monkeypatch.setattr(MainWindow, "_effective_archive_root",
                        lambda self: tmp_path / "archive")
    window = MainWindow(context)
    qtbot.addWidget(window)
    window.show()
    window._nav_list.setCurrentRow(1)  # 照片库页
    return SimpleNamespace(window=window, state=state)


def test_main_window_roles_and_empty_state_card(library) -> None:
    window = library.window
    assert button_role(window._bulk_archive_button) == ROLE_PRIMARY
    assert button_role(window._bulk_delete_button) == ROLE_DANGER
    assert button_role(window._empty_scan_button) == ROLE_PRIMARY
    # Batch 7 空态卡片走共享 objectName 挂钩。
    assert window._empty_scan_button.parent().objectName() == "EmptyStateCard"


def test_cancel_button_has_accessible_name(library) -> None:
    """The status-bar cancel entry carries an explicit accessible name."""
    window = library.window
    cancel = window.findChild(QToolButton, "CancelTask")
    assert cancel is not None
    assert cancel.accessibleName() == text.ACTION_CANCEL_TASK


def test_archive_accept_role_toggles_with_dry_run(qtbot) -> None:
    """试运行 = 主操作蓝；正式写入 = 危险红——视觉不可掩盖模式差异。"""
    plan = ArchivePlan(items=(
        ArchivePlanItem(
            photo_id=uuid4(), source_path=Path("photos/p.jpg"),
            target_path=ArchivePath(
                archive_root="D:/archive", person_name="A",
                event_or_date="2024-01-01", original_name="p.jpg",
            ),
            person_id=uuid4(), person_name="A",
        ),
    ))
    dialog = ArchivePreviewDialog(plan, Path("D:/archive"))
    qtbot.addWidget(dialog)
    assert button_role(dialog._accept_button) == ROLE_PRIMARY
    dialog._dry_run_check.setChecked(False)
    assert button_role(dialog._accept_button) == ROLE_DANGER


def test_destructive_confirms_are_danger_with_cancel_default(qtbot) -> None:
    from tests.unit.presentation.test_archive_export_safety import _preview_dto

    photo_dialog = PhotoDeletionConfirmDialog(_preview_dto())
    qtbot.addWidget(photo_dialog)
    box = photo_dialog.findChildren(QDialogButtonBox)[0]
    assert button_role(box.button(QDialogButtonBox.StandardButton.Ok)) == ROLE_DANGER
    assert box.button(QDialogButtonBox.StandardButton.Cancel).isDefault()


def test_person_deletion_confirm_is_danger_with_cancel_default(qtbot) -> None:
    from photo_archiver.domain import Person

    class _FakePersons:
        def execute(self):
            return [Person(name="Alice")]

    class _FakeUseCase:
        def preview(self, ids):
            return Mock(embedding_count=1, recognition_count=2)

        def execute(self, ids):
            return ids

    dialog = PersonDeletionDialog(
        _FakePersons(),  # type: ignore[arg-type]
        _FakeUseCase(),  # type: ignore[arg-type]
    )
    qtbot.addWidget(dialog)
    box = dialog._buttons
    assert button_role(box.button(QDialogButtonBox.StandardButton.Ok)) == ROLE_DANGER
    assert box.button(QDialogButtonBox.StandardButton.Cancel).isDefault()


def test_no_widget_scatters_setstylesheet() -> None:
    """UI-rules §16 guard: only visual_style.py may call app.setStyleSheet."""
    presentation_root = Path(__file__).parents[3] / "src" / "photo_archiver"
    offenders = [
        str(p) for p in presentation_root.rglob("*.py")
        if p.name != "visual_style.py"
        and ".setStyleSheet(" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_status_semantics_are_not_color_only() -> None:
    """Badges carry explicit text and the overview marks differ glyph-wise."""
    assert text.STATUS_BADGE_PENDING and text.STATUS_BADGE_APPROVED
    assert text.STATUS_BADGE_REJECTED and text.STATUS_BADGE_UNMATCHED
    assert text.OVERVIEW_STEP_DONE_MARK != text.OVERVIEW_STEP_TODO_MARK


# ── 2026-10-01 审核中心：可搜索下拉的展开按钮放大（属性选择器作用域） ─────────


def test_searchable_combo_rule_declared_in_stylesheet() -> None:
    qss = build_stylesheet()
    assert 'QComboBox[searchableCombo="true"]::drop-down' in qss
    assert 'QComboBox[searchableCombo="true"]::down-arrow' in qss


def test_searchable_combo_arrow_is_enlarged(styled_app, qtbot) -> None:
    """属性标记的子控件 rect 经 QSS 放大；未标记组合框不受影响。"""
    from PySide6.QtWidgets import QComboBox, QStyle

    from photo_archiver.presentation.visual_style import (
        SEARCHABLE_COMBO_MARK,
        SEARCHABLE_COMBO_PROPERTY,
        mark_searchable_combo,
    )

    marked = QComboBox()
    mark_searchable_combo(marked)
    plain = QComboBox()
    qtbot.addWidget(marked)
    qtbot.addWidget(plain)

    assert marked.property(SEARCHABLE_COMBO_PROPERTY) == SEARCHABLE_COMBO_MARK
    # 展开区放大以平台无关的 comboboxMetrics 比例钉死（各平台默认 drop-down
    # 宽度不同，像素断言会因平台基线漂移——Stage 14-CI 同一教训）。
    indicator = marked.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth)
    assert marked.minimumWidth() >= indicator * 4
    assert plain.minimumWidth() == 0  # 未标记组合框不受影响


# ── 阶段 1：Badge / Card / Banner 构建块与角色扩展（P0-4；N1-N7 落点随阶段
#    2-9 任务书逐点确认，本文件仅冻结约定与渲染探针，views 零新增使用点）──


def test_building_blocks_and_new_roles_declared_in_stylesheet() -> None:
    """P0-4 §2 选择器全文逐组在单源 QSS 中声明（双主题共用模板）。"""
    for theme in (THEME_LIGHT, THEME_DARK):
        qss = build_stylesheet(theme)
        assert "QLabel#Badge {" in qss
        for severity in ("success", "warning", "danger", "info", "neutral"):
            assert f'QLabel#Badge[severity="{severity}"]' in qss
        assert "QFrame#Card {" in qss
        assert "QFrame#Banner {" in qss
        for severity in ("info", "warning", "danger"):
            assert f'QFrame#Banner[severity="{severity}"]' in qss
        for role in (ROLE_SUCCESS, ROLE_WARNING, ROLE_NEUTRAL):
            assert f'QPushButton[styleRole="{role}"]' in qss


def test_badge_severity_property_and_domain(qtbot) -> None:
    """Badge：objectName＋severity 动态属性；取值域之外拒绝（§3.2 规则 3）。"""
    badge = QLabel()
    qtbot.addWidget(badge)
    style_badge(badge, "warning")
    assert badge.objectName() == BADGE_OBJECT_NAME
    assert badge.property(SEVERITY_PROPERTY) == "warning"
    style_badge(badge, "info")  # 变更 = setProperty + repolish（§3.2 规则 2）
    assert badge.property(SEVERITY_PROPERTY) == "info"
    with pytest.raises(ValueError):
        style_badge(badge, "critical")


def test_card_and_banner_building_blocks(qtbot) -> None:
    """Card/Banner：WA_StyledBackground＋severity 取值域（info/warning/danger）。"""
    banner = QFrame()
    qtbot.addWidget(banner)
    style_banner(banner, "warning")
    assert banner.objectName() == BANNER_OBJECT_NAME
    assert banner.property(SEVERITY_PROPERTY) == "warning"
    assert banner.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    with pytest.raises(ValueError):
        style_banner(banner, "success")  # Banner 取值域不含 success/neutral

    card = QFrame()
    qtbot.addWidget(card)
    style_card(card)
    assert card.objectName() == CARD_OBJECT_NAME
    assert card.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)


def _badge_interior(badge: QLabel) -> str:
    badge.setFixedSize(48, 24)
    image = badge.grab().toImage()
    return image.pixelColor(badge.width() // 2, badge.height() // 2).name().lower()


@pytest.mark.parametrize("styled", ["styled_app", "dark_styled_app"])
def test_render_badge_severities_paint_distinctly(styled: str, request) -> None:
    """五个 severity 徽章真实涂出两两可区分的底色（像素探针，双主题）。"""
    request.getfixturevalue(styled)  # 安装（浅/深）主题样式表与 palette
    host = QWidget()
    layout = QHBoxLayout(host)
    for severity in ("success", "warning", "danger", "info", "neutral"):
        badge = QLabel()
        style_badge(badge, severity)
        layout.addWidget(badge)
    host.show()
    host.grab()  # force style resolution before per-badge grabs

    colors = {
        severity: _badge_interior(badge)
        for severity, badge in (
            (severity, layout.itemAt(index).widget())
            for index, severity in enumerate(
                ("success", "warning", "danger", "info", "neutral")
            )
        )
    }
    assert len(set(colors.values())) == len(colors)


@pytest.mark.parametrize("theme", [THEME_LIGHT, THEME_DARK])
def test_render_new_role_buttons_paint_role_colors(qapp, theme: str) -> None:
    """success/warning/neutral 按钮角色真实涂色（绿/琥珀/有意消色差灰）。"""
    apply_visual_system(qapp, theme=theme)
    try:
        normal = QPushButton()
        success = QPushButton()
        assign_role(success, ROLE_SUCCESS)
        warning = QPushButton()
        assign_role(warning, ROLE_WARNING)
        neutral = QPushButton()
        assign_role(neutral, ROLE_NEUTRAL)

        success_paint = _median_color(_interior_colors(success))
        warning_paint = _median_color(_interior_colors(warning))
        neutral_paint = _median_color(_interior_colors(neutral))
        _assert_role_paint(success_paint, 118.0, 30.0, "success")
        _assert_role_paint(warning_paint, 40.0, 25.0, "warning")

        # neutral 走有意的低饱和实底：色调不再是角色色，且与普通按钮的
        # 中性观感可区分（规则被删/样式表被整体拒绝时塌缩为同一涂色）。
        _hue, neutral_sat, _value = _hsv(neutral_paint)
        assert neutral_sat <= 0.12
        assert neutral_paint != _median_color(_interior_colors(normal))
        assert len({success_paint.name(), warning_paint.name(), neutral_paint.name()}) == 3
    finally:
        _restore_default_look(qapp)


def test_theme_tokens_are_frozen_shapes() -> None:
    """Token 表形状守护：双主题同键集，深色为 P0-1 建议值（UNVERIFIED）。"""
    light = theme_tokens(THEME_LIGHT)
    dark = theme_tokens(THEME_DARK)
    assert set(light) == set(dark)
    # C4 现值契约：danger 浅色不变、红系色相保留。
    assert light["pa-danger-fg"] == "#c62828"
    assert light["pa-danger-border"] == "#8e1f1c"
    assert dark["pa-danger-fg"] == "#d13438"
    # R6/B-3 校准基线：C2 目标 pa-text-secondary 浅色 #5c5c5c。
    assert light["pa-text-secondary"] == "#5c5c5c"
    assert dark["pa-text-secondary"] == "#c8c8c8"


# ── 阶段 2：主窗口 chrome（导航 rail / 工具栏 / 状态栏）＋概览页五步卡 ────────


def test_chrome_rules_declared_in_stylesheet() -> None:
    """Chrome 组选择器在单源 QSS 双主题中声明（阶段 2 落位）。"""
    for theme in (THEME_LIGHT, THEME_DARK):
        qss = build_stylesheet(theme)
        assert "QToolBar#Main {" in qss
        assert "QToolBar#Main::separator" in qss
        assert "QListWidget#NavRail {" in qss
        assert "QListWidget#NavRail::item:selected" in qss
        # 聚焦态焦点环恢复（ID＋伪类特异性高于基行 border:none；1px＝P0-1 §1.4 列表冻结值）。
        assert "QListWidget#NavRail:focus {" in qss
        assert "QStatusBar {" in qss
        assert "QStatusBar QProgressBar::chunk" in qss
        # 横幅内文字着色（QSS color 不自 QFrame 级联到子 QLabel，需显式规则）。
        for severity in ("info", "warning", "danger"):
            assert f'QFrame#Banner[severity="{severity}"] QLabel' in qss


@pytest.mark.parametrize("theme", [THEME_LIGHT, THEME_DARK])
def test_render_nav_rail_selected_item_paints_highlight(qapp, theme: str) -> None:
    """导航 rail 选中项真实涂出高亮（选中≠未选中，双主题像素探针）。"""
    apply_visual_system(qapp, theme=theme)
    try:
        host = QWidget()
        layout = QVBoxLayout(host)
        rail = QListWidget(host)
        rail.setObjectName(NAV_RAIL_OBJECT_NAME)
        rail.setFixedWidth(150)
        for label in ("AA", "BB", "CC"):
            rail.addItem(label)
        rail.setCurrentRow(0)
        layout.addWidget(rail)
        host.show()
        host.grab()

        def interior(item_index: int) -> str:
            rect = rail.visualItemRect(rail.item(item_index))
            origin = rail.viewport().mapTo(host, rect.topLeft())
            image = host.grab().toImage()
            # 采样点避开左侧文字与边框/圆角（条目右段中部）。
            return image.pixelColor(
                int(origin.x() + rect.width() * 0.7),
                int(origin.y() + rect.height() * 0.5),
            ).name().lower()

        selected = interior(0)
        unselected = interior(2)
        assert selected != unselected, (
            f"nav rail selected item {selected} must differ from unselected "
            f"{unselected}: chrome rule likely dropped or stylesheet rejected"
        )
    finally:
        _restore_default_look(qapp)


@pytest.mark.parametrize("theme", [THEME_LIGHT, THEME_DARK])
def test_render_overview_banner_paints_info_background(qapp, theme: str) -> None:
    """概览欢迎横幅真实涂底（横幅底色≠窗口底色，双主题像素探针）。"""
    apply_visual_system(qapp, theme=theme)
    try:
        host = QWidget()
        host.resize(320, 200)
        layout = QVBoxLayout(host)
        banner = QFrame(host)
        style_banner(banner, "info")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(0, 0, 0, 0)
        banner_layout.addWidget(QLabel(text.OVERVIEW_WELCOME, banner))
        layout.addWidget(banner)
        layout.addStretch()
        host.show()
        image = host.grab().toImage()
        banner_rect = banner.geometry()
        banner_bg = image.pixelColor(
            int(banner_rect.x() + banner_rect.width() * 0.85),
            int(banner_rect.y() + banner_rect.height() * 0.5),
        ).name().lower()
        window_bg = image.pixelColor(280, 180).name().lower()
        assert banner_bg != window_bg, (
            f"overview banner {banner_bg} must not paint the window background "
            f"{window_bg}: banner rule likely dropped or stylesheet rejected"
        )
    finally:
        _restore_default_look(qapp)


def test_overview_page_renders_banner_and_five_step_cards(qtbot) -> None:
    """概览页结构：info 横幅＋五张步骤卡；render_model/set_busy 契约不变。"""
    from photo_archiver.presentation.controllers.overview_presenter import (
        OverviewModel, OverviewStep,
    )

    page = OverviewPage()
    qtbot.addWidget(page)

    banners = page.findChildren(QFrame, BANNER_OBJECT_NAME)
    assert len(banners) == 1
    assert banners[0].property(SEVERITY_PROPERTY) == "info"
    assert banners[0].testAttribute(Qt.WidgetAttribute.WA_StyledBackground)

    cards = page.findChildren(QFrame, CARD_OBJECT_NAME)
    assert len(cards) == 5
    assert all(card.testAttribute(Qt.WidgetAttribute.WA_StyledBackground) for card in cards)

    # CTA 契约（test_overview_primary_cta_is_primary 之外的结构级回归）。
    assert button_role(page._primary_button) == ROLE_PRIMARY

    steps = tuple(
        OverviewStep(label=f"步骤{i}", done=i % 2 == 0, detail=f"说明{i}")
        for i in range(5)
    )
    page.render_model(OverviewModel(steps, "scan", text.OVERVIEW_PRIMARY_SCAN, "tip"))
    assert not page._primary_button.isHidden()
    assert page._primary_button.text() == text.OVERVIEW_PRIMARY_SCAN
    assert page._primary_button.toolTip() == "tip"
    assert page._primary_button.isEnabled()
    assert not any(card.isHidden() for card in cards)
    # 状态＝符号＋文字（非仅色，§10-7）；正文＝模型 detail。
    first_labels = {label.text() for label in cards[0].findChildren(QLabel)}
    assert first_labels == {
        "步骤0", f"{text.OVERVIEW_STEP_DONE_MARK} {text.OVERVIEW_STEP_DONE}", "说明0",
    }
    assert text.OVERVIEW_STEP_TODO_MARK in cards[1].findChildren(QLabel)[1].text()
    assert (
        f"{text.OVERVIEW_STEP_TODO_MARK} {text.OVERVIEW_STEP_TODO}"
        in {label.text() for label in cards[1].findChildren(QLabel)}
    )

    page.set_busy(True, "扫描")
    assert not page._primary_button.isEnabled()
    assert page._primary_button.toolTip() == text.OVERVIEW_PRIMARY_BUSY.format(label="扫描")
    page.set_busy(False, "扫描")
    assert page._primary_button.isEnabled()
    assert page._primary_button.toolTip() == "tip"

    # 空快照（启动未加载）：五卡全隐、无 CTA——只渲染模型内容。
    page.render_model(OverviewModel((), None, "", ""))
    assert all(card.isHidden() for card in cards)
    assert page._primary_button.isHidden()


def test_nav_rail_object_name_hook(library) -> None:
    """主窗口导航 rail 挂有 NavRail objectName（chrome QSS 的落点）。"""
    rail = library.window.findChild(QListWidget, NAV_RAIL_OBJECT_NAME)
    assert rail is library.window._nav_list
    assert rail.objectName() == NAV_RAIL_OBJECT_NAME
